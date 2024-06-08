import logging
import os.path
import re
from abc import abstractmethod, ABC
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from random import Random
from typing import TypedDict, List
from uuid import UUID
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import libvirt
from libvirt import virConnect

from virtomate.error import NotFoundError, IllegalStateError, Conflict

logger = logging.getLogger(__name__)

# Maps virDomainState to a human-readable string.
# https://libvirt.org/html/libvirt-libvirt-domain.html#virDomainState
STATE_MAPPINGS: dict[int, str] = {
    libvirt.VIR_DOMAIN_NOSTATE: "no state",
    libvirt.VIR_DOMAIN_RUNNING: "running",
    libvirt.VIR_DOMAIN_BLOCKED: "blocked",
    libvirt.VIR_DOMAIN_PAUSED: "paused",
    libvirt.VIR_DOMAIN_SHUTDOWN: "shutdown",
    libvirt.VIR_DOMAIN_SHUTOFF: "shut-off",
    libvirt.VIR_DOMAIN_CRASHED: "crashed",
    libvirt.VIR_DOMAIN_PMSUSPENDED: "suspended",
}


class DomainDescriptor(TypedDict):
    """Descriptor of a libvirt domain."""

    uuid: str
    """UUID of the domain"""
    name: str
    """Name of the domain"""
    state: str
    """Current state of the domain"""


class AddressDescriptor(TypedDict):
    """Descriptor of an interface address of a libvirt domain."""

    address: str
    """Address assigned to this interface"""
    prefix: int
    """Prefix (netmask) of the address"""
    type: str
    """Human-readable type of the address (either `IPv4` or `IPv6`)"""


class InterfaceDescriptor(TypedDict):
    """Descriptor of an interface of a libvirt domain."""

    name: str
    """Human-readable name of the interface"""
    hwaddr: str
    """MAC address of the interface"""
    addresses: Sequence[AddressDescriptor]
    """Addresses assigned to the interface"""


class AddressSource(Enum):
    LEASE = 1

    AGENT = 2

    ARP = 3


class CloneMode(Enum):
    COPY = 1

    REFLINK = 2

    LINKED = 3


def list_domains(conn: virConnect) -> Sequence[DomainDescriptor]:
    """Return a list of all domains.

    Args:
        conn: libvirt connection

    Returns:
        List of all domains

    Raises:
        libvirt.libvirtError: if a libvirt operation fails
    """
    domains = conn.listAllDomains()
    mapped_domains: List[DomainDescriptor] = []
    for domain in domains:
        (state, _) = domain.state()
        readable_state = "unknown"
        if state in STATE_MAPPINGS:
            readable_state = STATE_MAPPINGS[state]

        mapped_domain: DomainDescriptor = {
            "uuid": domain.UUIDString(),
            "name": domain.name(),
            "state": readable_state,
        }
        mapped_domains.append(mapped_domain)

    # Sort to ensure stable order
    return sorted(mapped_domains, key=lambda m: m["uuid"])


def list_domain_interfaces(
    conn: virConnect, domain_name: str, source: AddressSource
) -> Sequence[InterfaceDescriptor]:
    """List all network interfaces of a domain.

    Addresses are obtained from the given ``source``. :py:class:`AddressSource.LEASE` consults libvirt's built-in DHCP
    server. Consequently, static addresses will be absent from the results as will be addresses assigned by an external
    DHCP server. :py:class:`AddressSource.AGENT` uses the QEMU Guest Agent to determine the addresses on the guest. This
    is the only method that delivers a complete list of addresses, but requires the QEMU Guest Agent to be installed.
    :py:class:`AddressSource.ARP` queries the host's ARP cache. The results returned from the ARP cache might be
    incomplete or outdated. Furthermore, the reported network mask is always 0 because layer 2 has no notion of network
    masks.

    Args:
        conn: libvirt connection
        domain_name: Name of the domain whose interfaces should be listed
        source: Source of address information

    Returns:
        List of all interfaces of a domain and their addresses

    Raises:
        virtomate.error.NotFoundError: if the domain does not exist
        virtomate.error.IllegalStateException: if the domain is not running
        libvirt.libvirtError: if a libvirt operation fails
    """
    # Convert the potential libvirt error in one of virtomate's exceptions because the domain lookup doubles as argument
    # validation which is virtomate's responsibility.
    try:
        domain = conn.lookupByName(domain_name)
    except libvirt.libvirtError as ex:
        raise NotFoundError(
            "Domain '%(domain)s' does not exist" % {"domain": domain_name}
        ) from ex

    match source:
        case AddressSource.LEASE:
            s = libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE
        case AddressSource.AGENT:
            s = libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_AGENT
        case AddressSource.ARP:
            s = libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_ARP
        case _:
            raise AssertionError("Unknown address source: {}".format(source))

    if not _domain_in_state(conn, domain_name, libvirt.VIR_DOMAIN_RUNNING):
        raise IllegalStateError(
            "Domain '%(domain)s' is not running" % {"domain": domain_name}
        )

    interfaces = domain.interfaceAddresses(s, 0)

    result: List[InterfaceDescriptor] = []
    for name, props in interfaces.items():
        addresses: List[AddressDescriptor] = []
        for addr in props["addrs"]:
            # https://libvirt.org/html/libvirt-libvirt-network.html#virIPAddrType
            match addr["type"]:
                case libvirt.VIR_IP_ADDR_TYPE_IPV4:
                    addr_type = "IPv4"
                case libvirt.VIR_IP_ADDR_TYPE_IPV6:
                    addr_type = "IPv6"
                case _:
                    raise AssertionError(
                        "Unknown address type: {}".format(addr["type"])
                    )

            address: AddressDescriptor = {
                "address": addr["addr"],
                "prefix": addr["prefix"],
                "type": addr_type,
            }
            addresses.append(address)

        interface: InterfaceDescriptor = {
            "name": name,
            "hwaddr": props["hwaddr"],
            "addresses": sorted(addresses, key=lambda a: a["address"]),
        }
        result.append(interface)

    # Sort to ensure stable order
    return sorted(result, key=lambda i: i["hwaddr"])


def clone_domain(
    conn: virConnect, name: str, new_name: str, mode: CloneMode = CloneMode.COPY
) -> None:
    """Clone the domain ``name`` into a domain named ``new_name``. The domain to be cloned must be shut down before it
    can be cloned.

    Args:
        conn: libvirt connection
        name: Name of the domain to clone
        new_name: Name of the cloned domain
        mode: How the domain should be cloned.

    Raises:
        virtomate.error.NotFoundError: if the domain to clone does not exist
        virtomate.error.Conflict: if a domain with the same name as the cloned domain already exists
        virtomate.error.IllegalStateError: if domain to be cloned is not shut down
        libvirt.libvirtError: if a libvirt operation fails
    """
    if not _domain_exists(conn, name):
        raise NotFoundError("Domain '%(domain)s' does not exist" % {"domain": name})

    if _domain_exists(conn, new_name):
        raise Conflict("Domain '%(domain)s' exists already" % {"domain": new_name})

    # Only domains that are shut off can be cloned.
    if not _domain_in_state(conn, name, libvirt.VIR_DOMAIN_SHUTOFF):
        raise IllegalStateError(
            "Domain '%(domain)s' must be shut off to be cloned" % {"domain": name}
        )

    domain_to_clone = conn.lookupByName(name)
    domain_xml = domain_to_clone.XMLDesc()
    config = ElementTree.fromstring(domain_xml)
    uuid_factory = LibvirtUUIDFactory(conn)
    mac_factory = LibvirtMACFactory(conn)

    op = CloneOperation(config, new_name, mode, uuid_factory, mac_factory)
    op.perform(conn)


# TODO: Make public
def _domain_exists(conn: virConnect, name: str) -> bool:
    """Returns `True` if a domain with the given name exists, `False` otherwise."""
    try:
        conn.lookupByName(name)
        return True
    except libvirt.libvirtError:
        return False


# TODO: Make public
def _domain_in_state(conn: virConnect, name: str, state: int) -> bool:
    try:
        domain = conn.lookupByName(name)
        (domain_state, _) = domain.state(0)
        # bool() to placate mypy because __eq__() can return NotImplemented.
        return bool(state == domain_state)
    except libvirt.libvirtError:
        return False


class MACFactory(ABC):
    @abstractmethod
    def create_from(self, mac_address: str) -> str: ...


class LibvirtMACFactory(MACFactory):
    _conn: virConnect
    _rnd: Random
    _attempts: int

    def __init__(self, conn: virConnect, rnd: Random = Random()):
        self._conn = conn
        self._rnd = rnd
        self._attempts = 0

    def create_from(self, mac_address: str) -> str:
        if not re.match(
            "^([a-f0-9]{2}:){5}[a-f0-9]{2}$", mac_address, flags=re.IGNORECASE
        ):
            raise ValueError("Invalid MAC address: {}".format(mac_address))

        # 100 attempts should be enough to find a free MAC address.
        for i in range(1, 101):
            self._attempts = i

            oui = mac_address[:8]
            rnd_segments = ["%02x" % self._rnd.randint(0x00, 0xFF) for _ in range(0, 3)]
            generated_mac = oui + ":" + ":".join(rnd_segments)

            if not self._mac_exists(generated_mac):
                return generated_mac

        raise Conflict("Failed to generate an unoccupied MAC address")

    def _mac_exists(self, mac_address: str) -> bool:
        """Tests whether the given `mac_address` is already in use by another locally defined machine. Returns `True`
        if it is, `False` otherwise.

        Note that this test does not guarantee that a MAC address is not used by another guest on another machine in the
        same subnet. Consequently, collisions are still possible.
        """
        for domain in self._conn.listAllDomains(0):
            # Checking the XML configuration allows to prevent collisions with machines that are not running. Consulting
            # the ARP cache to prevent collisions with running machines on other hosts is not possible because libvirt
            # does not expose it. Asking `arp` does not work either because we might be connected to a remote host in a
            # different network.
            domain_tag = ElementTree.fromstring(domain.XMLDesc(0))
            for mac_tag in domain_tag.findall("devices/interface/mac"):
                if "address" not in mac_tag.attrib:
                    continue

                if mac_tag.attrib["address"] == mac_address:
                    return True

        return False


class UUIDFactory(ABC):
    @abstractmethod
    def create(self) -> UUID: ...


class LibvirtUUIDFactory(UUIDFactory):
    _conn: virConnect
    _rnd: Random
    _attempts: int

    def __init__(self, conn: virConnect, rnd: Random = Random()):
        self._conn = conn
        self._rnd = rnd
        self._attempts = 0

    def create(self) -> UUID:
        # 100 attempts should be enough to find a UUID that is not already in use.
        for i in range(1, 101):
            self._attempts = i

            uuid4 = UUID(int=self._rnd.getrandbits(128), version=4)
            if not self._uuid_exists(uuid4):
                return uuid4

        raise Conflict("Failed to generate an unoccupied UUID")

    def _uuid_exists(self, uuid4: UUID) -> bool:
        """Tests whether the given `uuid` is already in use by another locally defined machine. Returns `True` if it is,
        `False` otherwise.
        """
        for domain in self._conn.listAllDomains(0):
            if uuid4 == UUID(bytes=domain.UUID()):
                return True

        return False


@dataclass
class SourceFirmware:
    """Firmware of a virtual machine about to be cloned."""

    source_path: str
    clone_name: str

    @property
    def pool_path(self) -> str:
        return os.path.dirname(self.source_path)

    @property
    def clone_path(self) -> str:
        return os.path.join(self.pool_path, self.cloned_volume_name)

    @property
    def cloned_volume_name(self) -> str:
        return self.clone_name + "-" + os.path.basename(self.source_path)


@dataclass
class SourceVolume:
    """Volume of a virtual machine about to be cloned."""

    source_path: str
    source_type: str
    clone_name: str

    @property
    def pool_path(self) -> str:
        return os.path.dirname(self.source_path)

    @property
    def clone_path(self) -> str:
        return os.path.join(self.pool_path, self.cloned_volume_name)

    @property
    def cloned_volume_name(self) -> str:
        # We deliberately do not mess with file extensions even though we could end up with a QCOW2 volume named
        # `clone.raw`. File extensions a just names and people are free to pick what they like. So we would never be
        # able to tell apart file extensions from whatever else could come after the last dot in a file name.
        return self.clone_name + "-" + os.path.basename(self.source_path)


class CloneOperation:
    _clone_name: str
    _config: Element
    _mode: CloneMode
    _firmware_to_clone: list[SourceFirmware]
    _volumes_to_clone: list[SourceVolume]

    def __init__(
        self,
        config: Element,
        new_name: str,
        mode: CloneMode,
        uuid_factory: UUIDFactory,
        mac_factory: MACFactory,
    ):
        self._clone_name = new_name
        self._config = config
        self._mode = mode
        self._firmware_to_clone = []
        self._volumes_to_clone = []

        element_name = self._config.find("name")
        # XML schema guarantees <name> to be present, hence an assertion.
        assert element_name is not None, "Required <name> is missing"
        element_name.text = new_name

        element_uuid = self._config.find("uuid")
        # XML schema guarantees <uuid> to be present, hence an assertion.
        assert element_uuid is not None, "Required <uuid> is missing"
        element_uuid.text = str(uuid_factory.create())

        for fw_disk in self._config.findall("os/nvram"):
            # Since libvirt 8.5.0, there can be a `type` attribute that allows non-file firmware. It is unlikely that we
            # can do anything with firmware loaded over the network. Maybe something can be done with disks.
            if "type" in fw_disk.attrib and fw_disk.attrib["type"] not in ["file"]:
                continue

            if fw_disk.text is None:
                continue

            # There is a `format` attribute on <loader> and <nvram> that allows to load firmware from raw or QCOW2
            # files. This would only concern virtomate if we ever decided to apply `CloneMode` to firmware.
            # Is there any reason to? The files are usually tiny (2 MB tops).
            source_firmware = SourceFirmware(fw_disk.text, new_name)
            self._firmware_to_clone.append(source_firmware)

            fw_disk.text = source_firmware.clone_path

        for disk in self._config.findall("devices/disk"):
            # No need to clone disks that area read-only.
            if disk.find("readonly") is not None:
                continue

            # We can probably clone a lot more than only files through libvirt. Maybe someone can figure that out.
            if "type" not in disk.attrib or disk.attrib["type"] not in ["file"]:
                continue

            source = disk.find("source")
            if source is None or "file" not in source.attrib:
                continue

            driver = disk.find("driver")
            if driver is None or "type" not in driver.attrib:
                continue

            source_volume = SourceVolume(
                source.attrib["file"], driver.attrib["type"], new_name
            )
            self._volumes_to_clone.append(source_volume)

            source.attrib["file"] = source_volume.clone_path
            # Linked clones must be qcow2.
            if self._mode == CloneMode.LINKED:
                driver.attrib["type"] = "qcow2"

        for mac in self._config.findall("devices/interface/mac"):
            if "address" not in mac.attrib:
                continue

            new_address = mac_factory.create_from(mac.attrib["address"])
            mac.attrib["address"] = new_address

        # Remove <target/> element of each interface. Hypervisors will automatically generate an appropriate name. See
        # https://libvirt.org/formatdomain.html#overriding-the-target-element.
        for iface in self._config.findall("devices/interface"):
            target = iface.find("target")
            if target is None:
                continue

            iface.remove(target)

        for graphics in self._config.findall("devices/graphics"):
            if "port" in graphics.attrib:
                del graphics.attrib["port"]
                graphics.attrib["autoport"] = "yes"

            if "tlsPort" in graphics.attrib:
                del graphics.attrib["tlsPort"]
                graphics.attrib["autoport"] = "yes"

            # VNC Web Sockets do not support `autoport`.
            if "websocket" in graphics.attrib:
                graphics.attrib["websocket"] = "-1"

    def clone_config(self) -> str:
        return ElementTree.tostring(self._config, encoding="unicode")

    def perform(self, conn: virConnect) -> None:
        try:
            conn.defineXML(self.clone_config())

            for fw in self._firmware_to_clone:
                CloneOperation._copy_firmware(conn, fw)

            # While `CloneMode.COPY` and `CloneMode.LINKED` should work with any volume format, `CloneMode.REFLINK` is
            # limited to filesystems with reflink support and raw volumes due to libvirt's reliance on qemu-img (see
            # https://bugzilla.redhat.com/show_bug.cgi?id=1324006). We leave it to libvirt to raise errors because
            # libvirt knows best, and it spares us to perform version checks, for example, "Raise exception if libvirt
            # version is smaller than X".
            #
            # Invoking `cp` ourselves to work around qemu-img's deficiencies is not an option because virtomate might
            # operate on a remote machine.
            for volume in self._volumes_to_clone:
                match self._mode:
                    case CloneMode.COPY:
                        CloneOperation._copy_volume(conn, volume, False)
                    case CloneMode.REFLINK:
                        CloneOperation._copy_volume(conn, volume, True)
                    case CloneMode.LINKED:
                        CloneOperation._link_volume(conn, volume)
        except BaseException:
            for fw in self._firmware_to_clone:
                CloneOperation._delete_volume(conn, fw.clone_path)

            for volume in self._volumes_to_clone:
                CloneOperation._delete_volume(conn, volume.clone_path)

            # Has to happen last because domains with firmware cannot be undefined.
            CloneOperation._undefine_domain(conn, self._clone_name)

            raise

    @staticmethod
    def _copy_firmware(conn: virConnect, source_fw: SourceFirmware) -> None:
        mac_tag = ElementTree.Element("volume")
        name_tag = ElementTree.SubElement(mac_tag, "name")
        name_tag.text = source_fw.cloned_volume_name
        volume_xml = ElementTree.tostring(mac_tag, encoding="unicode")

        pool = conn.storagePoolLookupByTargetPath(source_fw.pool_path)
        fw_to_copy = conn.storageVolLookupByPath(source_fw.source_path)
        pool.createXMLFrom(volume_xml, fw_to_copy, 0)

    @staticmethod
    def _copy_volume(
        conn: virConnect, source_volume: SourceVolume, reflink: bool = False
    ) -> None:
        volume_tag = ElementTree.Element("volume")
        name_tag = ElementTree.SubElement(volume_tag, "name")
        name_tag.text = source_volume.cloned_volume_name
        target_tag = ElementTree.SubElement(volume_tag, "target")
        ElementTree.SubElement(
            target_tag, "format", {"type": source_volume.source_type}
        )
        volume_xml = ElementTree.tostring(volume_tag, encoding="unicode")

        create_flags = 0
        if reflink:
            create_flags |= libvirt.VIR_STORAGE_VOL_CREATE_REFLINK

        pool = conn.storagePoolLookupByTargetPath(source_volume.pool_path)
        volume_to_copy = conn.storageVolLookupByPath(source_volume.source_path)
        pool.createXMLFrom(volume_xml, volume_to_copy, create_flags)

    @staticmethod
    def _link_volume(conn: virConnect, source_volume: SourceVolume) -> None:
        volume_tag = ElementTree.Element("volume")
        name_tag = ElementTree.SubElement(volume_tag, "name")
        name_tag.text = source_volume.cloned_volume_name
        target_tag = ElementTree.SubElement(volume_tag, "target")
        ElementTree.SubElement(target_tag, "format", {"type": "qcow2"})
        backing_store_tag = ElementTree.SubElement(volume_tag, "backingStore")
        path_tag = ElementTree.SubElement(backing_store_tag, "path")
        path_tag.text = source_volume.source_path
        ElementTree.SubElement(
            backing_store_tag, "format", {"type": source_volume.source_type}
        )
        volume_xml = ElementTree.tostring(volume_tag, encoding="unicode")

        pool = conn.storagePoolLookupByTargetPath(source_volume.pool_path)
        pool.createXML(volume_xml)

    @staticmethod
    def _undefine_domain(conn: virConnect, name: str) -> None:
        try:
            domain = conn.lookupByName(name)
            domain.undefine()
        except BaseException as ex:
            logger.debug(
                "Failed to undefine domain %s while rolling back clone: %s",
                name,
                ex,
            )

    @staticmethod
    def _delete_volume(conn: virConnect, volume_path: str) -> None:
        try:
            volume = conn.storageVolLookupByPath(volume_path)
            volume.delete()
        except BaseException as ex:
            logger.debug(
                "Failed to delete volume %s while rolling back clone: %s",
                volume_path,
                ex,
            )
