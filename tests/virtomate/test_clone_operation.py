from uuid import UUID
from xml.etree import ElementTree

from tests.resources import fixture, expectation
from virtomate import (
    CloneOperation,
    MACFactory,
    UUIDFactory,
    SourceVolume,
    CloneMode,
    SourceFirmware,
)


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
