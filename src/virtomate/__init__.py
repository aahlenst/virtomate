#!/usr/bin/env python3
import json
import logging
from enum import Enum
from typing import Dict, Sequence

import libvirt
import libvirt_qemu
from libvirt import virConnect

logger = logging.getLogger(__name__)

MachineList = Sequence[Dict[str, str]]
AddressList = Sequence[Dict[str, str]]

# Maps virDomainState to a human-readable string.
# https://libvirt.org/html/libvirt-libvirt-domain.html#virDomainState
STATE_MAPPINGS: dict[int, str] = {
    libvirt.VIR_DOMAIN_NOSTATE: "no state",
    libvirt.VIR_DOMAIN_RUNNING: "running",
    libvirt.VIR_DOMAIN_BLOCKED: "blocked",
    libvirt.VIR_DOMAIN_PAUSED: "paused",
    libvirt.VIR_DOMAIN_SHUTDOWN: "shutdown",
    libvirt.VIR_DOMAIN_SHUTOFF: "shut-off",
    libvirt.VIR_DOMAIN_CRASHED: "crashed",
    libvirt.VIR_DOMAIN_PMSUSPENDED: "suspended",
}


class AddressSource(Enum):
    LEASE = 1

    AGENT = 2

    ARP = 3


class CloneMode(Enum):
    COPY = 1

    REFLINK = 2

    LINKED = 3


class Hypervisor:
    _conn: virConnect

    def __init__(self, url: str):
        self._conn = libvirt.open(url)

    def connection(self) -> virConnect:
        """
        Return the underlying connection to the libvirt daemon for testing purposes. It allows to perform actions
        otherwise not supported by this class. This is especially useful when using libvirt's mock driver that keeps its
        state in memory only.
        """
        return self._conn

    def list_domains(self) -> MachineList:
        domains = self._conn.listAllDomains()
        mapped_domains = []
        for domain in domains:
            (state, _) = domain.state()
            readable_state = "unknown"
            if state in STATE_MAPPINGS:
                readable_state = STATE_MAPPINGS[state]

            mapped_domain = {
                "uuid": domain.UUIDString(),
                "name": domain.name(),
                "state": readable_state,
            }
            mapped_domains.append(mapped_domain)

        # Sort to ensure stable order
        return sorted(mapped_domains, key=lambda m: m["uuid"])

    def list_domain_interfaces(
        self, domain_name: str, source: AddressSource
    ) -> AddressList:
        domain = self._conn.lookupByName(domain_name)

        match source:
            case AddressSource.LEASE:
                s = libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE
            case AddressSource.AGENT:
                s = libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_AGENT
            case AddressSource.ARP:
                s = libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_ARP
            case _:
                raise AssertionError("Unknown address source: {}".format(source))

        interfaces = domain.interfaceAddresses(s, 0)

        result = []
        for name, props in interfaces.items():
            addresses = []
            for addr in props["addrs"]:
                # https://libvirt.org/html/libvirt-libvirt-network.html#virIPAddrType
                match addr["type"]:
                    case libvirt.VIR_IP_ADDR_TYPE_IPV4:
                        addr_type = "IPv4"
                    case libvirt.VIR_IP_ADDR_TYPE_IPV6:
                        addr_type = "IPv6"
                    case _:
                        raise AssertionError(
                            "Unknown address type: {}".format(addr["type"])
                        )

                address = {
                    "address": addr["addr"],
                    "prefix": addr["prefix"],
                    "type": addr_type,
                }
                addresses.append(address)

            interface = {
                "name": name,
                "hwaddr": props["hwaddr"],
                "addresses": sorted(addresses, key=lambda a: a["address"]),
            }
            result.append(interface)

        # Sort to ensure stable order
        return sorted(result, key=lambda i: i["hwaddr"])

    def ping_guest(self, domain_name: str) -> bool:
        domain = self._conn.lookupByName(domain_name)
        cmd = {"execute": "guest-ping"}
        json_cmd = json.dumps(cmd)
        try:
            libvirt_qemu.qemuAgentCommand(
                domain, json_cmd, libvirt_qemu.VIR_DOMAIN_QEMU_AGENT_COMMAND_DEFAULT, 0
            )
            return True
        except libvirt.libvirtError:
            return False


def main() -> int:
    hypervisor = Hypervisor("qemu:///system")
    if hypervisor.ping_guest("virtomate-simple-bios"):
        return 0
    else:
        return 1
