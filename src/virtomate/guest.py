import json
import logging
import sys
import time
from base64 import b64decode, b64encode
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TypedDict

import libvirt
import libvirt_qemu
from libvirt import virConnect, virDomain

from virtomate.error import NotFoundError, IllegalStateError

logger = logging.getLogger(__name__)


def ping_guest(conn: virConnect, domain_name: str, wait: float = 0) -> bool:
    """Ping the QEMU Guest Agent of a domain. Return ``True`` if the QEMU Guest Agent responded, ``False`` otherwise.

    Args:
        conn: libvirt connection
        domain_name: Name of the domain to ping
        wait: For how many seconds to wait for the QEMU Guest Agent to respond

    Returns:
        ``True`` if the QEMU Guest Agent responded, ``False`` otherwise.

    Raises:
        virtomate.error.NotFoundError: if the domain does not exist
    """
    # Convert the potential libvirt error in one of virtomate's exceptions because the domain lookup doubles as argument
    # validation which is virtomate's responsibility.
    try:
        domain = conn.lookupByName(domain_name)
    except libvirt.libvirtError as ex:
        raise NotFoundError(
            "Domain '%(domain)s' does not exist" % {"domain": domain_name}
        ) from ex

    cmd = {"execute": "guest-ping"}
    json_cmd = json.dumps(cmd)

    attempt = 0
    end = datetime.now() + timedelta(seconds=wait)
    while True:  # We want to send at least one ping and Python has no do...while.
        attempt += 1
        try:
            libvirt_qemu.qemuAgentCommand(domain, json_cmd, 30, 0)
            logger.debug("Attempt %d to ping %s succeeded", attempt, domain_name)
            return True
        except libvirt.libvirtError as ex:
            logger.debug(
                "Attempt %d to ping %s failed", attempt, domain_name, exc_info=ex
            )
            time.sleep(0.5)

        if datetime.now() >= end:
            return False


_GuestExecStatus = TypedDict(
    "_GuestExecStatus",
    {
        "exited": bool,
        "exitcode": int,
        "signal": int,
        "out-data": str,
        "err-data": str,
        "out-truncated": bool,
        "err-truncated": bool,
    },
    total=False,
)


class RunResult(TypedDict):
    exit_code: int | None
    """Exit code of the program if it was terminated normally."""
    signal: int | None
    """Signal number (Unix-like operating systems) or unhandled exception code (Windows) if the program was terminated
    abnormally."""
    stdout: str | None
    """Captured standard output of the program."""
    stderr: str | None
    """Captured standard error of the program."""
    stdout_truncated: bool
    """Whether standard output was truncated."""
    stderr_truncated: bool
    """Whether standard error was truncated."""


def run_in_guest(
    conn: virConnect,
    domain_name: str,
    program: str,
    arguments: Sequence[str],
    encode: bool = False,
    stdin: bytes | None = None,
) -> RunResult:
    """Run ``program`` with its ``arguments`` on the guest identified by ``domain_name``, optionally passing  ``stdin``
    as standard input to ``program``. The program's exit code, standard output and standard error and any potentially
    received signal will be returned once the program has exited. QEMU Guest Agent needs to installed and running on the
    guest for this function to work. If QEMU Guest Agent is not installed or running, :py:class:`libvirt.libvirtError`
    will be raised.

    ``program`` will be run directly using an ``exec()``-like function without the involvement of any shell or command
    prompt.

    Due to limitations of libvirt and QEMU Guest Agent, standard input, output, and error are limited in size to a few
    megabytes. Furthermore, standard input is fully buffered due to way QEMU Guest Agent operates.

    Args:
        conn: libvirt connection
        domain_name: Name of the domain
        program: Name or path of the program to run on the guest. ``program`` must be on ``PATH`` if only the name of
            ``program`` is given.
        arguments: Arguments to be passed to ``program``
        encode: Whether standard output and standard error should be encoded with Base64
        stdin: Optional standard input to be passed to ``program``

    Returns:
        Results of the program execution

    Raises:
        virtomate.error.NotFoundError: if the domain does not exist
        virtomate.error.IllegalStateError: if the domain is not running
        libvirt.libvirtError: if any libvirt operation fails
    """
    try:
        domain = conn.lookupByName(domain_name)
    except libvirt.libvirtError as ex:
        raise NotFoundError(
            "Domain '%(domain)s' does not exist" % {"domain": domain_name}
        ) from ex

    # Validate state instead of using domain_in_state to save a lookup.
    (domain_state, _) = domain.state(0)
    if domain_state != libvirt.VIR_DOMAIN_RUNNING:
        raise IllegalStateError(
            "Domain '%(domain)s' is not running" % {"domain": domain_name}
        )

    pid = _guest_exec(domain, program, arguments, stdin=stdin)
    result = _wait_for_guest_exec(domain, pid)

    # For JSON structure, see https://qemu-project.gitlab.io/qemu/interop/qemu-ga-ref.html#qapidoc-194
    exit_code = result["exitcode"] if "exitcode" in result else None
    signal = result["signal"] if "signal" in result else None

    stdout = None
    if "out-data" in result:
        if encode:
            stdout = result["out-data"]
        else:
            stdout = b64decode(result["out-data"]).decode("utf-8")

    stderr = None
    if "err-data" in result:
        if encode:
            stderr = result["err-data"]
        else:
            stderr = b64decode(result["err-data"]).decode("utf-8")

    # According to https://gitlab.com/qemu-project/qemu/-/blob/master/qga/commands.c#L23, the maximum output size is 16
    # MB. But libvirt already refuses to process responses that are much smaller (around 4 MB unencoded) and raises an
    # error. Hence, we never get into the situation that output is truncated. But libvirt might change its mind and
    # start accepting much larger messages. Hence, it seems sensible to leave it in.
    stdout_truncated = False
    if "out-truncated" in result:
        stdout_truncated = result["out-truncated"]

    stderr_truncated = False
    if "err-truncated" in result:
        stderr_truncated = result["err-truncated"]

    return {
        "exit_code": exit_code,
        "signal": signal,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }


def _guest_exec(
    domain: virDomain,
    program: str,
    arguments: Sequence[str],
    stdin: bytes | None = None,
) -> int:
    # For JSON structure, see https://qemu-project.gitlab.io/qemu/interop/qemu-ga-ref.html#qapidoc-211
    cmd_args = {"path": program, "arg": arguments, "capture-output": True}
    if stdin is not None:
        cmd_args["input-data"] = b64encode(stdin).decode("ascii")

    cmd = {"execute": "guest-exec", "arguments": cmd_args}
    cmd_json = json.dumps(cmd)

    logger.debug("Sending QMP command to %s: %s", domain.name(), cmd_json)

    result_json = libvirt_qemu.qemuAgentCommand(
        domain, cmd_json, libvirt_qemu.VIR_DOMAIN_QEMU_AGENT_COMMAND_DEFAULT, 0
    )

    logger.debug("QMP response received from %s: %s", domain.name(), result_json)

    result = json.loads(result_json)
    # For JSON structure, see https://qemu-project.gitlab.io/qemu/interop/qemu-ga-ref.html#qapidoc-201
    pid = result["return"]["pid"]
    assert isinstance(pid, int), "PID is not a number"
    return pid


def _wait_for_guest_exec(
    domain: virDomain, pid: int, timeout: int = sys.maxsize
) -> _GuestExecStatus:
    start = time.monotonic()
    while True:
        if (time.monotonic() - start) > timeout:
            raise TimeoutError("Agent command did not complete in %u seconds" % timeout)

        cmd = {"execute": "guest-exec-status", "arguments": {"pid": pid}}
        cmd_json = json.dumps(cmd)

        logger.debug("Sending QMP command to %s: %s", domain.name(), cmd_json)

        result_json = libvirt_qemu.qemuAgentCommand(
            domain, cmd_json, libvirt_qemu.VIR_DOMAIN_QEMU_AGENT_COMMAND_DEFAULT, 0
        )

        logger.debug("QMP response received from %s: %s", domain.name(), result_json)

        result: _GuestExecStatus = json.loads(result_json)["return"]
        if not result["exited"]:
            logger.debug("Command has not finished yet, trying again")
            continue

        return result
