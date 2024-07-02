import json
import logging
import os
import pathlib
import random
import string
import subprocess
from collections.abc import Sequence
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import pytest
from tenacity import wait_fixed, retry, Retrying, stop_after_delay
import importlib.metadata
from tests.matchers import ANY_STR, ANY_INT
from virtomate.domain import DomainDescriptor
from virtomate.pool import PoolDescriptor
from virtomate.volume import VolumeDescriptor

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

BOOT_TIMEOUT = 60
"""For how many seconds to wait for a guest to boot."""

NETWORK_TIMEOUT = 30
"""For how many seconds to wait for a guest to become online."""


@retry(stop=stop_after_delay(BOOT_TIMEOUT), wait=wait_fixed(1))
def wait_until_running(domain: str) -> None:
    """Waits until the QEMU Guest Agent of the given domain becomes responsive."""
    args = ["virtomate", "guest-ping", domain]
    subprocess.run(args, check=True)


@retry(stop=stop_after_delay(NETWORK_TIMEOUT), wait=wait_fixed(1))
def wait_for_network(domain: str) -> None:
    """Waits until the given domain is connected a network."""
    # Use ARP because this is the method that takes the longest for changes to become visible.
    args = ["virtomate", "domain-iface-list", "--source", "arp", domain]
    result = subprocess.run(args, check=True, capture_output=True)
    assert len(json.loads(result.stdout)) > 0


def start_domain(name: str) -> None:
    cmd = ["virsh", "start", name]
    result = subprocess.run(cmd)
    assert result.returncode == 0, f"Could not start {name}"


def read_volume_xml(pool: str, volume: str) -> Element:
    cmd = ["virsh", "vol-dumpxml", "--pool", pool, volume]
    result = subprocess.run(cmd, check=True, capture_output=True)
    return ElementTree.fromstring(result.stdout)


def list_virtomate_domains() -> Sequence[DomainDescriptor]:
    cmd = ["virtomate", "domain-list"]
    result = subprocess.run(cmd, check=True, capture_output=True)
    domains: Sequence[DomainDescriptor] = json.loads(result.stdout)
    return [d for d in domains if d["name"].startswith("virtomate")]


def list_virtomate_volumes(pool: str) -> Sequence[VolumeDescriptor]:
    cmd = ["virtomate", "volume-list", pool]
    result = subprocess.run(cmd, check=True, text=True, capture_output=True)
    volumes: Sequence[VolumeDescriptor] = json.loads(result.stdout)
    return [v for v in volumes if v["name"].startswith("virtomate")]


class TestHelp:
    def test_short_form(self) -> None:
        cmd = ["virtomate", "-h"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "help failed unexpectedly"
        assert "usage: virtomate" in result.stdout
        assert result.stderr == ""

    def test_long_form(self) -> None:
        cmd = ["virtomate", "--help"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "help failed unexpectedly"
        assert "usage: virtomate" in result.stdout
        assert result.stderr == ""

    def test_usage_errors(self) -> None:
        cmd = ["virtomate", "unknown-command"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 2, "unknown-command succeeded unexpectedly"
        assert result.stdout == ""
        assert "usage: virtomate" in result.stderr

    def test_missing_subcommand_raises_usage(self) -> None:
        cmd = ["virtomate"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 2, "command succeeded unexpectedly"
        assert result.stdout == ""
        assert "usage: virtomate" in result.stderr


class TestLogging:
    def test_no_logging_by_default(self) -> None:
        cmd = ["virtomate", "domain-list"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"

        domains: Sequence[DomainDescriptor] = json.loads(result.stdout)
        virtomate_domains = [d for d in domains if d["name"].startswith("virtomate")]
        assert virtomate_domains == []

        assert result.stderr == ""

    def test_short_form(self) -> None:
        cmd = ["virtomate", "-l", "debug", "domain-list"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"

        domains: Sequence[DomainDescriptor] = json.loads(result.stdout)
        virtomate_domains = [d for d in domains if d["name"].startswith("virtomate")]
        assert virtomate_domains == []

        assert "INFO:virtomate:Connecting to" in result.stderr

    def test_long_form(self) -> None:
        cmd = ["virtomate", "--log", "info", "domain-list"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"

        domains: Sequence[DomainDescriptor] = json.loads(result.stdout)
        virtomate_domains = [d for d in domains if d["name"].startswith("virtomate")]
        assert virtomate_domains == []

        assert "INFO:virtomate:Connecting to" in result.stderr

    def test_error_when_level_is_invalid(self) -> None:
        cmd = ["virtomate", "--log", "invalid", "domain-list"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 2, "domain-list succeeded unexpectedly"
        assert result.stdout == ""
        assert "usage: virtomate" in result.stderr


class TestVersionOption:
    def test_short_form(self) -> None:
        cmd = ["virtomate", "-v"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "version failed unexpectedly"
        assert result.stdout.strip() != ""
        assert result.stdout.strip() == importlib.metadata.version("virtomate")
        assert result.stderr == ""

    def test_long_form(self) -> None:
        cmd = ["virtomate", "--version"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "version failed unexpectedly"
        assert result.stdout.strip() != ""
        assert result.stdout.strip() == importlib.metadata.version("virtomate")
        assert result.stderr == ""


class TestConnectionOption:
    def test_default(self, simple_bios_vm: str) -> None:
        cmd = ["virtomate", "domain-list"]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"
        assert result.stderr == b""

        domains = json.loads(result.stdout)

        machine = next(d for d in domains if d["name"] == simple_bios_vm)
        assert machine == {
            "uuid": "d2ecf360-24a6-4952-95fb-68b99307d942",
            "name": simple_bios_vm,
            "state": "shut-off",
        }

    def test_short_form(self, simple_bios_vm: str) -> None:
        cmd = ["virtomate", "-c", "test:///default", "domain-list"]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"
        assert result.stderr == b""

        domains = json.loads(result.stdout)

        with pytest.raises(StopIteration):
            next(d for d in domains if d["name"] == simple_bios_vm)

    def test_long_form(self, simple_bios_vm: str) -> None:
        cmd = ["virtomate", "--connection", "test:///default", "domain-list"]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"
        assert result.stderr == b""

        domains = json.loads(result.stdout)

        with pytest.raises(StopIteration):
            next(d for d in domains if d["name"] == simple_bios_vm)


class TestPrettyOption:
    expected = [
        {
            "uuid": "6695eb01-f6a4-8304-79aa-97f2502e193f",
            "name": "test",
            "state": "running",
        },
    ]

    expected_error = {
        "type": "NotFoundError",
        "message": "Domain 'unknown' does not exist",
    }

    def test_default_not_pretty(self) -> None:
        cmd = ["virtomate", "-c", "test:///default", "domain-list"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"
        assert result.stdout.strip() == json.dumps(
            self.expected,
            indent=None,
            separators=(",", ":"),
            sort_keys=True,
        )
        assert result.stderr == ""

    def test_short_form(self) -> None:
        cmd = ["virtomate", "-c", "test:///default", "-p", "domain-list"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"
        assert result.stdout == json.dumps(
            self.expected, indent=2, separators=(",", ": "), sort_keys=True
        )
        assert result.stderr == ""

    def test_long_form(self) -> None:
        cmd = [
            "virtomate",
            "-c",
            "test:///default",
            "--pretty",
            "domain-list",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"
        assert result.stdout == json.dumps(
            self.expected, indent=2, separators=(",", ": "), sort_keys=True
        )
        assert result.stderr == ""

    def test_error_default_not_pretty(self) -> None:
        cmd = ["virtomate", "-c", "test:///default", "guest-ping", "unknown"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "guest-ping succeeded unexpectedly"
        assert result.stdout.strip() == json.dumps(
            self.expected_error,
            indent=None,
            separators=(",", ":"),
            sort_keys=True,
        )
        assert result.stderr == ""

    def test_error_short_form(self) -> None:
        cmd = ["virtomate", "-c", "test:///default", "-p", "guest-ping", "unknown"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "guest-ping succeeded unexpectedly"
        assert result.stdout.strip() == json.dumps(
            self.expected_error, indent=2, separators=(",", ": "), sort_keys=True
        )
        assert result.stderr == ""

    def test_error_long_form(self) -> None:
        cmd = [
            "virtomate",
            "-c",
            "test:///default",
            "--pretty",
            "guest-ping",
            "unknown",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "guest-ping succeeded unexpectedly"
        assert result.stdout.strip() == json.dumps(
            self.expected_error, indent=2, separators=(",", ": "), sort_keys=True
        )
        assert result.stderr == ""


class TestDomainList:
    def test_list(self, simple_bios_vm: str, simple_uefi_vm: str) -> None:
        cmd = ["virtomate", "domain-list"]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, "domain-list failed unexpectedly"
        assert result.stderr == b""

        domains = json.loads(result.stdout)

        # There might be pre-existing domains.
        assert len(domains) >= 2

        machine = next(d for d in domains if d["name"] == simple_bios_vm)
        assert machine == {
            "uuid": "d2ecf360-24a6-4952-95fb-68b99307d942",
            "name": simple_bios_vm,
            "state": "shut-off",
        }

        machine = next(d for d in domains if d["name"] == simple_uefi_vm)
        assert machine == {
            "uuid": "ef70b4c0-1773-44a3-9b95-f239ae97d9db",
            "name": simple_uefi_vm,
            "state": "shut-off",
        }


class TestDomainIfaceList:
    def test_error_when_domain_does_not_exist(self) -> None:
        cmd = ["virtomate", "domain-iface-list", "unknown"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "domain-iface-list succeeded unexpectedly"
        assert json.loads(result.stdout) == {
            "type": "NotFoundError",
            "message": "Domain 'unknown' does not exist",
        }
        assert result.stderr == ""

    def test_error_when_domain_off(self, simple_bios_vm: str) -> None:
        cmd = ["virtomate", "domain-iface-list", simple_bios_vm]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "domain-iface-list succeeded unexpectedly"
        assert json.loads(result.stdout) == {
            "type": "IllegalStateError",
            "message": f"Domain '{simple_bios_vm}' is not running",
        }
        assert result.stderr == ""

    def test_default_source(self, running_vm_for_class: str) -> None:
        wait_until_running(running_vm_for_class)
        wait_for_network(running_vm_for_class)

        # Default is lease (same as of `virsh domifaddr`)
        cmd = ["virtomate", "domain-iface-list", running_vm_for_class]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-iface-list failed unexpectedly"
        assert result.stderr == ""

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

    def test_source_lease(self, running_vm_for_class: str) -> None:
        wait_until_running(running_vm_for_class)
        wait_for_network(running_vm_for_class)

        cmd = [
            "virtomate",
            "domain-iface-list",
            "--source",
            "lease",
            running_vm_for_class,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-iface-list failed unexpectedly"
        assert result.stderr == ""

        interfaces = json.loads(result.stdout)
        assert interfaces == [
            {
                "name": ANY_STR,
                "hwaddr": "52:54:00:3d:0e:bb",
                "addresses": [{"address": ANY_STR, "prefix": ANY_INT, "type": "IPv4"}],
            },
        ]

    def test_source_agent(self, running_vm_for_class: str) -> None:
        wait_until_running(running_vm_for_class)
        wait_for_network(running_vm_for_class)

        cmd = [
            "virtomate",
            "domain-iface-list",
            "--source",
            "agent",
            running_vm_for_class,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-iface-list failed unexpectedly"
        assert result.stderr == ""

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

    def test_source_arp(self, running_vm_for_class: str) -> None:
        wait_until_running(running_vm_for_class)
        wait_for_network(running_vm_for_class)

        cmd = [
            "virtomate",
            "domain-iface-list",
            "--source",
            "arp",
            running_vm_for_class,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-iface-list failed unexpectedly"
        assert result.stderr == ""

        interfaces = json.loads(result.stdout)
        assert interfaces == [
            {
                "name": ANY_STR,
                "hwaddr": "52:54:00:3d:0e:bb",
                "addresses": [{"address": ANY_STR, "prefix": 0, "type": "IPv4"}],
            },
        ]


class TestDomainClone:
    def test_error_if_domain_to_clone_does_not_exist(self) -> None:
        clone_name = "virtomate-clone-copy"

        cmd = ["virtomate", "domain-clone", "does-not-exist", clone_name]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "domain-clone succeeded unexpectedly"
        assert json.loads(result.stdout) == {
            "type": "NotFoundError",
            "message": "Domain 'does-not-exist' does not exist",
        }
        assert result.stderr == ""

    def test_error_if_clone_already_exists(self, simple_bios_vm: str) -> None:
        cmd = ["virtomate", "domain-clone", simple_bios_vm, simple_bios_vm]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "domain-clone succeeded unexpectedly"
        assert json.loads(result.stdout) == {
            "type": "Conflict",
            "message": f"Domain '{simple_bios_vm}' exists already",
        }
        assert result.stderr == ""

    def test_error_if_original_not_shut_off(self, simple_bios_vm: str) -> None:
        clone_name = "virtomate-clone-copy"

        start_domain(simple_bios_vm)
        wait_until_running(simple_bios_vm)

        cmd = ["virtomate", "domain-clone", simple_bios_vm, clone_name]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "domain-clone succeeded unexpectedly"
        assert json.loads(result.stdout) == {
            "type": "IllegalStateError",
            "message": f"Domain '{simple_bios_vm}' must be shut off to be cloned",
        }
        assert result.stderr == ""

    def test_copy(self, simple_bios_vm: str) -> None:
        clone_name = "virtomate-clone-copy"

        cmd = ["virtomate", "domain-clone", simple_bios_vm, clone_name]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-clone failed unexpectedly"
        assert result.stdout == ""
        assert result.stderr == ""

        volume_tag = read_volume_xml(
            "default", "virtomate-clone-copy-virtomate-simple-bios"
        )
        format_tag = volume_tag.find("target/format")
        assert format_tag is not None
        assert format_tag.attrib["type"] == "qcow2"
        assert volume_tag.find("backingStore") is None

        start_domain(clone_name)
        wait_until_running(clone_name)

    def test_linked_with_qcow2_backing_store(self, simple_bios_vm: str) -> None:
        clone_name = "virtomate-clone-linked"

        cmd = [
            "virtomate",
            "domain-clone",
            "--mode",
            "linked",
            simple_bios_vm,
            clone_name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-clone failed unexpectedly"
        assert result.stdout == ""
        assert result.stderr == ""

        volume_tag = read_volume_xml(
            "default", "virtomate-clone-linked-virtomate-simple-bios"
        )
        format_tag = volume_tag.find("target/format")
        bs_path_tag = volume_tag.find("backingStore/path")
        bs_format_tag = volume_tag.find("backingStore/format")

        assert format_tag is not None
        assert format_tag.attrib["type"] == "qcow2"
        assert bs_path_tag is not None
        assert bs_path_tag.text == "/var/lib/libvirt/images/virtomate-simple-bios"
        assert bs_format_tag is not None
        assert bs_format_tag.attrib["type"] == "qcow2"

        start_domain(clone_name)
        wait_until_running(clone_name)

    def test_linked_with_raw_backing_store(self, simple_bios_raw_vm: str) -> None:
        clone_name = "virtomate-clone-linked"

        cmd = [
            "virtomate",
            "domain-clone",
            "--mode",
            "linked",
            simple_bios_raw_vm,
            clone_name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-clone failed unexpectedly"
        assert result.stdout == ""
        assert result.stderr == ""

        volume_tag = read_volume_xml(
            "default", "virtomate-clone-linked-virtomate-simple-bios-raw"
        )
        format_tag = volume_tag.find("target/format")
        bs_path_tag = volume_tag.find("backingStore/path")
        bs_format_tag = volume_tag.find("backingStore/format")

        assert format_tag is not None
        assert format_tag.attrib["type"] == "qcow2"
        assert bs_path_tag is not None
        assert bs_path_tag.text == "/var/lib/libvirt/images/virtomate-simple-bios-raw"
        assert bs_format_tag is not None
        assert bs_format_tag.attrib["type"] == "raw"

        start_domain(clone_name)
        wait_until_running(clone_name)

    def test_linked_with_copied_firmware(self, simple_uefi_vm: str) -> None:
        clone_name = "virtomate-clone-linked"

        cmd = [
            "virtomate",
            "domain-clone",
            "--mode",
            "linked",
            simple_uefi_vm,
            clone_name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-clone failed unexpectedly"
        assert result.stdout == ""
        assert result.stderr == ""

        volume_tag = read_volume_xml(
            "nvram", "virtomate-clone-linked-virtomate-simple-uefi-efivars.fd"
        )
        format_tag = volume_tag.find("target/format")
        assert format_tag is not None
        assert format_tag.attrib["type"] == "raw"
        assert volume_tag.find("backingStore") is None

        volume_tag = read_volume_xml(
            "default", "virtomate-clone-linked-virtomate-simple-uefi"
        )
        format_tag = volume_tag.find("target/format")
        bs_path_tag = volume_tag.find("backingStore/path")
        bs_format_tag = volume_tag.find("backingStore/format")

        assert format_tag is not None
        assert format_tag.attrib["type"] == "qcow2"
        assert bs_path_tag is not None
        assert bs_path_tag.text == "/var/lib/libvirt/images/virtomate-simple-uefi"
        assert bs_format_tag is not None
        assert bs_format_tag.attrib["type"] == "qcow2"

        start_domain(clone_name)
        wait_until_running(clone_name)

    @pytest.mark.reflink
    def test_reflink_copy(self, simple_bios_raw_vm: str) -> None:
        clone_name = "virtomate-clone-reflink"

        cmd = [
            "virtomate",
            "domain-clone",
            "--mode",
            "reflink",
            simple_bios_raw_vm,
            clone_name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "domain-clone failed unexpectedly"
        assert result.stdout == ""
        assert result.stderr == ""

        # Unfortunately, there is no tool that can tell apart a full from a shallow copy.
        volume_tag = read_volume_xml(
            "default", "virtomate-clone-reflink-virtomate-simple-bios-raw"
        )
        format_tag = volume_tag.find("target/format")
        assert format_tag is not None
        assert format_tag.attrib["type"] == "raw"
        assert volume_tag.find("backingStore") is None

        start_domain(clone_name)
        wait_until_running(clone_name)

    def test_rollback_if_disk_already_exists(self, simple_uefi_vm: str) -> None:
        clone_name = "virtomate-clone-copy"
        clone_disk_name = "virtomate-clone-copy-virtomate-simple-uefi"

        # Create a volume with the same name that is going to be used by `domain-clone` to induce a failure during the
        # clone process.
        cmd = ["virsh", "vol-create-as", "default", clone_disk_name, "1"]
        subprocess.run(cmd, check=True)

        cmd = [
            "virtomate",
            "domain-clone",
            simple_uefi_vm,
            clone_name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "domain-clone succeeded unexpectedly"
        assert json.loads(result.stdout) == {
            "type": "libvirtError",
            "message": f"internal error: storage volume name '{clone_disk_name}' already in use.",
        }
        assert result.stderr == ""

        domain_names = [d["name"] for d in list_virtomate_domains()]
        assert domain_names == [simple_uefi_vm]

        vol_names_default = [v["name"] for v in list_virtomate_volumes("default")]
        assert vol_names_default == ["virtomate-simple-uefi"]

        vol_names_nvram = [v["name"] for v in list_virtomate_volumes("nvram")]
        assert vol_names_nvram == ["virtomate-simple-uefi-efivars.fd"]


class TestGuestPing:
    def test_error_unknown_machine(self) -> None:
        cmd = ["virtomate", "guest-ping", "does-not-exist"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "guest-ping succeeded unexpectedly"
        assert json.loads(result.stdout) == {
            "type": "NotFoundError",
            "message": "Domain 'does-not-exist' does not exist",
        }
        assert result.stderr == ""

    def test_error_when_domain_off(self, simple_bios_vm: str) -> None:
        cmd = ["virtomate", "guest-ping", simple_bios_vm]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 125, "guest-ping succeeded unexpectedly"
        # No error because the return code already indicates that the guest could not be reached.
        assert result.stdout == ""
        assert result.stderr == ""

    def test_guest_ping(self, simple_bios_vm: str) -> None:
        start_domain(simple_bios_vm)

        for attempt in Retrying(stop=stop_after_delay(BOOT_TIMEOUT)):
            with attempt:
                cmd = ["virtomate", "guest-ping", simple_bios_vm]
                result = subprocess.run(cmd, capture_output=True, check=True, text=True)

        assert result.returncode == 0, f"Could not ping {simple_bios_vm}"
        assert result.stdout == ""
        assert result.stderr == ""

    def test_wait_for_guest_ping_success(self, simple_bios_vm: str) -> None:
        start_domain(simple_bios_vm)

        cmd = ["virtomate", "guest-ping", "--wait", str(BOOT_TIMEOUT), simple_bios_vm]
        result = subprocess.run(cmd, capture_output=True, text=True)

        assert result.returncode == 0, "Agent did not respond within timeout"
        assert result.stdout == ""
        assert result.stderr == ""


class TestPoolList:
    def test(self) -> None:
        cmd = ["virtomate", "pool-list"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "pool-list failed unexpectedly"
        assert result.stderr == ""

        pools: Sequence[PoolDescriptor] = json.loads(result.stdout)
        virtomate_pool = next(p for p in pools if p["name"] == "default")

        assert virtomate_pool == {
            "active": True,
            "allocation": ANY_INT,
            "available": ANY_INT,
            "capacity": ANY_INT,
            "name": "default",
            "number_of_volumes": ANY_INT,
            "persistent": True,
            "state": "running",
            "uuid": ANY_STR,
        }


class TestGuestRun:
    def test_error_unknown_domain(self) -> None:
        cmd = ["virtomate", "guest-run", "does-not-exist", "echo", "Hello World!"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "guest-run succeeded unexpectedly"
        assert json.loads(result.stdout) == {
            "type": "NotFoundError",
            "message": "Domain 'does-not-exist' does not exist",
        }
        assert result.stderr == ""

    def test_error_domain_not_running(self, simple_bios_vm: str) -> None:
        cmd = ["virtomate", "guest-run", simple_bios_vm, "echo", "Hello World!"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "guest-run succeeded unexpectedly"
        assert json.loads(result.stdout) == {
            "type": "IllegalStateError",
            "message": f"Domain '{simple_bios_vm}' is not running",
        }
        assert result.stderr == ""

    def test_hello_world_text(self, running_vm_for_class: str) -> None:
        wait_until_running(running_vm_for_class)

        cmd = [
            "virtomate",
            "guest-run",
            running_vm_for_class,
            "--",
            "echo",
            "-n",
            "Hello World!",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "guest-run failed unexpectedly"
        assert json.loads(result.stdout) == {
            "exit_code": 0,
            "signal": None,
            "stdout": "Hello World!",
            "stderr": None,
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
        assert result.stderr == ""

    def test_hello_world_base64(self, running_vm_for_class: str) -> None:
        wait_until_running(running_vm_for_class)

        cmd = [
            "virtomate",
            "guest-run",
            "--encode",
            running_vm_for_class,
            "--",
            "echo",
            "-n",
            "Hello World!",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "guest-run failed unexpectedly"
        assert json.loads(result.stdout) == {
            "exit_code": 0,
            "signal": None,
            "stdout": "SGVsbG8gV29ybGQh",  # == Hello World!
            "stderr": None,
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
        assert result.stderr == ""

    def test_run_failure(self, running_vm_for_class: str) -> None:
        wait_until_running(running_vm_for_class)

        cmd = ["virtomate", "guest-run", running_vm_for_class, "cat", "/unknown"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "guest-run failed unexpectedly"
        assert json.loads(result.stdout) == {
            "exit_code": 1,
            "signal": None,
            "stdout": None,
            "stderr": "cat: /unknown: No such file or directory\n",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
        assert result.stderr == ""

    def test_error_if_program_unknown(self, running_vm_for_class: str) -> None:
        wait_until_running(running_vm_for_class)

        cmd = ["virtomate", "guest-run", running_vm_for_class, "/does/not/exist"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "guest-run succeeded unexpectedly"
        assert result.stderr == ""

        error = json.loads(result.stdout)
        assert error["type"] == "libvirtError"
        assert "Failed to execute child process" in error["message"]

    def test_bash(self, running_vm_for_class: str) -> None:
        wait_until_running(running_vm_for_class)

        cmd = [
            "virtomate",
            "guest-run",
            running_vm_for_class,
            "--",
            "/usr/bin/env",
            "bash",
            "-c",
            'printf "Hello World" | wc -m',
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "guest-run failed unexpectedly"
        assert json.loads(result.stdout) == {
            "exit_code": 0,
            "signal": None,
            "stdout": "11\n",  # len("Hello World")
            "stderr": None,
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
        assert result.stderr == ""

    def test_empty_output(self, running_vm_for_class: str) -> None:
        wait_until_running(running_vm_for_class)

        cmd = ["virtomate", "guest-run", running_vm_for_class, "--", "true"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "guest-run failed unexpectedly"
        assert json.loads(result.stdout) == {
            "exit_code": 0,
            "signal": None,
            "stdout": None,
            "stderr": None,
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
        assert result.stderr == ""

    def test_stdout_and_stderr(self, running_vm_for_class: str) -> None:
        wait_until_running(running_vm_for_class)

        cmd = [
            "virtomate",
            "guest-run",
            running_vm_for_class,
            "--",
            "/usr/bin/env",
            "bash",
            "-c",
            "printf 'out' ; printf 'err' 1>&2",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "guest-run failed unexpectedly"
        assert json.loads(result.stdout) == {
            "exit_code": 0,
            "signal": None,
            "stdout": "out",
            "stderr": "err",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
        assert result.stderr == ""

    def test_stdin(self, running_vm_for_class: str) -> None:
        wait_until_running(running_vm_for_class)

        cmd = [
            "virtomate",
            "guest-run",
            running_vm_for_class,
            "--stdin",
            "--",
            "wc",
            "-m",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input="Hello World",
        )
        assert result.returncode == 0, "guest-run failed unexpectedly"
        assert json.loads(result.stdout) == {
            "exit_code": 0,
            "signal": None,
            "stdout": "11\n",
            "stderr": None,
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
        assert result.stderr == ""


class TestVolumeList:
    def test_list_nonexistent_pool(self) -> None:
        cmd = ["virtomate", "volume-list", "does-not-exist"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "volume-list succeeded unexpectedly"
        assert json.loads(result.stdout) == {
            "type": "NotFoundError",
            "message": "Pool 'does-not-exist' does not exist",
        }
        assert result.stderr == ""

    def test_list(self) -> None:
        cmd = ["virtomate", "volume-list", "default"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "Could not list volumes of pool default"
        assert result.stderr == ""

        volumes = json.loads(result.stdout)

        # Filter the volumes in case there are others in the storage pool.
        expected_names = ("simple-bios", "simple-uefi", "simple-uefi-efivars.fd")
        filtered_volumes = [v for v in volumes if v["name"] in expected_names]

        assert filtered_volumes == [
            {
                "name": "simple-bios",
                "key": "/var/lib/libvirt/images/simple-bios",
                "capacity": ANY_INT,
                "allocation": ANY_INT,
                "physical": ANY_INT,
                "type": "file",
                "target": {
                    "path": "/var/lib/libvirt/images/simple-bios",
                    "format_type": "qcow2",
                },
                "backing_store": None,
            },
            {
                "name": "simple-uefi",
                "key": "/var/lib/libvirt/images/simple-uefi",
                "capacity": ANY_INT,
                "allocation": ANY_INT,
                "physical": ANY_INT,
                "type": "file",
                "target": {
                    "path": "/var/lib/libvirt/images/simple-uefi",
                    "format_type": "qcow2",
                },
                "backing_store": None,
            },
            {
                "name": "simple-uefi-efivars.fd",
                "key": "/var/lib/libvirt/images/simple-uefi-efivars.fd",
                "capacity": ANY_INT,
                "allocation": ANY_INT,
                "physical": ANY_INT,
                "type": "file",
                "target": {
                    "path": "/var/lib/libvirt/images/simple-uefi-efivars.fd",
                    "format_type": "raw",
                },
                "backing_store": None,
            },
        ]


class TestVolumeImport:
    def test_error_if_volume_does_not_exist(
        self, tmp_path: pathlib.Path, after_function_cleanup: None
    ) -> None:
        volume_name = "virtomate-raw-" + "".join(
            random.choices(string.ascii_letters, k=10)
        )
        volume_path = tmp_path.joinpath(volume_name)

        volumes = list_virtomate_volumes("default")
        assert volumes == []

        cmd = ["virtomate", "volume-import", str(volume_path), "default"]
        result = subprocess.run(cmd, text=True, capture_output=True)
        assert result.returncode == 1
        assert json.loads(result.stdout) == {
            "type": "FileNotFoundError",
            "message": f"File '{volume_path}' does not exist",
        }
        assert result.stderr == ""

        # Ensure that there are no leftovers.
        volumes = list_virtomate_volumes("default")
        assert volumes == []

    def test_error_if_volume_is_not_a_file(
        self, tmp_path: pathlib.Path, after_function_cleanup: None
    ) -> None:
        volume_name = "virtomate-raw-" + "".join(
            random.choices(string.ascii_letters, k=10)
        )
        volume_path = tmp_path.joinpath(volume_name)
        volume_path.mkdir()

        volumes = list_virtomate_volumes("default")
        assert volumes == []

        cmd = ["virtomate", "volume-import", str(volume_path), "default"]
        result = subprocess.run(cmd, text=True, capture_output=True)
        assert result.returncode == 1
        assert json.loads(result.stdout) == {
            "type": "ValueError",
            "message": f"Cannot import '{volume_path}' because it is not a file",
        }
        assert result.stderr == ""

        # Ensure that there are no leftovers.
        volumes = list_virtomate_volumes("default")
        assert volumes == []

    def test_error_if_volume_already_exists(
        self, tmp_path: pathlib.Path, after_function_cleanup: None
    ) -> None:
        volume_name = "virtomate-raw-" + "".join(
            random.choices(string.ascii_letters, k=10)
        )
        volume_path = tmp_path.joinpath(volume_name)

        cmd = ["qemu-img", "create", "-f", "raw", str(volume_path), "1G"]
        subprocess.run(cmd, check=True)

        # Create a volume with the same name as the one we are going to import to induce a collision.
        cmd = ["virsh", "vol-create-as", "default", volume_name, "0"]
        subprocess.run(cmd, check=True)

        volumes = list_virtomate_volumes("default")
        assert volumes == [
            {
                "allocation": 0,
                "backing_store": None,
                "capacity": 0,
                "key": "/var/lib/libvirt/images/" + volume_name,
                "name": volume_name,
                "physical": None,
                "target": {
                    "format_type": "raw",
                    "path": "/var/lib/libvirt/images/" + volume_name,
                },
                "type": "file",
            }
        ]

        cmd = ["virtomate", "volume-import", str(volume_path), "default"]
        result = subprocess.run(cmd, text=True, capture_output=True)
        assert result.returncode == 1
        assert json.loads(result.stdout) == {
            "type": "Conflict",
            "message": f"Volume '{volume_name}' already exists in pool 'default'",
        }
        assert result.stderr == ""

        # Ensure that the original volume is still there and has not been tampered with.
        volumes = list_virtomate_volumes("default")
        assert volumes == [
            {
                "allocation": 0,
                "backing_store": None,
                "capacity": 0,
                "key": "/var/lib/libvirt/images/" + volume_name,
                "name": volume_name,
                "physical": None,
                "target": {
                    "format_type": "raw",
                    "path": "/var/lib/libvirt/images/" + volume_name,
                },
                "type": "file",
            }
        ]

    def test_import_qcow2(
        self, tmp_path: pathlib.Path, after_function_cleanup: None
    ) -> None:
        volume_name = "virtomate-qcow2-" + "".join(
            random.choices(string.ascii_letters, k=10)
        )
        volume_path = tmp_path.joinpath(volume_name)

        cmd = ["qemu-img", "create", "-f", "qcow2", str(volume_path), "1G"]
        subprocess.run(cmd, check=True)

        volumes = list_virtomate_volumes("default")
        assert volumes == []

        cmd = ["virtomate", "volume-import", str(volume_path), "default"]
        result = subprocess.run(cmd, text=True, capture_output=True)
        assert result.returncode == 0
        assert result.stdout == ""
        assert result.stderr == ""

        volumes = list_virtomate_volumes("default")
        assert volumes == [
            {
                "allocation": 200704,
                "backing_store": None,
                "capacity": 1073741824,
                "key": "/var/lib/libvirt/images/" + volume_name,
                "name": volume_name,
                "physical": 196624,
                "target": {
                    "format_type": "qcow2",
                    "path": "/var/lib/libvirt/images/" + volume_name,
                },
                "type": "file",
            }
        ]

    def test_import_raw(
        self, tmp_path: pathlib.Path, after_function_cleanup: None
    ) -> None:
        volume_name = "virtomate-raw-" + "".join(
            random.choices(string.ascii_letters, k=10)
        )
        volume_path = tmp_path.joinpath(volume_name)

        # Volume is sparse by default. Disk size is only a couple of kilobytes.
        cmd = ["qemu-img", "create", "-f", "raw", str(volume_path), "1G"]
        subprocess.run(cmd, check=True)

        volumes = list_virtomate_volumes("default")
        assert volumes == []

        cmd = ["virtomate", "volume-import", str(volume_path), "default"]
        result = subprocess.run(cmd, text=True, capture_output=True)
        assert result.returncode == 0
        assert result.stdout == ""
        assert result.stderr == ""

        volumes = list_virtomate_volumes("default")
        assert volumes == [
            {
                "allocation": 4096,
                "backing_store": None,
                "capacity": 1073741824,
                "key": "/var/lib/libvirt/images/" + volume_name,
                "name": volume_name,
                "physical": 1073741824,
                "target": {
                    "format_type": "raw",
                    "path": "/var/lib/libvirt/images/" + volume_name,
                },
                "type": "file",
            }
        ]

    def test_import_with_rename(
        self, tmp_path: pathlib.Path, after_function_cleanup: None
    ) -> None:
        volume_name = "virtomate-qcow2-" + "".join(
            random.choices(string.ascii_letters, k=10)
        )
        volume_path = tmp_path.joinpath(volume_name)

        cmd = ["qemu-img", "create", "-f", "qcow2", str(volume_path), "1G"]
        subprocess.run(cmd, check=True)

        volumes = list_virtomate_volumes("default")
        assert volumes == []

        cmd = [
            "virtomate",
            "volume-import",
            str(volume_path),
            "default",
            "virtomate-renamed",
        ]
        result = subprocess.run(cmd, text=True, capture_output=True)
        assert result.returncode == 0
        assert result.stdout == ""
        assert result.stderr == ""

        volumes = list_virtomate_volumes("default")
        assert volumes == [
            {
                "allocation": 200704,
                "backing_store": None,
                "capacity": 1073741824,
                "key": "/var/lib/libvirt/images/virtomate-renamed",
                "name": "virtomate-renamed",
                "physical": 196624,
                "target": {
                    "format_type": "qcow2",
                    "path": "/var/lib/libvirt/images/virtomate-renamed",
                },
                "type": "file",
            }
        ]
