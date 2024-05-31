import json
import logging
import os
import subprocess
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import pytest
from tenacity import stop_after_attempt, wait_fixed, retry
import importlib.metadata
from tests.matchers import ANY_STR, ANY_INT

logger = logging.getLogger(__name__)

if "LIBVIRT_DEFAULT_URI" not in os.environ:
    logger.warning(
        "Environment variable LIBVIRT_DEFAULT_URI undefined, using qemu:///system"
    )
    os.environ["LIBVIRT_DEFAULT_URI"] = "qemu:///system"

pytestmark = [
    pytest.mark.functional,
    pytest.mark.skipif(
        os.environ["LIBVIRT_DEFAULT_URI"].startswith("test://"),
        reason="libvirt test driver is not supported",
    ),
]


@retry(stop=stop_after_attempt(30), wait=wait_fixed(1))
def wait_until_running(domain: str) -> None:
    """Waits until the QEMU Guest Agent of the given domain becomes responsive."""
    args = ["virtomate", "guest-ping", domain]
    subprocess.run(args, check=True)


@retry(stop=stop_after_attempt(30), wait=wait_fixed(1))
def wait_for_network(domain: str) -> None:
    """Waits until the given domain is connected a network."""
    # Use ARP because this is the method that takes the longest for changes to become visible.
    args = ["virtomate", "domain-iface-list", "--source", "arp", domain]
    result = subprocess.run(args, check=True, capture_output=True)
    assert len(json.loads(result.stdout)) > 0


def start_domain(name: str) -> None:
    cmd = ["virsh", "start", name]
    result = subprocess.run(cmd)
    assert result.returncode == 0, "Could not start {}".format(name)


def domain_exists(name: str) -> bool:
    cmd = ["virtomate", "domain-list"]
    result = subprocess.run(cmd, check=True, capture_output=True)
    domains = json.loads(result.stdout)

    for domain in domains:
        if domain["name"] == name:
            return True

    return False


def read_volume_xml(pool: str, volume: str) -> Element:
    cmd = ["virsh", "vol-dumpxml", "--pool", pool, volume]
    result = subprocess.run(cmd, check=True, capture_output=True)
    return ElementTree.fromstring(result.stdout)


class TestVersionOption:
    def test_short_form(self, automatic_cleanup: None) -> None:
        cmd = ["virtomate", "-v"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "version failed unexpectedly"
        assert result.stdout.strip() != ""
        assert result.stdout.strip() == importlib.metadata.version("virtomate")
        assert result.stderr == ""

    def test_long_form(self, automatic_cleanup: None) -> None:
        cmd = ["virtomate", "--version"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "version failed unexpectedly"
        assert result.stdout.strip() != ""
        assert result.stdout.strip() == importlib.metadata.version("virtomate")
        assert result.stderr == ""


class TestConnectionOption:
    def test_default(self, simple_bios_machine: str, automatic_cleanup: None) -> None:
        cmd = ["virtomate", "domain-list"]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"
        assert result.stderr == b""

        domains = json.loads(result.stdout)

        machine = next(d for d in domains if d["name"] == simple_bios_machine)
        assert machine == {
            "uuid": "d2ecf360-24a6-4952-95fb-68b99307d942",
            "name": simple_bios_machine,
            "state": "shut-off",
        }

    def test_short_form(
        self, simple_bios_machine: str, automatic_cleanup: None
    ) -> None:
        cmd = ["virtomate", "-c", "test:///default", "domain-list"]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"
        assert result.stderr == b""

        domains = json.loads(result.stdout)

        with pytest.raises(StopIteration):
            next(d for d in domains if d["name"] == simple_bios_machine)

    def test_long_form(self, simple_bios_machine: str, automatic_cleanup: None) -> None:
        cmd = ["virtomate", "--connection", "test:///default", "domain-list"]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"
        assert result.stderr == b""

        domains = json.loads(result.stdout)

        with pytest.raises(StopIteration):
            next(d for d in domains if d["name"] == simple_bios_machine)


class TestDomainList:
    def test_list(
        self,
        simple_bios_machine: str,
        simple_uefi_machine: str,
        automatic_cleanup: None,
    ) -> None:
        cmd = ["virtomate", "domain-list"]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"
        assert result.stderr == b""

        domains = json.loads(result.stdout)

        # There might be pre-existing domains.
        assert len(domains) >= 2

        machine = next(d for d in domains if d["name"] == simple_bios_machine)
        assert machine == {
            "uuid": "d2ecf360-24a6-4952-95fb-68b99307d942",
            "name": simple_bios_machine,
            "state": "shut-off",
        }

        machine = next(d for d in domains if d["name"] == simple_uefi_machine)
        assert machine == {
            "uuid": "ef70b4c0-1773-44a3-9b95-f239ae97d9db",
            "name": simple_uefi_machine,
            "state": "shut-off",
        }


class TestDomainIfaceList:
    def test_error_when_domain_off(
        self, simple_bios_machine: str, automatic_cleanup: None
    ) -> None:
        cmd = ["virtomate", "domain-iface-list", simple_bios_machine]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 1, "domain-iface-list succeeded unexpectedly"
        assert result.stdout == b""
        # TODO: Expect proper JSON error response
        assert result.stderr != b""

    def test_all_sources(
        self, simple_bios_machine: str, automatic_cleanup: None
    ) -> None:
        start_domain(simple_bios_machine)
        wait_until_running(simple_bios_machine)
        wait_for_network(simple_bios_machine)

        # Default is lease (same as of `virsh domifaddr`)
        cmd = ["virtomate", "domain-iface-list", simple_bios_machine]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "domain-iface-list failed unexpectedly"
        assert result.stderr == b""

        # As of libvirt 10.1, there can be multiple leases per hardware address if the same machine has been defined and
        # undefined multiple times. This is a problem of libvirt as shown by `virsh net-dhcp-leases default`.
        interfaces = json.loads(result.stdout)
        assert interfaces == [
            {
                "name": ANY_STR,
                "hwaddr": "52:54:00:3d:0e:bb",
                "addresses": [{"address": ANY_STR, "prefix": ANY_INT, "type": "IPv4"}],
            },
        ]

        # Lease (explicit)
        cmd = [
            "virtomate",
            "domain-iface-list",
            "--source",
            "lease",
            simple_bios_machine,
        ]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "domain-iface-list failed unexpectedly"
        assert result.stderr == b""

        interfaces = json.loads(result.stdout)
        assert interfaces == [
            {
                "name": ANY_STR,
                "hwaddr": "52:54:00:3d:0e:bb",
                "addresses": [{"address": ANY_STR, "prefix": ANY_INT, "type": "IPv4"}],
            },
        ]

        # Agent
        cmd = [
            "virtomate",
            "domain-iface-list",
            "--source",
            "agent",
            simple_bios_machine,
        ]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "domain-iface-list failed unexpectedly"
        assert result.stderr == b""

        interfaces = json.loads(result.stdout)
        assert interfaces == [
            {
                "name": "lo",
                "hwaddr": "00:00:00:00:00:00",
                "addresses": [
                    {"address": "127.0.0.1", "prefix": 8, "type": "IPv4"},
                    {"address": "::1", "prefix": 128, "type": "IPv6"},
                ],
            },
            {
                "name": ANY_STR,
                "hwaddr": "52:54:00:3d:0e:bb",
                "addresses": [
                    {"address": ANY_STR, "prefix": ANY_INT, "type": "IPv4"},
                    {"address": ANY_STR, "prefix": ANY_INT, "type": "IPv6"},
                ],
            },
        ]

        # ARP table
        cmd = ["virtomate", "domain-iface-list", "--source", "arp", simple_bios_machine]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "domain-iface-list failed unexpectedly"
        assert result.stderr == b""

        interfaces = json.loads(result.stdout)
        assert interfaces == [
            {
                "name": ANY_STR,
                "hwaddr": "52:54:00:3d:0e:bb",
                "addresses": [{"address": ANY_STR, "prefix": 0, "type": "IPv4"}],
            },
        ]


class TestDomainClone:
    def test_copy(self, simple_bios_machine: str, automatic_cleanup: None) -> None:
        clone_name = "virtomate-clone-copy"

        cmd = ["virtomate", "domain-clone", simple_bios_machine, clone_name]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-clone failed unexpectedly"
        assert result.stdout == ""
        assert result.stderr == ""

        volume_el = read_volume_xml(
            "default", "virtomate-clone-copy-virtomate-simple-bios"
        )
        format_el = volume_el.find("target/format")
        assert format_el is not None
        assert format_el.attrib["type"] == "qcow2"
        assert volume_el.find("backingStore") is None

        start_domain(clone_name)
        wait_until_running(clone_name)

    def test_linked_with_qcow2_backing_store(
        self, simple_bios_machine: str, automatic_cleanup: None
    ) -> None:
        clone_name = "virtomate-clone-linked"

        cmd = [
            "virtomate",
            "domain-clone",
            "--mode",
            "linked",
            simple_bios_machine,
            clone_name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-clone failed unexpectedly"
        assert result.stdout == ""
        assert result.stderr == ""

        volume_el = read_volume_xml(
            "default", "virtomate-clone-linked-virtomate-simple-bios"
        )
        format_el = volume_el.find("target/format")
        bs_path_el = volume_el.find("backingStore/path")
        bs_format_el = volume_el.find("backingStore/format")

        assert format_el is not None
        assert format_el.attrib["type"] == "qcow2"
        assert bs_path_el is not None
        assert bs_path_el.text == "/var/lib/libvirt/images/virtomate-simple-bios"
        assert bs_format_el is not None
        assert bs_format_el.attrib["type"] == "qcow2"

        start_domain(clone_name)
        wait_until_running(clone_name)

    def test_linked_with_raw_backing_store(
        self, simple_bios_raw_machine: str, automatic_cleanup: None
    ) -> None:
        clone_name = "virtomate-clone-linked"

        cmd = [
            "virtomate",
            "domain-clone",
            "--mode",
            "linked",
            simple_bios_raw_machine,
            clone_name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-clone failed unexpectedly"
        assert result.stdout == ""
        assert result.stderr == ""

        volume_el = read_volume_xml(
            "default", "virtomate-clone-linked-virtomate-simple-bios-raw"
        )
        format_el = volume_el.find("target/format")
        bs_path_el = volume_el.find("backingStore/path")
        bs_format_el = volume_el.find("backingStore/format")

        assert format_el is not None
        assert format_el.attrib["type"] == "qcow2"
        assert bs_path_el is not None
        assert bs_path_el.text == "/var/lib/libvirt/images/virtomate-simple-bios-raw"
        assert bs_format_el is not None
        assert bs_format_el.attrib["type"] == "raw"

        start_domain(clone_name)
        wait_until_running(clone_name)

    def test_linked_with_copied_firmware(
        self, simple_uefi_machine: str, automatic_cleanup: None
    ) -> None:
        clone_name = "virtomate-clone-linked"

        cmd = [
            "virtomate",
            "domain-clone",
            "--mode",
            "linked",
            simple_uefi_machine,
            clone_name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-clone failed unexpectedly"
        assert result.stdout == ""
        assert result.stderr == ""

        volume_el = read_volume_xml(
            "nvram", "virtomate-clone-linked-virtomate-simple-uefi-efivars.fd"
        )
        format_el = volume_el.find("target/format")
        assert format_el is not None
        assert format_el.attrib["type"] == "raw"
        assert volume_el.find("backingStore") is None

        volume_el = read_volume_xml(
            "default", "virtomate-clone-linked-virtomate-simple-uefi"
        )
        format_el = volume_el.find("target/format")
        bs_path_el = volume_el.find("backingStore/path")
        bs_format_el = volume_el.find("backingStore/format")

        assert format_el is not None
        assert format_el.attrib["type"] == "qcow2"
        assert bs_path_el is not None
        assert bs_path_el.text == "/var/lib/libvirt/images/virtomate-simple-uefi"
        assert bs_format_el is not None
        assert bs_format_el.attrib["type"] == "qcow2"

        start_domain(clone_name)
        wait_until_running(clone_name)

    def test_reflink_copy(
        self, simple_bios_raw_machine: str, automatic_cleanup: None
    ) -> None:
        clone_name = "virtomate-clone-reflink"

        cmd = [
            "virtomate",
            "domain-clone",
            "--mode",
            "reflink",
            simple_bios_raw_machine,
            clone_name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-clone failed unexpectedly"
        assert result.stdout == ""
        assert result.stderr == ""

        # Unfortunately, there is no tool that can tell apart a full from a shallow copy.
        volume_el = read_volume_xml(
            "default", "virtomate-clone-reflink-virtomate-simple-bios-raw"
        )
        format_el = volume_el.find("target/format")
        assert format_el is not None
        assert format_el.attrib["type"] == "raw"
        assert volume_el.find("backingStore") is None

        start_domain(clone_name)
        wait_until_running(clone_name)


class TestGuestPing:
    def test_error_unknown_machine(
        self, simple_bios_machine: str, automatic_cleanup: None
    ) -> None:
        cmd = ["virtomate", "guest-ping", "does-not-exist"]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 1, "guest-ping succeeded unexpectedly"
        assert result.stdout == b""
        # TODO: Expect proper JSON error response
        assert result.stderr != b""

    def test_error_when_domain_off(
        self, simple_bios_machine: str, automatic_cleanup: None
    ) -> None:
        cmd = ["virtomate", "guest-ping", simple_bios_machine]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 1, "guest-ping succeeded unexpectedly"
        assert result.stdout == b""
        # No error because the return code already indicates that the guest could not be reached.
        assert result.stderr == b""

    def test_guest_ping(
        self, simple_bios_machine: str, automatic_cleanup: None
    ) -> None:
        start_domain(simple_bios_machine)
        wait_until_running(simple_bios_machine)

        cmd = ["virtomate", "guest-ping", simple_bios_machine]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "Could not ping {}".format(simple_bios_machine)
        assert result.stdout == b""
        assert result.stderr == b""
