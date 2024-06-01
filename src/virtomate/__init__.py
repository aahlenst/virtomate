#!/usr/bin/env python3
import abc
import argparse
import importlib.metadata
import json
import logging
import re
import os.path
from typing import TypedDict, Iterable
from dataclasses import dataclass
from enum import Enum
import random
from random import Random
from types import TracebackType
from typing import Dict, Sequence
from uuid import UUID
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import libvirt
import libvirt_qemu
from libvirt import virConnect

logger = logging.getLogger(__name__)


def libvirt_error_handler(ctx, error):  # type: ignore
    # TODO: Make it useful. Problem: Duplicates (?) contents of libvirt.libvirtError which would not be useful.
    #  https://libvirt.gitlab.io/libvirt-appdev-guide-python/libvirt_application_development_guide_using_python-Error_Handling-Registering_Error_Handler.html
    logger.debug("libvirt error %s", error)


libvirt.registerErrorHandler(f=libvirt_error_handler, ctx=None)

MachineList = Sequence[Dict[str, str]]
AddressList = Sequence[Dict[str, str]]

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


class AddressSource(Enum):
    LEASE = 1

    AGENT = 2

    ARP = 3


class CloneMode(Enum):
    COPY = 1

    REFLINK = 2

    LINKED = 3


class TargetDescriptor(TypedDict):
    path: str
    format_type: str | None


class BackingStoreDescriptor(TypedDict):
    path: str | None
    format_type: str | None


class VolumeDescriptor(TypedDict):
    name: str
    key: str
    capacity: int | None
    allocation: int | None
    physical: int | None
    type: str | None
    target: TargetDescriptor | None
    backing_store: BackingStoreDescriptor | None


class Hypervisor:
    _conn: virConnect

    def __init__(self, url: str | None = None):
        self._conn = libvirt.open(url)

    def __enter__(self) -> "Hypervisor":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._conn is not None:
            self._conn.close()

    def connection(self) -> virConnect:
        """
        Return the underlying connection to the libvirt daemon for testing purposes. It allows to perform actions
        otherwise not supported by this class. This is especially useful when using libvirt's mock driver that keeps its
        state in memory only.
        """
        return self._conn

    def list_domains(self) -> MachineList:
        domains = self._conn.listAllDomains()
        mapped_domains = []
        for domain in domains:
            (state, _) = domain.state()
            readable_state = "unknown"
            if state in STATE_MAPPINGS:
                readable_state = STATE_MAPPINGS[state]

            mapped_domain = {
                "uuid": domain.UUIDString(),
                "name": domain.name(),
                "state": readable_state,
            }
            mapped_domains.append(mapped_domain)

        # Sort to ensure stable order
        return sorted(mapped_domains, key=lambda m: m["uuid"])

    def list_domain_interfaces(
        self, domain_name: str, source: AddressSource
    ) -> AddressList:
        """List all network interfaces of a domain."""
        domain = self._conn.lookupByName(domain_name)

        match source:
            case AddressSource.LEASE:
                s = libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE
            case AddressSource.AGENT:
                s = libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_AGENT
            case AddressSource.ARP:
                s = libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_ARP
            case _:
                raise AssertionError("Unknown address source: {}".format(source))

        interfaces = domain.interfaceAddresses(s, 0)

        result = []
        for name, props in interfaces.items():
            addresses = []
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

                address = {
                    "address": addr["addr"],
                    "prefix": addr["prefix"],
                    "type": addr_type,
                }
                addresses.append(address)

            interface = {
                "name": name,
                "hwaddr": props["hwaddr"],
                "addresses": sorted(addresses, key=lambda a: a["address"]),
            }
            result.append(interface)

        # Sort to ensure stable order
        return sorted(result, key=lambda i: i["hwaddr"])

    def ping_guest(self, domain_name: str) -> bool:
        domain = self._conn.lookupByName(domain_name)
        cmd = {"execute": "guest-ping"}
        json_cmd = json.dumps(cmd)
        try:
            libvirt_qemu.qemuAgentCommand(
                domain, json_cmd, libvirt_qemu.VIR_DOMAIN_QEMU_AGENT_COMMAND_DEFAULT, 0
            )
            return True
        except libvirt.libvirtError:
            return False

    def clone_domain(
        self, name: str, new_name: str, mode: CloneMode = CloneMode.COPY
    ) -> None:
        if not self._domain_exists(name):
            raise Exception

        if self._domain_exists(new_name):
            raise Exception

        # Only domains that are shut off can be cloned.
        if not self._domain_in_state(name, libvirt.VIR_DOMAIN_SHUTOFF):
            raise Exception

        domain_to_clone = self._conn.lookupByName(name)
        domain_xml = domain_to_clone.XMLDesc()
        config = ElementTree.fromstring(domain_xml)
        uuid_factory = LibvirtUUIDFactory(self._conn)
        mac_factory = LibvirtMACFactory(self._conn)

        op = CloneOperation(config, new_name, mode, uuid_factory, mac_factory)
        op.perform(self._conn)

    def list_volumes(self, pool_name: str) -> Iterable[VolumeDescriptor]:
        op = ListVolumesOperation()
        return op.perform(self._conn, pool_name)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()

    # TODO: Make public
    def _domain_exists(self, name: str) -> bool:
        """Returns `True` if a domain with the given name exists, `False` otherwise."""
        try:
            self._conn.lookupByName(name)
            return True
        except libvirt.libvirtError:
            return False

    # TODO: Make public
    def _domain_in_state(self, name: str, state: int) -> bool:
        try:
            domain = self._conn.lookupByName(name)
            (domain_state, _) = domain.state(0)
            # bool() to placate mypy because __eq__() can return NotImplemented.
            return bool(state == domain_state)
        except libvirt.libvirtError:
            return False


class MACFactory(abc.ABC):
    @abc.abstractmethod
    def create_from(self, mac_address: str) -> str: ...


class LibvirtMACFactory(MACFactory):
    _conn: virConnect
    _rnd: Random
    _attempts: int

    def __init__(self, conn: virConnect, rnd: random.Random = random.Random()):
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

        # TODO: Raise custom exception
        raise Exception

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
            root = ElementTree.fromstring(domain.XMLDesc(0))
            for mac_element in root.findall("devices/interface/mac"):
                if "address" not in mac_element.attrib:
                    continue

                if mac_element.attrib["address"] == mac_address:
                    return True

        return False


class UUIDFactory(abc.ABC):
    @abc.abstractmethod
    def create(self) -> UUID: ...


class LibvirtUUIDFactory(UUIDFactory):
    _conn: virConnect
    _rnd: Random
    _attempts: int

    def __init__(self, conn: virConnect, rnd: random.Random = random.Random()):
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

        # TODO: Raise custom exception
        raise Exception

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
            # https://bugzilla.redhat.com/show_bug.cgi?id=1324006). We leave it to libvirt to raise errors because libvirt
            # knows best, and it spares us to perform version checks, for example, "Raise exception if libvirt < X".
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
            CloneOperation._undefine_domain(conn, self._clone_name)

            for fw in self._firmware_to_clone:
                CloneOperation._delete_volume(conn, fw.clone_path)

            for volume in self._volumes_to_clone:
                CloneOperation._delete_volume(conn, volume.clone_path)

            raise

    @staticmethod
    def _copy_firmware(conn: virConnect, source_fw: SourceFirmware) -> None:
        volume_el = ElementTree.Element("volume")
        name_el = ElementTree.SubElement(volume_el, "name")
        name_el.text = source_fw.cloned_volume_name
        volume_xml = ElementTree.tostring(volume_el, encoding="unicode")

        pool = conn.storagePoolLookupByTargetPath(source_fw.pool_path)
        fw_to_copy = conn.storageVolLookupByPath(source_fw.source_path)
        pool.createXMLFrom(volume_xml, fw_to_copy, 0)

    @staticmethod
    def _copy_volume(
        conn: virConnect, source_volume: SourceVolume, reflink: bool = False
    ) -> None:
        volume_el = ElementTree.Element("volume")
        name_el = ElementTree.SubElement(volume_el, "name")
        name_el.text = source_volume.cloned_volume_name
        target_el = ElementTree.SubElement(volume_el, "target")
        ElementTree.SubElement(target_el, "format", {"type": source_volume.source_type})
        volume_xml = ElementTree.tostring(volume_el, encoding="unicode")

        create_flags = 0
        if reflink:
            create_flags |= libvirt.VIR_STORAGE_VOL_CREATE_REFLINK

        pool = conn.storagePoolLookupByTargetPath(source_volume.pool_path)
        volume_to_copy = conn.storageVolLookupByPath(source_volume.source_path)
        pool.createXMLFrom(volume_xml, volume_to_copy, create_flags)

    @staticmethod
    def _link_volume(conn: virConnect, source_volume: SourceVolume) -> None:
        volume_el = ElementTree.Element("volume")
        name_el = ElementTree.SubElement(volume_el, "name")
        name_el.text = source_volume.cloned_volume_name
        target_el = ElementTree.SubElement(volume_el, "target")
        ElementTree.SubElement(target_el, "format", {"type": "qcow2"})
        backing_store_el = ElementTree.SubElement(volume_el, "backingStore")
        path_el = ElementTree.SubElement(backing_store_el, "path")
        path_el.text = source_volume.source_path
        ElementTree.SubElement(
            backing_store_el, "format", {"type": source_volume.source_type}
        )
        volume_xml = ElementTree.tostring(volume_el, encoding="unicode")

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


class ListVolumesOperation:
    def perform(self, conn: virConnect, pool_name: str) -> Iterable[VolumeDescriptor]:
        volumes = []
        pool = conn.storagePoolLookupByName(pool_name)
        for volume in pool.listAllVolumes(0):
            # Schema: https://gitlab.com/libvirt/libvirt/-/blob/master/src/conf/schemas/storagevol.rng
            volume_desc = volume.XMLDesc()
            volume_tag = ElementTree.fromstring(volume_desc)

            # Attribute type is optional
            volume_type = volume_tag.get("type")

            # target/format is optional
            format_type = None
            target_format_tag = volume_tag.find("target/format")
            if target_format_tag is not None:
                format_type = target_format_tag.get("type")

            volume_props: VolumeDescriptor = {
                "name": volume.name(),
                "key": volume.key(),
                "capacity": self._extract_size("capacity", volume_tag),
                "allocation": self._extract_size("allocation", volume_tag),
                "physical": self._extract_size("physical", volume_tag),
                "type": volume_type,
                "target": {"path": volume.path(), "format_type": format_type},
                "backing_store": self._extract_backing_store(volume_tag),
            }

            volumes.append(volume_props)

        return sorted(volumes, key=lambda vol: vol["name"])

    def _extract_size(self, tag_name: str, volume_tag: Element) -> int | None:
        size_tag = volume_tag.find(tag_name)
        if size_tag is not None and size_tag.text is not None:
            unit = size_tag.get("unit")
            # Internally, libvirt operates on bytes. Therefore, we should never encounter any other unit.
            # https://gitlab.com/libvirt/libvirt/-/blob/master/include/libvirt/libvirt-storage.h#L248
            assert unit is None or unit == "bytes"

            # int in Python is only bound by available memory, see https://peps.python.org/pep-0237/
            return int(size_tag.text)

        return None

    def _extract_backing_store(
        self, volume_tag: Element
    ) -> BackingStoreDescriptor | None:
        bs_tag = volume_tag.find("backingStore")
        if bs_tag is None:
            return None

        backing_store = BackingStoreDescriptor(path=None, format_type=None)
        path_tag = bs_tag.find("path")
        if path_tag is not None:
            backing_store["path"] = path_tag.text

        format_tag = bs_tag.find("format")
        if format_tag is not None:
            backing_store["format_type"] = format_tag.get("type")

        return backing_store


def list_domains(args: argparse.Namespace) -> int:
    with Hypervisor(args.connection) as hypervisor:
        result = hypervisor.list_domains()
        print(json.dumps(result))
        return 0


def clone_domain(args: argparse.Namespace) -> int:
    match args.mode:
        case "copy":
            mode = CloneMode.COPY
        case "linked":
            mode = CloneMode.LINKED
        case "reflink":
            mode = CloneMode.REFLINK
        case _:
            # Argument choices not matching all CloneMode types is a programming error.
            raise AssertionError("Unknown clone mode: {}".format(args.mode))

    with Hypervisor(args.connection) as hypervisor:
        hypervisor.clone_domain(args.domain, args.newname, mode)
        return 0


def list_domain_interfaces(args: argparse.Namespace) -> int:
    match args.source:
        case "lease":
            source = AddressSource.LEASE
        case "agent":
            source = AddressSource.AGENT
        case "arp":
            source = AddressSource.ARP
        case _:
            # Argument choices not matching all AddressSource types is a programming error.
            raise AssertionError("Unknown address source: {}".format(args.source))

    with Hypervisor(args.connection) as hypervisor:
        result = hypervisor.list_domain_interfaces(args.domain, source)
        print(json.dumps(result))
        return 0


def ping_guest(args: argparse.Namespace) -> int:
    with Hypervisor(args.connection) as hypervisor:
        if hypervisor.ping_guest(args.domain):
            return 0
        else:
            return 1


def list_volumes(args: argparse.Namespace) -> int:
    with Hypervisor(args.connection) as hypervisor:
        result = hypervisor.list_volumes(args.pool)
        print(json.dumps(result))
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Automate libvirt.")
    p.add_argument(
        "-v",
        "--version",
        action="version",
        version=importlib.metadata.version("virtomate"),
    )
    p.add_argument("-c", "--connection", help="libvirt connection URI", default=None)
    sp = p.add_subparsers(title="Subcommands")

    # domain-list
    p_domain_list = sp.add_parser("domain-list", help="List all domains")
    p_domain_list.set_defaults(func=list_domains)

    # domain-clone
    p_domain_clone = sp.add_parser("domain-clone", help="clone a domain")
    p_domain_clone.add_argument(
        "domain",
        type=str,
        help="name of the domain to clone",
    )
    p_domain_clone.add_argument(
        "newname",
        type=str,
        help="name of the cloned domain",
    )
    p_domain_clone.add_argument(
        "--mode",
        choices=(
            "copy",
            "linked",
            "reflink",
        ),
        default="copy",
        help="how disks are cloned (default: %(default)s)",
    )
    p_domain_clone.set_defaults(func=clone_domain)

    # domain-iface-list
    p_domain_iface_list = sp.add_parser(
        "domain-iface-list", help="List network interfaces of a running domain"
    )
    p_domain_iface_list.add_argument("domain", type=str, help="Name of the domain")
    p_domain_iface_list.add_argument(
        "--source",
        choices=(
            "lease",
            "agent",
            "arp",
        ),
        default="lease",
        help="Source of the addresses (default: %(default)s)",
    )
    p_domain_iface_list.set_defaults(func=list_domain_interfaces)

    # guest-ping
    p_guest_ping = sp.add_parser("guest-ping", help="Ping the QEMU Guest Agent")
    p_guest_ping.add_argument(
        "domain",
        type=str,
        help="Name of the domain to ping",
    )
    p_guest_ping.set_defaults(func=ping_guest)

    # volume-list
    p_volume_list = sp.add_parser("volume-list", help="list volumes of a pool")
    p_volume_list.add_argument(
        "pool",
        type=str,
        help="name of the pool whose volumes should be listed",
    )
    p_volume_list.set_defaults(func=list_volumes)

    args = p.parse_args()
    status_code = args.func(args)

    # Ensure that all functions return a status code. This also helps mypy to narrow the type from Any.
    assert isinstance(status_code, int)

    return status_code
