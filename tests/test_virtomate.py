import subprocess
from tenacity import stop_after_attempt, wait_fixed, retry

from tests.conftest import AutomaticCleanupRoutine


@retry(stop=stop_after_attempt(30), wait=wait_fixed(1))
def wait_until_running(domain: str) -> None:
    args = ["virsh", "qemu-agent-command", domain, '{"execute": "guest-ping"}']
    subprocess.run(args, check=True)


def test_guest_ping(
    simple_bios_machine: str, automatic_cleanup: AutomaticCleanupRoutine
) -> None:
    result = subprocess.run(["virtomate", "guest-ping", simple_bios_machine])
    assert result.returncode == 1, "guest-ping succeeded unexpectedly"

    result = subprocess.run(["virsh", "start", simple_bios_machine])
    assert result.returncode == 0, "Could not start {}".format(simple_bios_machine)

    wait_until_running(simple_bios_machine)

    result = subprocess.run(["virtomate", "guest-ping", simple_bios_machine])
    assert result.returncode == 0, "Could not ping {}".format(simple_bios_machine)
