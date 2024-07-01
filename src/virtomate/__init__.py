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

from virtomate import guest, volume, domain, pool
from virtomate.domain import AddressSource, CloneMode

logger = logging.getLogger(__name__)
# Disable logging by default to prevent any output. Can be explicitly enabled with --log.
logging.basicConfig(level=sys.maxsize, force=True)
# Disable libvirt's default error handler because it is redundant. Every error raises a Python exception.
libvirt.registerErrorHandler(f=lambda ctx, err: ..., ctx=None)


class ErrorMessage(TypedDict):
    """Standardised error message that will be printed in case of an error."""

    type: str
    """Type of error, typically the name of the raised exception."""
    message: str | None
    """Human-readable message describing the error."""


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
    if uri is None or uri == "":
        logger.info("Connecting to default libvirt instance")
    else:
        logger.info("Connecting to libvirt instance %s", uri)

    conn = libvirt.open(uri)
    try:
        yield conn
    finally:
        conn.close()


def _list_domains(args: argparse.Namespace) -> int:
    with connect(args.connection) as conn:
        result = domain.list_domains(conn)
        _print_json(result, pretty=args.pretty)
        return 0


def _clone_domain(args: argparse.Namespace) -> int:
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


def _list_domain_interfaces(args: argparse.Namespace) -> int:
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
        _print_json(result, pretty=args.pretty)
        return 0


def _ping_guest(args: argparse.Namespace) -> int:
    with connect(args.connection) as conn:
        if guest.ping_guest(conn, args.domain, wait=args.wait):
            return 0
        else:
            # Why 125? See https://unix.stackexchange.com/a/418802/610434 for why the range of usable exit codes is
            # [0,125]. We assign exit codes for specific errors like this one ("Agent unreachable") by starting at the
            # upper end of the range and count down from there.
            return 125


def _run_in_guest(args: argparse.Namespace) -> int:
    stdin: bytes | None = None
    if args.stdin is not None:
        stdin = args.stdin.buffer.read()

    with connect(args.connection) as conn:
        result = guest.run_in_guest(
            conn,
            args.domain,
            args.program,
            args.argument,
            encode=args.encode,
            stdin=stdin,
        )
        _print_json(result, pretty=args.pretty)
        return 0


def _list_pools(args: argparse.Namespace) -> int:
    with connect(args.connection) as conn:
        result = pool.list_pools(conn)
        _print_json(result, pretty=args.pretty)
        return 0


def _list_volumes(args: argparse.Namespace) -> int:
    with connect(args.connection) as conn:
        result = volume.list_volumes(conn, args.pool)
        _print_json(result, pretty=args.pretty)
        return 0


def _import_volume(args: argparse.Namespace) -> int:
    with connect(args.connection) as conn:
        volume.import_volume(conn, args.file, args.pool, args.new_name)
        return 0


def _handle_exception(
    ex: BaseException, output: typing.IO[str] = sys.stdout, pretty: bool = False
) -> int:
    """Handle the given exception by converting it into JSON and printing it to ``output``.

    Args:
        ex: exception to handle
        output: file-like object the exception will be written to

    Returns:
        exit code to be passed to :py:func:`sys.exit`
    """
    logger.error("An error occurred, see exception below for details", exc_info=ex)
    message: ErrorMessage = {"type": ex.__class__.__name__, "message": str(ex)}
    _print_json(message, output=output, pretty=pretty)
    return 1


def _configure_logging(args: argparse.Namespace) -> None:
    if "log" not in args or not isinstance(args.log, str):
        return

    numeric_level = getattr(logging, args.log.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError("Invalid log level '%(level)s'" % {"level": args.log})

    logging.basicConfig(level=numeric_level, force=True)


def _print_json(
    result: typing.Any, output: typing.IO[str] = sys.stdout, pretty: bool = False
) -> None:
    indent = 2 if pretty else None
    separators = (",", ": ") if pretty else (",", ":")
    json.dump(result, output, indent=indent, separators=separators, sort_keys=True)


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
    p.add_argument(
        "-l",
        "--log",
        choices=("debug", "info", "warning", "error", "critical"),
        help="change the log level (default: %(default)s)",
        default=None,
    )
    p.add_argument(
        "-p",
        "--pretty",
        action="store_true",
        help="pretty-print JSON",
    )
    sp = p.add_subparsers(title="Subcommands", required=True)

    # domain-list
    p_domain_list = sp.add_parser("domain-list", help="list all domains")
    p_domain_list.set_defaults(func=_list_domains)

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
    p_domain_clone.set_defaults(func=_clone_domain)

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
    p_domain_iface_list.set_defaults(func=_list_domain_interfaces)

    # guest-ping
    p_guest_ping = sp.add_parser("guest-ping", help="ping the QEMU Guest Agent")
    p_guest_ping.add_argument(
        "domain",
        type=str,
        help="name of the domain to ping",
    )
    p_guest_ping.add_argument(
        "--wait",
        type=float,
        default=0,
        metavar="N",
        help="wait for N seconds for the QEMU Guest Agent to respond (default: %(default)s)",
    )
    p_guest_ping.set_defaults(func=_ping_guest)

    # guest-run
    p_guest_run = sp.add_parser("guest-run", help="run a program in the domain")
    p_guest_run.add_argument(
        "-e",
        "--encode",
        action="store_true",
        help="encode output with Base64",
    )
    # Use a flag to indicate that stdin should be consumed. As stdin is not mandatory, it is not possible to use a
    # positional argument for it because we are already treating all optional arguments as arguments for `program`.
    p_guest_run.add_argument(
        "--stdin",
        action="store_const",
        const=sys.stdin,
        help="consume stdin and pass it to program",
    )

    p_guest_run.add_argument(
        "domain",
        type=str,
        help="name of the domain",
    )
    p_guest_run.add_argument(
        "program",
        type=str,
        help="path of the program to run",
    )
    p_guest_run.add_argument(
        "argument",
        type=str,
        nargs="*",
        help="optional program argument",
    )
    p_guest_run.set_defaults(func=_run_in_guest)

    # pool-list
    p_pool_list = sp.add_parser("pool-list", help="list storage pools")
    p_pool_list.set_defaults(func=_list_pools)

    # volume-list
    p_volume_list = sp.add_parser("volume-list", help="list volumes of a pool")
    p_volume_list.add_argument(
        "pool",
        type=str,
        help="name of the pool whose volumes should be listed",
    )
    p_volume_list.set_defaults(func=_list_volumes)

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
    p_volume_import.add_argument(
        "new_name",
        type=str,
        nargs="?",
        help="name of the imported volume",
    )
    p_volume_import.set_defaults(func=_import_volume)

    args = p.parse_args()
    try:
        _configure_logging(args)
        logger.debug("Recognised arguments: %s", args)
        status_code = args.func(args)
    except BaseException as ex:
        status_code = _handle_exception(ex, sys.stdout, pretty=args.pretty)

    # Ensure that all functions return a status code. This also helps mypy to narrow the type from Any.
    assert isinstance(status_code, int)

    return status_code
