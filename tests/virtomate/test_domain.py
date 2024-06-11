from random import Random
from uuid import UUID
from xml.etree import ElementTree

import pytest
from libvirt import virConnect

from tests.resources import fixture, expectation
from virtomate.domain import (
    list_domains,
    AddressSource,
    list_domain_interfaces,
    clone_domain,
    LibvirtMACFactory,
    LibvirtUUIDFactory,
    CloneMode,
    CloneOperation,
    SourceFirmware,
    SourceVolume,
    MACFactory,
    UUIDFactory,
    domain_exists,
)
from virtomate.error import NotFoundError, IllegalStateError


class TestListDomains:
    def test_list(self, test_connection: virConnect) -> None:
        assert list_domains(test_connection) == [
            {
                "uuid": "6695eb01-f6a4-8304-79aa-97f2502e193f",
                "name": "test",
                "state": "running",
            }
        ]

        domain = test_connection.lookupByName("test")

        domain.suspend()
        assert list_domains(test_connection) == [
            {
                "uuid": "6695eb01-f6a4-8304-79aa-97f2502e193f",
                "name": "test",
                "state": "paused",
            }
        ]

        domain.shutdown()
        assert list_domains(test_connection) == [
            {
                "uuid": "6695eb01-f6a4-8304-79aa-97f2502e193f",
                "name": "test",
                "state": "shut-off",
            }
        ]

        domain.undefine()
        assert list_domains(test_connection) == []

        test_connection.defineXML(fixture("simple-bios.xml"))
        test_connection.defineXML(fixture("simple-uefi.xml"))

        assert list_domains(test_connection) == [
            {
                "uuid": "d2ecf360-24a6-4952-95fb-68b99307d942",
                "name": "virtomate-simple-bios",
                "state": "shut-off",
            },
            {
                "uuid": "ef70b4c0-1773-44a3-9b95-f239ae97d9db",
                "name": "virtomate-simple-uefi",
                "state": "shut-off",
            },
        ]


class TestListDomainInterfaces:
    def test_error_if_domain_not_defined(self, test_connection: virConnect) -> None:
        with pytest.raises(NotFoundError, match="Domain 'unknown' does not exist"):
            list_domain_interfaces(test_connection, "unknown", AddressSource.AGENT)

    def test_source_lease(self, test_connection: virConnect) -> None:
        assert list_domain_interfaces(test_connection, "test", AddressSource.LEASE) == [
            {
                "name": "testnet0",
                "hwaddr": "aa:bb:cc:dd:ee:ff",
                "addresses": [
                    {"address": "192.168.122.3", "prefix": 24, "type": "IPv4"}
                ],
            }
        ]

    def test_source_agent(self, test_connection: virConnect) -> None:
        assert list_domain_interfaces(test_connection, "test", AddressSource.AGENT) == [
            {
                "name": "testnet0",
                "hwaddr": "aa:bb:cc:dd:ee:ff",
                "addresses": [
                    {"address": "192.168.122.3", "prefix": 24, "type": "IPv4"}
                ],
            }
        ]

    def test_source_arp(self, test_connection: virConnect) -> None:
        # The mock driver always returns the same answer, regardless of the source. Hence, the prefix is wrong. It
        # should be 0 because ARP does not know anything about prefixes.
        assert list_domain_interfaces(test_connection, "test", AddressSource.ARP) == [
            {
                "name": "testnet0",
                "hwaddr": "aa:bb:cc:dd:ee:ff",
                "addresses": [
                    {"address": "192.168.122.3", "prefix": 24, "type": "IPv4"}
                ],
            }
        ]

    def test_error_domain_not_running(self, test_connection: virConnect) -> None:
        domain = test_connection.lookupByName("test")
        domain.shutdown()

        with pytest.raises(IllegalStateError, match="Domain 'test' is not running"):
            list_domain_interfaces(test_connection, "test", AddressSource.AGENT)


class TestCloneDomain:
    # Unfortunately, it is impossible to test the happy path with the test driver because it does not implement all
    # required libvirt functions.

    def test_error_if_domain_running(self, test_connection: virConnect) -> None:
        assert list_domains(test_connection) == [
            {
                "uuid": "6695eb01-f6a4-8304-79aa-97f2502e193f",
                "name": "test",
                "state": "running",
            }
        ]

        with pytest.raises(Exception):
            clone_domain(test_connection, "test", "my-clone")

    def test_error_if_new_name_identical(self, test_connection: virConnect) -> None:
        domain_test = test_connection.lookupByName("test")
        domain_test.shutdown()

        with pytest.raises(Exception):
            clone_domain(test_connection, "test", "test")

    def test_error_if_source_undefined(self, test_connection: virConnect) -> None:
        with pytest.raises(Exception):
            clone_domain(test_connection, "does-not-exist", "my-clone")


class TestLibvirtUUIDFactory:
    def test_create(self, test_connection: virConnect) -> None:
        rnd = Random()
        rnd.seed(37)

        uuid_factory = LibvirtUUIDFactory(test_connection, rnd=rnd)

        assert uuid_factory.create() == UUID(hex="ef70b4c0-1773-44a3-9b95-f239ae97d9db")
        assert uuid_factory.create() == UUID(hex="bf2eb110-d788-4003-aa59-ce1e9e293641")

    def test_create_collision_avoidance(self, test_connection: virConnect) -> None:
        rnd = Random()
        rnd.seed(37)

        test_connection.defineXML(fixture("simple-uefi.xml"))
        uuid_factory = LibvirtUUIDFactory(test_connection, rnd=rnd)

        assert uuid_factory.create() == UUID(hex="bf2eb110-d788-4003-aa59-ce1e9e293641")
        assert uuid_factory._attempts == 2


class TestLibvirtMACFactory:
    def test_create_from(self, test_connection: virConnect) -> None:
        rnd = Random()
        rnd.seed(37)

        mac_factory = LibvirtMACFactory(test_connection, rnd=rnd)

        assert mac_factory.create_from("52:54:00:4c:4e:25") == "52:54:00:2e:12:bd"
        assert mac_factory.create_from("52:54:00:4c:4e:25") == "52:54:00:e0:37:e9"
        assert mac_factory.create_from("00:00:00:00:00:00") == "00:00:00:90:c1:d8"

        with pytest.raises(ValueError) as excinfo:
            mac_factory.create_from("_")

        assert str(excinfo.value) == "Invalid MAC address: _"

        with pytest.raises(ValueError) as excinfo:
            mac_factory.create_from("z0:00:00:00:00:00")

        assert str(excinfo.value) == "Invalid MAC address: z0:00:00:00:00:00"

    def test_create_from_collision_avoidance(self, test_connection: virConnect) -> None:
        rnd = Random()
        rnd.seed(37)

        test_connection.defineXML(fixture("simple-uefi.xml"))
        mac_factory = LibvirtMACFactory(test_connection, rnd=rnd)

        assert mac_factory.create_from("52:54:00:4c:4e:25") == "52:54:00:e0:37:e9"
        assert mac_factory._attempts == 2


class FixedUUIDFactory(UUIDFactory):
    _fixed_uuid: UUID

    def __init__(self, fixed_uuid: UUID):
        self._fixed_uuid = fixed_uuid

    def create(self) -> UUID:
        return self._fixed_uuid


class FixedMACFactory(MACFactory):
    _fixed_mac_address: str

    def __init__(self, fixed_mac_address: str):
        self._fixed_mac_address = fixed_mac_address

    def create_from(self, _mac_address: str) -> str:
        return self._fixed_mac_address


class TestSourceFirmware:
    def test_pool_path(self) -> None:
        source_fw = SourceFirmware("/somewhere/nvram/OVMF_VARS.fd", "my-clone")
        assert source_fw.pool_path == "/somewhere/nvram"

    def test_cloned_volume_name(self) -> None:
        source_fw = SourceFirmware("/somewhere/nvram/OVMF_VARS.fd", "my-clone")
        assert source_fw.cloned_volume_name == "my-clone-OVMF_VARS.fd"

    def test_clone_path(self) -> None:
        source_fw = SourceFirmware("/somewhere/nvram/OVMF_VARS.fd", "my-clone")
        assert source_fw.clone_path == "/somewhere/nvram/my-clone-OVMF_VARS.fd"


class TestSourceVolume:
    def test_pool_path(self) -> None:
        source_volume = SourceVolume("/somewhere/images/image", "qcow2", "my-clone")
        assert source_volume.pool_path == "/somewhere/images"

    def test_cloned_volume_name(self) -> None:
        source_volume = SourceVolume("/somewhere/images/image", "qcow2", "my-clone")
        assert source_volume.cloned_volume_name == "my-clone-image"

    def test_clone_path(self) -> None:
        source_volume = SourceVolume("/somewhere/images/image", "qcow2", "my-clone")
        assert source_volume.clone_path == "/somewhere/images/my-clone-image"


class TestCloneOperation:
    def test_clone_config_simple_bios_copy(self) -> None:
        name = "virtomate-clone-copy"
        config = ElementTree.fromstring(fixture("simple-bios.xml"))
        clone_config = ElementTree.fromstring(expectation("clone-copy-simple-bios.xml"))
        mac_factory = FixedMACFactory("52:54:00:4c:4e:25")
        uuid_factory = FixedUUIDFactory(
            UUID(hex="e5a8d70e-0cb5-49af-bf66-59c13180e344")
        )

        op = CloneOperation(config, name, CloneMode.COPY, uuid_factory, mac_factory)

        assert op.clone_config() == ElementTree.tostring(
            clone_config, encoding="unicode"
        )

    def test_clone_config_simple_bios_linked(self) -> None:
        name = "virtomate-clone-linked"
        config = ElementTree.fromstring(fixture("simple-bios-raw.xml"))
        clone_config = ElementTree.fromstring(
            expectation("clone-linked-simple-bios-raw.xml")
        )
        mac_factory = FixedMACFactory("52:54:00:9a:e6:0e")
        uuid_factory = FixedUUIDFactory(
            UUID(hex="ee309161-8e9b-4227-a0b0-f430f82d1437")
        )

        op = CloneOperation(config, name, CloneMode.LINKED, uuid_factory, mac_factory)

        assert op.clone_config() == ElementTree.tostring(
            clone_config, encoding="unicode"
        )

    def test_clone_config_simple_bios_reflink(self) -> None:
        name = "virtomate-clone-reflink"
        config = ElementTree.fromstring(fixture("simple-bios-raw.xml"))
        clone_config = ElementTree.fromstring(
            expectation("clone-reflink-simple-bios-raw.xml")
        )
        mac_factory = FixedMACFactory("52:54:00:ce:35:01")
        uuid_factory = FixedUUIDFactory(
            UUID(hex="0496dcd3-4c1f-4508-a3f3-a0d2be788848")
        )

        op = CloneOperation(config, name, CloneMode.REFLINK, uuid_factory, mac_factory)

        assert op.clone_config() == ElementTree.tostring(
            clone_config, encoding="unicode"
        )

    def test_clone_config_simple_uefi_copy(self) -> None:
        name = "virtomate-clone-copy"
        config = ElementTree.fromstring(fixture("simple-uefi.xml"))
        clone_config = ElementTree.fromstring(expectation("clone-copy-simple-uefi.xml"))
        mac_factory = FixedMACFactory("52:54:00:6c:91:a2")
        uuid_factory = FixedUUIDFactory(
            UUID(hex="70d6b969-6a1f-47f8-ab69-38cc33d000ea")
        )

        op = CloneOperation(config, name, CloneMode.COPY, uuid_factory, mac_factory)

        assert op.clone_config() == ElementTree.tostring(
            clone_config, encoding="unicode"
        )


class TestDomainExists:
    def test(self, test_connection: virConnect) -> None:
        assert domain_exists(test_connection, "test") is True
        assert domain_exists(test_connection, "does-not-exist") is False
