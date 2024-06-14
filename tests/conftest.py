from collections.abc import Generator

import libvirt
from libvirt import virConnect
import pytest

from tests.resources import fixture
from virtomate import connect


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--functional", action="store_true", default=False, help="run functional tests"
    )
    parser.addoption(
        "--reflink",
        action="store_true",
        default=False,
        help="run tests that require reflink support",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "functional: mark test as functional test")
    config.addinivalue_line(
        "markers", "reflink: mark test as requiring reflink (Btrfs, XFS) support"
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    skip_functional = pytest.mark.skip(reason="needs --functional to run")
    for item in items:
        if "functional" in item.keywords and not config.getoption("--functional"):
            item.add_marker(skip_functional)

    skip_reflink = pytest.mark.skip(reason="needs --reflink to run")
    for item in items:
        if "reflink" in item.keywords and not config.getoption("--reflink"):
            item.add_marker(skip_reflink)


@pytest.fixture
def test_connection() -> Generator[virConnect, None, None]:
    with connect("test:///default") as conn:
        yield conn


@pytest.fixture
def conn_for_function() -> Generator[virConnect, None, None]:
    with connect() as conn:
        yield conn


@pytest.fixture(scope="class")
def conn_for_class() -> Generator[virConnect, None, None]:
    with connect() as conn:
        yield conn


def _clean_up(conn: virConnect) -> None:
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


def _simple_bios_vm(conn: virConnect) -> str:
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
    pool_default = conn.storagePoolLookupByName("default")
    pool_default.createXML(vol_xml, 0)
    conn.defineXML(fixture("simple-bios.xml"))

    return "virtomate-simple-bios"


@pytest.fixture
def simple_bios_vm(conn_for_function: virConnect, after_function_cleanup: None) -> str:
    return _simple_bios_vm(conn_for_function)


@pytest.fixture(scope="class")
def running_vm_for_class(conn_for_class: virConnect, after_class_cleanup: None) -> str:
    domain_name = _simple_bios_vm(conn_for_class)
    domain = conn_for_class.lookupByName(domain_name)
    domain.create()
    return domain_name


def _simple_uefi_vm(conn: virConnect) -> str:
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

    pool_default = conn.storagePoolLookupByName("default")
    pool_default.createXML(vol_xml, 0)

    pool_nvram = conn.storagePoolLookupByName("nvram")
    nvram_vol = conn.storageVolLookupByPath(
        "/var/lib/libvirt/virtomate/simple-uefi-efivars.fd"
    )
    pool_nvram.createXMLFrom(nvram_xml, nvram_vol, 0)

    conn.defineXML(fixture("simple-uefi.xml"))

    return "virtomate-simple-uefi"


@pytest.fixture
def simple_uefi_vm(conn_for_function: virConnect, after_function_cleanup: None) -> str:
    return _simple_uefi_vm(conn_for_function)


def _simple_bios_raw_vm(conn: virConnect) -> str:
    vol_xml = """
        <volume>
            <name>virtomate-simple-bios-raw</name>
            <target>
                <format type='raw'/>
            </target>
        </volume>
        """

    pool_virtomate = conn.storagePoolLookupByName("virtomate")
    vol_to_clone = pool_virtomate.storageVolLookupByName("simple-bios")

    pool_default = conn.storagePoolLookupByName("default")
    pool_default.createXMLFrom(vol_xml, vol_to_clone, 0)
    conn.defineXML(fixture("simple-bios-raw.xml"))

    return "virtomate-simple-bios-raw"


@pytest.fixture
def simple_bios_raw_vm(
    conn_for_function: virConnect, after_function_cleanup: None
) -> str:
    return _simple_bios_raw_vm(conn_for_function)


@pytest.fixture
def after_function_cleanup(
    conn_for_function: virConnect,
) -> Generator[None, None, None]:
    yield
    _clean_up(conn_for_function)


@pytest.fixture(scope="class")
def after_class_cleanup(conn_for_class: virConnect) -> Generator[None, None, None]:
    yield
    _clean_up(conn_for_class)
