from typing import Generator, List

import libvirt
import pytest

from tests.resources import resource_content

AutomaticCleanup = Generator[None, None, None]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--functional", action="store_true", default=False, help="run functional tests"
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "functional: mark test as functional test")


def pytest_collection_modifyitems(
    config: pytest.Config, items: List[pytest.Item]
) -> None:
    if config.getoption("--functional"):
        return

    skip_functional = pytest.mark.skip(reason="needs --functional to run")
    for item in items:
        if "functional" in item.keywords:
            item.add_marker(skip_functional)


@pytest.fixture
def simple_bios_machine() -> str:
    vol_xml = """
    <volume>
        <name>virtomate-simple-bios</name>
        <target>
            <format type='qcow2'/>
        </target>
        <backingStore>
            <path>/var/lib/libvirt/virtomate/simple-bios</path>
            <format type='qcow2'/>
        </backingStore>
    </volume>
    """

    conn = libvirt.open()
    try:
        pool_default = conn.storagePoolLookupByName("default")
        pool_default.createXML(vol_xml, 0)
        conn.defineXML(resource_content("simple-bios.xml"))
    finally:
        if conn is not None:
            conn.close()

    return "virtomate-simple-bios"


@pytest.fixture
def simple_uefi_machine() -> str:
    vol_xml = """
    <volume>
        <name>virtomate-simple-uefi</name>
        <target>
            <format type='qcow2'/>
        </target>
        <backingStore>
            <path>/var/lib/libvirt/virtomate/simple-uefi</path>
            <format type='qcow2'/>
        </backingStore>
    </volume>
    """

    nvram_xml = """
    <volume>
        <name>virtomate-simple-uefi-efivars.fd</name>
        <target>
            <format type='raw'/>
        </target>
    </volume>
    """

    conn = libvirt.open()
    try:
        pool_default = conn.storagePoolLookupByName("default")
        pool_default.createXML(vol_xml, 0)

        pool_nvram = conn.storagePoolLookupByName("nvram")
        nvram_vol = conn.storageVolLookupByPath(
            "/var/lib/libvirt/virtomate/simple-uefi-efivars.fd"
        )
        pool_nvram.createXMLFrom(nvram_xml, nvram_vol, 0)

        conn.defineXML(resource_content("simple-uefi.xml"))
    finally:
        if conn is not None:
            conn.close()

    return "virtomate-simple-uefi"


@pytest.fixture
def automatic_cleanup() -> AutomaticCleanup:
    """Pytest fixture that removes all QEMU virtual machines and disks from the pools `default` and `nvram` prefixed
    with `virtomate` after a test has completed.
    """
    yield

    conn = libvirt.open()
    try:
        for name in ["default", "nvram"]:
            pool = conn.storagePoolLookupByName(name)
            for volume in pool.listAllVolumes():
                if not volume.name().startswith("virtomate-"):
                    continue

                volume.delete(0)

        domains = conn.listAllDomains()
        for domain in domains:
            if not domain.name().startswith("virtomate-"):
                continue

            (state, _) = domain.state()
            if state == libvirt.VIR_DOMAIN_RUNNING:
                domain.destroy()

            flags = 0
            flags |= libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE
            flags |= libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA
            flags |= libvirt.VIR_DOMAIN_UNDEFINE_NVRAM
            flags |= libvirt.VIR_DOMAIN_UNDEFINE_CHECKPOINTS_METADATA
            flags |= libvirt.VIR_DOMAIN_UNDEFINE_TPM
            domain.undefineFlags(flags)
    finally:
        if conn is not None:
            conn.close()
