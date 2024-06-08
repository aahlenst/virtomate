import json

import libvirt
import libvirt_qemu
from libvirt import virConnect

from virtomate.error import NotFoundError


def ping_guest(conn: virConnect, domain_name: str) -> bool:
    """Ping the QEMU Guest Agent of a domain. Return ``True`` if the QEMU Guest Agent responded, ``False`` otherwise.

    Args:
        conn: libvirt connection
        domain_name: Name of the domain to ping

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
    try:
        libvirt_qemu.qemuAgentCommand(
            domain, json_cmd, libvirt_qemu.VIR_DOMAIN_QEMU_AGENT_COMMAND_DEFAULT, 0
        )
        return True
    except libvirt.libvirtError:
        return False
