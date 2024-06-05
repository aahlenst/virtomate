import json
import os.path
import subprocess
from collections.abc import Iterable
from typing import TypedDict
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import libvirt
from libvirt import virConnect

_EOF_POSITION = -1


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


def import_volume(conn: virConnect, path: str, pool_name: str) -> None:
    cmd = ["qemu-img", "info", "--output=json", path]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        # TODO: Custom exception
        raise Exception

    volume_info = json.loads(result.stdout)
    if "format" not in volume_info:
        # TODO: Custom exception
        raise Exception

    volume_tag = ElementTree.Element("volume")
    name_tag = ElementTree.SubElement(volume_tag, "name")
    name_tag.text = os.path.basename(path)
    capacity_tag = ElementTree.SubElement(volume_tag, "capacity", {"unit": "bytes"})
    # Volume will be resized automatically during upload. A size of 0 ensures that a sparse volume stays sparse.
    capacity_tag.text = "0"
    volume_xml = ElementTree.tostring(volume_tag, encoding="unicode")

    pool = conn.storagePoolLookupByName(pool_name)
    volume = pool.createXML(volume_xml, 0)
    stream = conn.newStream(0)
    try:
        offset = 0
        length = 0  # read entire file
        volume.upload(
            stream, offset, length, libvirt.VIR_STORAGE_VOL_UPLOAD_SPARSE_STREAM
        )

        with open(path, mode="rb") as f:
            # To make sense of all the callbacks and their logic, see
            # https://libvirt.org/html/libvirt-libvirt-stream.html#virStreamSparseSendAll
            #
            # There is also example code in Python on
            # https://gitlab.com/libvirt/libvirt-python/-/blob/master/examples/sparsestream.py
            stream.sparseSendAll(_read_source, _determine_hole, _skip_hole, f.fileno())

        stream.finish()
    except BaseException:
        stream.abort()

        raise


def _read_source(_stream: libvirt.virStream, nbytes: int, fd: int) -> bytes:
    return os.read(fd, nbytes)


def _determine_hole(_stream: libvirt.virStream, fd: int) -> tuple[bool, int]:
    current_position = os.lseek(fd, 0, os.SEEK_CUR)

    try:
        data_position = os.lseek(fd, current_position, os.SEEK_DATA)
    except OSError as e:
        # Error 6 is "No such device or address". This means we have reached the end of the file.
        if e.errno == 6:
            data_position = _EOF_POSITION
        else:
            raise

    if current_position < data_position:
        in_data = False
        offset = data_position - current_position
    elif data_position == _EOF_POSITION:
        in_data = False
        offset = os.lseek(fd, 0, os.SEEK_END) - current_position
    else:
        in_data = True
        next_hole_position = os.lseek(fd, data_position, os.SEEK_HOLE)
        assert next_hole_position > 0, "No trailing hole"
        offset = next_hole_position - data_position

    # Reset position in file
    os.lseek(fd, current_position, os.SEEK_SET)

    assert offset >= 0, "Next position is behind current position"

    return (
        in_data,
        offset,
    )


def _skip_hole(_stream: libvirt.virStream, nbytes: int, fd: int) -> int:
    return os.lseek(fd, nbytes, os.SEEK_CUR)
