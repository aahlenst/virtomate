import argparse
import importlib.metadata
import json
import logging
import sys
import typing
from collections.abc import Generator
from contextlib import contextmanager
from typing import TypedDict

import libvirt
from libvirt import virConnect

from virtomate import guest, volume, domain
from virtomate.domain import AddressSource, CloneMode

logger = logging.getLogger(__name__)


def libvirt_error_handler(ctx, error):  # type: ignore
    # TODO: Make it useful. Problem: Duplicates (?) contents of libvirt.libvirtError which would not be useful.
    #  https://libvirt.gitlab.io/libvirt-appdev-guide-python/libvirt_application_development_guide_using_python-Error_Handling-Registering_Error_Handler.html
    logger.debug("libvirt error %s", error)


libvirt.registerErrorHandler(f=libvirt_error_handler, ctx=None)


class ErrorMessage(TypedDict):
    type: str
    message: str | None


@contextmanager
def connect(uri: str | None = None) -> Generator[virConnect, None, None]:
    """Connect to a hypervisor using the given `uri` through libvirt. If `uri` is `None`, libvirt will use the following
    logic to determine what URI to use:

    1. The environment variable `LIBVIRT_DEFAULT_URI`
    2. The `uri_default` parameter defined in the client configuration file
    3. The first working hypervisor encountered

    See the libvirt documentation for supported `Connection URIs`_.

    Example:
        >>> with connect("test:///default") as conn:
        ...   ...

    Args:
        uri: libvirt connection URI or `None`

    Yields:
        libvirt connection

    Raises:
        libvirt.libvirtError: The connection could not be established.

    .. _Connection URIs:
        https://www.python.org/dev/peps/pep-0484/
    """
    conn = libvirt.open(uri)
    try:
        yield conn
    finally:
        conn.close()


def list_domains(args: argparse.Namespace) -> int:
    with connect(args.connection) as conn:
        result = domain.list_domains(conn)
        print(json.dumps(result))
        return 0


def clone_domain(args: argparse.Namespace) -> int:
    match args.mode:
        case "copy":
            mode = CloneMode.COPY
        case "linked":
            mode = CloneMode.LINKED
        case "reflink":
            mode = CloneMode.REFLINK
        case _:
            # Argument choices not matching all CloneMode types is a programming error.
            raise AssertionError("Unknown clone mode: {}".format(args.mode))

    with connect(args.connection) as conn:
        domain.clone_domain(conn, args.domain, args.newname, mode)
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
            # Argument choices not matching all AddressSource types is a programming error.
            raise AssertionError("Unknown address source: {}".format(args.source))

    with connect(args.connection) as conn:
        result = domain.list_domain_interfaces(conn, args.domain, source)
        print(json.dumps(result))
        return 0


def ping_guest(args: argparse.Namespace) -> int:
    with connect(args.connection) as conn:
        if guest.ping_guest(conn, args.domain):
            return 0
        else:
            return 1


def list_volumes(args: argparse.Namespace) -> int:
    with connect(args.connection) as conn:
        result = volume.list_volumes(conn, args.pool)
        print(json.dumps(result))
        return 0


def import_volume(args: argparse.Namespace) -> int:
    with connect(args.connection) as conn:
        volume.import_volume(conn, args.file, args.pool)
        return 0


def _handle_exception(ex: BaseException, output: typing.IO[str] = sys.stdout) -> int:
    """Handle the given exception by converting it into JSON and printing it to ``output``.

    Args:
        ex: exception to handle
        output: file-like object the exception will be written to

    Returns:
        exit code to be passed to :py:func:`sys.exit`
    """
    message: ErrorMessage = {"type": ex.__class__.__name__, "message": str(ex)}
    json.dump(message, output)
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description="Automate libvirt.")
    p.add_argument(
        "-v",
        "--version",
        action="version",
        version=importlib.metadata.version("virtomate"),
    )
    p.add_argument(
        "-c",
        "--connection",
        help="change the libvirt connection URI (default: %(default)s)",
        default=None,
    )
    sp = p.add_subparsers(title="Subcommands")

    # domain-list
    p_domain_list = sp.add_parser("domain-list", help="list all domains")
    p_domain_list.set_defaults(func=list_domains)

    # domain-clone
    p_domain_clone = sp.add_parser("domain-clone", help="clone a domain")
    p_domain_clone.add_argument(
        "domain",
        type=str,
        help="name of the domain to clone",
    )
    p_domain_clone.add_argument(
        "newname",
        type=str,
        help="name of the cloned domain",
    )
    p_domain_clone.add_argument(
        "--mode",
        choices=(
            "copy",
            "linked",
            "reflink",
        ),
        default="copy",
        help="how disks are cloned (default: %(default)s)",
    )
    p_domain_clone.set_defaults(func=clone_domain)

    # domain-iface-list
    p_domain_iface_list = sp.add_parser(
        "domain-iface-list", help="list network interfaces of a running domain"
    )
    p_domain_iface_list.add_argument("domain", type=str, help="name of the domain")
    p_domain_iface_list.add_argument(
        "--source",
        choices=(
            "lease",
            "agent",
            "arp",
        ),
        default="lease",
        help="source of the addresses (default: %(default)s)",
    )
    p_domain_iface_list.set_defaults(func=list_domain_interfaces)

    # guest-ping
    p_guest_ping = sp.add_parser("guest-ping", help="ping the QEMU Guest Agent")
    p_guest_ping.add_argument(
        "domain",
        type=str,
        help="name of the domain to ping",
    )
    p_guest_ping.set_defaults(func=ping_guest)

    # volume-list
    p_volume_list = sp.add_parser("volume-list", help="list volumes of a pool")
    p_volume_list.add_argument(
        "pool",
        type=str,
        help="name of the pool whose volumes should be listed",
    )
    p_volume_list.set_defaults(func=list_volumes)

    # volume-import
    p_volume_import = sp.add_parser("volume-import", help="import volume into a pool")
    p_volume_import.add_argument(
        "file",
        type=str,
        help="path to the file to be imported as a volume",
    )
    p_volume_import.add_argument(
        "pool",
        type=str,
        help="name of the pool that the volume should be imported into",
    )
    p_volume_import.set_defaults(func=import_volume)

    args = p.parse_args()
    try:
        status_code = args.func(args)
    except BaseException as ex:
        status_code = _handle_exception(ex, sys.stdout)

    # Ensure that all functions return a status code. This also helps mypy to narrow the type from Any.
    assert isinstance(status_code, int)

    return status_code
