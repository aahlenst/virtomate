import libvirt
import pytest

from tests.resources import resource_content
from virtomate import Hypervisor, AddressSource


def test_list_domains() -> None:
    hypervisor = Hypervisor("test:///default")
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

    conn.defineXML(resource_content("simple-bios.xml"))
    conn.defineXML(resource_content("simple-uefi.xml"))

    assert hypervisor.list_domains() == [
        {
            "uuid": "6fc06a10-3c15-4fd5-bc16-495e11e1083a",
            "name": "virtomate-simple-uefi",
            "state": "shut-off",
        },
        {
            "uuid": "d2ecf360-24a6-4952-95fb-68b99307d942",
            "name": "virtomate-simple-bios",
            "state": "shut-off",
        },
    ]


def test_list_domain_interfaces() -> None:
    hypervisor = Hypervisor("test:///default")

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
