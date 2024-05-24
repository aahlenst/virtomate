import json
import logging
import os
import subprocess
import pytest
from tenacity import stop_after_attempt, wait_fixed, retry

from tests.matchers import ANY_STR, ANY_INT

logger = logging.getLogger(__name__)

if "LIBVIRT_DEFAULT_URI" not in os.environ:
    logger.warning(
        "Environment variable LIBVIRT_DEFAULT_URI undefined, using qemu:///system"
    )
    os.environ["LIBVIRT_DEFAULT_URI"] = "qemu:///system"

pytestmark = pytest.mark.functional


@retry(stop=stop_after_attempt(30), wait=wait_fixed(1))
def wait_until_running(domain: str) -> None:
    """Waits until the QEMU Guest Agent of the given domain becomes responsive."""
    args = ["virtomate", "guest-ping", domain]
    subprocess.run(args, check=True)


@retry(stop=stop_after_attempt(30), wait=wait_fixed(1))
def wait_for_network(domain: str) -> None:
    """Waits until the given domain is connected a network."""
    # Use ARP because this is the method that takes the longest for changes to become visible.
    args = ["virtomate", "domifaddr", "--source", "arp", domain]
    result = subprocess.run(args, check=True, capture_output=True)
    assert len(json.loads(result.stdout)) > 0


def test_guest_ping(simple_bios_machine: str, automatic_cleanup: None) -> None:
    cmd = ["virtomate", "guest-ping", "does-not-exist"]
    result = subprocess.run(cmd, capture_output=True)
    assert result.returncode == 1, "guest-ping succeeded unexpectedly"
    assert result.stdout == b""
    # TODO: Expect proper JSON error response
    assert result.stderr != b""

    cmd = ["virtomate", "guest-ping", simple_bios_machine]
    result = subprocess.run(cmd, capture_output=True)
    assert result.returncode == 1, "guest-ping succeeded unexpectedly"
    assert result.stdout == b""
    assert result.stderr == b""

    cmd = ["virsh", "start", simple_bios_machine]
    result = subprocess.run(cmd)
    assert result.returncode == 0, "Could not start {}".format(simple_bios_machine)

    wait_until_running(simple_bios_machine)

    cmd = ["virtomate", "guest-ping", simple_bios_machine]
    result = subprocess.run(cmd, capture_output=True)
    assert result.returncode == 0, "Could not ping {}".format(simple_bios_machine)
    assert result.stdout == b""
    assert result.stderr == b""


def test_domifaddr(simple_bios_machine: str, automatic_cleanup: None) -> None:
    cmd = ["virtomate", "domifaddr", simple_bios_machine]
    result = subprocess.run(cmd, capture_output=True)
    assert result.returncode == 1, "domifaddr succeeded unexpectedly"
    assert result.stdout == b""
    # TODO: Expect proper JSON error response
    assert result.stderr != b""

    cmd = ["virsh", "start", simple_bios_machine]
    result = subprocess.run(cmd)
    assert result.returncode == 0, "Could not start {}".format(simple_bios_machine)

    wait_until_running(simple_bios_machine)
    wait_for_network(simple_bios_machine)

    # Default is lease (same as of `virsh domifaddr`)
    cmd = ["virtomate", "domifaddr", simple_bios_machine]
    result = subprocess.run(cmd, capture_output=True)
    assert result.returncode == 0, "domifaddr failed unexpectedly"
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

    # Lease
    cmd = ["virtomate", "domifaddr", "--source", "lease", simple_bios_machine]
    result = subprocess.run(cmd, capture_output=True)
    assert result.returncode == 0, "domifaddr failed unexpectedly"
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
    cmd = ["virtomate", "domifaddr", "--source", "agent", simple_bios_machine]
    result = subprocess.run(cmd, capture_output=True)
    assert result.returncode == 0, "domifaddr failed unexpectedly"
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
    cmd = ["virtomate", "domifaddr", "--source", "arp", simple_bios_machine]
    result = subprocess.run(cmd, capture_output=True)
    assert result.returncode == 0, "domifaddr failed unexpectedly"
    assert result.stderr == b""

    interfaces = json.loads(result.stdout)
    assert interfaces == [
        {
            "name": ANY_STR,
            "hwaddr": "52:54:00:3d:0e:bb",
            "addresses": [{"address": ANY_STR, "prefix": 0, "type": "IPv4"}],
        },
    ]
