from typing import Generator

import libvirt
import pytest

from tests.resources import fixture
from virtomate import Hypervisor, AddressSource


@pytest.fixture
def hypervisor() -> Generator[Hypervisor, None, None]:
    with Hypervisor("test:///default") as hypervisor:
        yield hypervisor


def test_list_domains(hypervisor: Hypervisor) -> None:
    conn = hypervisor.connection()

    assert hypervisor.list_domains() == [
        {
            "uuid": "6695eb01-f6a4-8304-79aa-97f2502e193f",
            "name": "test",
            "state": "running",
        }
    ]

    domain = conn.lookupByName("test")

    domain.suspend()
    assert hypervisor.list_domains() == [
        {
            "uuid": "6695eb01-f6a4-8304-79aa-97f2502e193f",
            "name": "test",
            "state": "paused",
        }
    ]

    domain.shutdown()
    assert hypervisor.list_domains() == [
        {
            "uuid": "6695eb01-f6a4-8304-79aa-97f2502e193f",
            "name": "test",
            "state": "shut-off",
        }
    ]

    domain.undefine()
    assert hypervisor.list_domains() == []

    conn.defineXML(fixture("simple-bios.xml"))
    conn.defineXML(fixture("simple-uefi.xml"))

    assert hypervisor.list_domains() == [
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


def test_list_domain_interfaces(hypervisor: Hypervisor) -> None:
    with pytest.raises(libvirt.libvirtError, match="Domain not found"):
        hypervisor.list_domain_interfaces("unknown", AddressSource.AGENT)

    # It makes no sense to test additional address sources because the mock driver always returns the same answer.
    assert hypervisor.list_domain_interfaces("test", AddressSource.LEASE) == [
        {
            "name": "testnet0",
            "hwaddr": "aa:bb:cc:dd:ee:ff",
            "addresses": [{"address": "192.168.122.3", "prefix": 24, "type": "IPv4"}],
        }
    ]

    conn = hypervisor.connection()
    domain = conn.lookupByName("test")
    domain.shutdown()

    with pytest.raises(libvirt.libvirtError, match="domain is not running"):
        hypervisor.list_domain_interfaces("test", AddressSource.AGENT)


def test_clone_domain(hypervisor: Hypervisor) -> None:
    assert hypervisor.list_domains() == [
        {
            "uuid": "6695eb01-f6a4-8304-79aa-97f2502e193f",
            "name": "test",
            "state": "running",
        }
    ]

    with pytest.raises(Exception):
        hypervisor.clone_domain("test", "my-clone")

    conn = hypervisor.connection()
    domain_test = conn.lookupByName("test")
    domain_test.shutdown()

    with pytest.raises(Exception):
        hypervisor.clone_domain("test", "test")

    with pytest.raises(Exception):
        hypervisor.clone_domain("does-not-exist", "my-clone")

    # Unfortunately, it is impossible to test the happy path with the test driver because it neither persists disks nor
    # does it implement all required libvirt functions.
