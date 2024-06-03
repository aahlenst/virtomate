from collections.abc import Iterable
from typing import TypedDict
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from libvirt import virConnect


class TargetDescriptor(TypedDict):
    path: str
    format_type: str | None


class BackingStoreDescriptor(TypedDict):
    path: str | None
    format_type: str | None


class VolumeDescriptor(TypedDict):
    name: str
    key: str
    capacity: int | None
    allocation: int | None
    physical: int | None
    type: str | None
    target: TargetDescriptor
    backing_store: BackingStoreDescriptor | None


def list_volumes(conn: virConnect, pool_name: str) -> Iterable[VolumeDescriptor]:
    """List the volumes of a storage pool.

    Args:
        conn: libvirt connection
        pool_name: Name of the storage pool whose volumes should be listed

    Returns:
        List of volumes
    """
    volumes = []
    pool = conn.storagePoolLookupByName(pool_name)
    for volume in pool.listAllVolumes(0):
        # Schema: https://gitlab.com/libvirt/libvirt/-/blob/master/src/conf/schemas/storagevol.rng
        volume_xml = volume.XMLDesc()
        volume_tag = ElementTree.fromstring(volume_xml)

        # Attribute type is optional
        volume_type = volume_tag.get("type")

        # target/format is optional
        format_type = None
        target_format_tag = volume_tag.find("target/format")
        if target_format_tag is not None:
            format_type = target_format_tag.get("type")

        volume_props: VolumeDescriptor = {
            "name": volume.name(),
            "key": volume.key(),
            "capacity": _extract_sizing_element("capacity", volume_tag),
            "allocation": _extract_sizing_element("allocation", volume_tag),
            "physical": _extract_sizing_element("physical", volume_tag),
            "type": volume_type,
            "target": {"path": volume.path(), "format_type": format_type},
            "backing_store": _extract_backing_store(volume_tag),
        }

        volumes.append(volume_props)

    return sorted(volumes, key=lambda vol: vol["name"])


def _extract_sizing_element(tag_name: str, volume_tag: Element) -> int | None:
    """Extract a `sizing` element (`capacity`, `allocation`, …) from a volume descriptor. Return the size in bytes or
    `None` if the `sizing` element is absent or empty.

    Args:
        tag_name: Name of the `sizing` element to extract
        volume_tag: Root element of the volume descriptor

    Returns:
        The size in bytes, if present, or `None`, otherwise.
    """
    size_tag = volume_tag.find(tag_name)
    if size_tag is not None and size_tag.text is not None:
        unit = size_tag.get("unit")
        # Internally, libvirt operates on bytes. Therefore, we should never encounter any other unit.
        # https://gitlab.com/libvirt/libvirt/-/blob/master/include/libvirt/libvirt-storage.h#L248
        assert unit is None or unit == "bytes"

        # int in Python is only bound by available memory, see https://peps.python.org/pep-0237/
        return int(size_tag.text)

    return None


def _extract_backing_store(volume_tag: Element) -> BackingStoreDescriptor | None:
    """Extract the `backingStore` element from a volume descriptor. Return the extracted descriptor or `None` if the
    volume has no backing store.

    Args:
        volume_tag: Root element of the volume descriptor

    Returns:
        Extracted descriptor or `None` if the volume has no backing store.
    """
    bs_tag = volume_tag.find("backingStore")
    if bs_tag is None:
        return None

    backing_store = BackingStoreDescriptor(path=None, format_type=None)
    path_tag = bs_tag.find("path")
    if path_tag is not None:
        backing_store["path"] = path_tag.text

    format_tag = bs_tag.find("format")
    if format_tag is not None:
        backing_store["format_type"] = format_tag.get("type")

    return backing_store
