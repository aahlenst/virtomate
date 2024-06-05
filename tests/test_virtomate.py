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
from tenacity import stop_after_attempt, wait_fixed, retry
import importlib.metadata
from tests.matchers import ANY_STR, ANY_INT
from virtomate.domain import DomainDescriptor
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

        volume_tag = read_volume_xml(
            "default", "virtomate-clone-copy-virtomate-simple-bios"
        )
        format_tag = volume_tag.find("target/format")
        assert format_tag is not None
        assert format_tag.attrib["type"] == "qcow2"
        assert volume_tag.find("backingStore") is None

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
        volume_tag = read_volume_xml(
            "default", "virtomate-clone-reflink-virtomate-simple-bios-raw"
        )
        format_tag = volume_tag.find("target/format")
        assert format_tag is not None
        assert format_tag.attrib["type"] == "raw"
        assert volume_tag.find("backingStore") is None

        start_domain(clone_name)
        wait_until_running(clone_name)

    def test_rollback_if_disk_already_exists(
        self, simple_uefi_machine: str, automatic_cleanup: None
    ) -> None:
        clone_name = "virtomate-clone-copy"
        clone_disk_name = "virtomate-clone-copy-virtomate-simple-uefi"

        # Create a volume with the same name that is going to be used by `domain-clone` to induce a failure during the
        # clone process.
        cmd = ["virsh", "vol-create-as", "default", clone_disk_name, "1"]
        subprocess.run(cmd, check=True)

        cmd = [
            "virtomate",
            "domain-clone",
            simple_uefi_machine,
            clone_name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "domain-clone succeeded unexpectedly"
        assert result.stdout == ""
        # TODO: Expect proper JSON error response
        assert result.stderr != ""

        domain_names = [d["name"] for d in list_virtomate_domains()]
        assert domain_names == [simple_uefi_machine]

        vol_names_default = [v["name"] for v in list_virtomate_volumes("default")]
        assert vol_names_default == ["virtomate-simple-uefi"]

        vol_names_nvram = [v["name"] for v in list_virtomate_volumes("nvram")]
        assert vol_names_nvram == ["virtomate-simple-uefi-efivars.fd"]


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


class TestVolumeList:
    def test_list_nonexistent_pool(self) -> None:
        cmd = ["virtomate", "volume-list", "does-not-exist"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1, "volume-list succeeded unexpectedly"
        # TODO: Expect proper JSON response
        assert result.stderr != ""

    def test_list(self) -> None:
        cmd = ["virtomate", "volume-list", "virtomate"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "Could not list volumes of pool virtomate"
        assert result.stderr == ""

        volumes = json.loads(result.stdout)
        assert volumes == [
            {
                "name": "simple-bios",
                "key": "/var/lib/libvirt/virtomate/simple-bios",
                "capacity": ANY_INT,
                "allocation": ANY_INT,
                "physical": ANY_INT,
                "type": "file",
                "target": {
                    "path": "/var/lib/libvirt/virtomate/simple-bios",
                    "format_type": "qcow2",
                },
                "backing_store": None,
            },
            {
                "name": "simple-uefi",
                "key": "/var/lib/libvirt/virtomate/simple-uefi",
                "capacity": ANY_INT,
                "allocation": ANY_INT,
                "physical": ANY_INT,
                "type": "file",
                "target": {
                    "path": "/var/lib/libvirt/virtomate/simple-uefi",
                    "format_type": "qcow2",
                },
                "backing_store": None,
            },
            {
                "name": "simple-uefi-efivars.fd",
                "key": "/var/lib/libvirt/virtomate/simple-uefi-efivars.fd",
                "capacity": ANY_INT,
                "allocation": ANY_INT,
                "physical": ANY_INT,
                "type": "file",
                "target": {
                    "path": "/var/lib/libvirt/virtomate/simple-uefi-efivars.fd",
                    "format_type": "raw",
                },
                "backing_store": None,
            },
        ]


class TestVolumeUpload:
    def test_error_if_volume_does_not_exist(
        self, tmp_path: pathlib.Path, automatic_cleanup: None
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
        assert result.stdout == ""
        # TODO: Expect proper JSON error
        assert result.stderr != ""

        # Ensure that there are no leftovers.
        volumes = list_virtomate_volumes("default")
        assert volumes == []

    def test_error_if_volume_already_exists(
        self, tmp_path: pathlib.Path, automatic_cleanup: None
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
        assert result.stdout == ""
        # TODO: Expect proper JSON error
        assert result.stderr != ""

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
        self, tmp_path: pathlib.Path, automatic_cleanup: None
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

    def test_import_raw(self, tmp_path: pathlib.Path, automatic_cleanup: None) -> None:
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
