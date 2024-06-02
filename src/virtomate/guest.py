import json

import libvirt
import libvirt_qemu
from libvirt import virConnect


def ping_guest(conn: virConnect, domain_name: str) -> bool:
    """Ping the QEMU Guest Agent of a domain.

    Args:
        conn: libvirt connection
        domain_name: name of the domain to ping

    Returns:
        `True` if the QEMU Guest Agent responded, `False` otherwise.
    """
    # TODO: Reconsider error handling. If the domain does not exist, libvirt will raise an error. Do we want to check
    #  the existence of the domain ourselves and raise our own error or leave it to libvirt?
    domain = conn.lookupByName(domain_name)
    cmd = {"execute": "guest-ping"}
    json_cmd = json.dumps(cmd)
    try:
        libvirt_qemu.qemuAgentCommand(
            domain, json_cmd, libvirt_qemu.VIR_DOMAIN_QEMU_AGENT_COMMAND_DEFAULT, 0
        )
        return True
    except libvirt.libvirtError:
        return False
