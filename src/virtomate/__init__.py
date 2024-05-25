#!/usr/bin/env python3
import argparse
import json
import logging
from enum import Enum
from types import TracebackType
from typing import Dict, Sequence

import libvirt
import libvirt_qemu
from libvirt import virConnect

logger = logging.getLogger(__name__)


def libvirt_error_handler(ctx, error):  # type: ignore
    # TODO: Make it useful. Problem: Duplicates (?) contents of libvirt.libvirtError which would not be useful.
    #  https://libvirt.gitlab.io/libvirt-appdev-guide-python/libvirt_application_development_guide_using_python-Error_Handling-Registering_Error_Handler.html
    logger.debug("libvirt error %s", error)


libvirt.registerErrorHandler(f=libvirt_error_handler, ctx=None)

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

    def __init__(self, url: str | None = None):
        self._conn = libvirt.open(url)

    def __enter__(self) -> "Hypervisor":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._conn is not None:
            self._conn.close()

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
        """List all network interfaces of a domain."""
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

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()


def list_domains(args: argparse.Namespace) -> int:
    with Hypervisor(args.connection) as hypervisor:
        result = hypervisor.list_domains()
        print(json.dumps(result))
        return 0


def list_domain_interfaces(args: argparse.Namespace) -> int:
    match args.source:
        case "lease":
            source = AddressSource.LEASE
        case "agent":
            source = AddressSource.AGENT
        case "arp":
            source = AddressSource.ARP
        case _:
            # Argument choices not matching all AddressSource is a programming error.
            raise AssertionError("Unknown address source: {}".format(args.source))

    with Hypervisor(args.connection) as hypervisor:
        result = hypervisor.list_domain_interfaces(args.domain, source)
        print(json.dumps(result))
        return 0


def ping_guest(args: argparse.Namespace) -> int:
    with Hypervisor(args.connection) as hypervisor:
        if hypervisor.ping_guest(args.domain):
            return 0
        else:
            return 1


def main() -> int:
    p = argparse.ArgumentParser(description="Automate libvirt.")
    p.add_argument("-c", "--connection", help="libvirt connection URI", default=None)
    sp = p.add_subparsers(title="Subcommands")

    # domain-list
    p_domain_list = sp.add_parser("domain-list", help="List all domains")
    p_domain_list.set_defaults(func=list_domains)

    # domain-iface-list
    p_domain_iface_list = sp.add_parser(
        "domain-iface-list", help="List network interfaces of a running domain"
    )
    p_domain_iface_list.add_argument("domain", type=str, help="Name of the domain")
    p_domain_iface_list.add_argument(
        "--source",
        choices=(
            "lease",
            "agent",
            "arp",
        ),
        default="lease",
        help="Source of the addresses (default: %(default)s)",
    )
    p_domain_iface_list.set_defaults(func=list_domain_interfaces)

    # guest-ping
    p_guest_ping = sp.add_parser("guest-ping", help="Ping the QEMU Guest Agent")
    p_guest_ping.add_argument(
        "domain",
        type=str,
        help="Name of the domain to ping",
    )
    p_guest_ping.set_defaults(func=ping_guest)

    args = p.parse_args()
    status_code = args.func(args)

    # Ensure that all functions return a status code. This also helps mypy to narrow the type from Any.
    assert isinstance(status_code, int)

    return status_code
