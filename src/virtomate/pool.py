from collections.abc import Sequence
from typing import TypedDict

import libvirt
from libvirt import virConnect

# Maps virStoragePoolState to a human-readable string.
# https://libvirt.org/html/libvirt-libvirt-storage.html#virStoragePoolState
STATE_MAPPINGS: dict[int, str] = {
    libvirt.VIR_STORAGE_POOL_INACTIVE: "inactive",
    libvirt.VIR_STORAGE_POOL_BUILDING: "building",
    libvirt.VIR_STORAGE_POOL_RUNNING: "running",
    libvirt.VIR_STORAGE_POOL_DEGRADED: "degraded",
    libvirt.VIR_STORAGE_POOL_INACCESSIBLE: "inaccessible",
}


class PoolDescriptor(TypedDict):
    """Descriptor of a libvirt storage pool."""

    name: str
    """Name of the storage pool"""
    uuid: str
    """UUID of the storage pool"""
    state: str
    """Current state of the storage pool. Possible values: ``inactive``, ``building``, ``running``, ``degraded``,
    ``inaccessible``."""
    active: bool
    """Whether the storage pool is currently active."""
    persistent: bool
    """Whether the storage pool is persistent (``True``) or transient (``False``)."""
    capacity: int
    """Total capacity of the storage pool in bytes."""
    allocation: int
    """How much space (in bytes) has been allocated to storage volumes."""
    available: int
    """How much free space (in bytes) there is left in the storage pool."""
    number_of_volumes: int | None
    """Number of volumes in the storage pool. This value is only populated if the storage pool is running."""


def list_pools(conn: virConnect) -> Sequence[PoolDescriptor]:
    """List the all storage pools.

    Args:
        conn: libvirt connection

    Returns:
        List of all storage pools
    """
    pools: list[PoolDescriptor] = []
    for pool in conn.listAllStoragePools():
        (state, capacity, allocation, available) = pool.info()

        readable_state = "unknown"
        if state in STATE_MAPPINGS:
            readable_state = STATE_MAPPINGS[state]

        number_of_volumes = None
        if pool.isActive():
            number_of_volumes = pool.numOfVolumes()

        pool_descriptor: PoolDescriptor = {
            "name": pool.name(),
            "uuid": pool.UUIDString(),
            "state": readable_state,
            "active": bool(pool.isActive()),
            "persistent": bool(pool.isPersistent()),
            "capacity": capacity,
            "allocation": allocation,
            "available": available,
            "number_of_volumes": number_of_volumes,
        }
        pools.append(pool_descriptor)

    return pools


def pool_exists(conn: virConnect, name: str) -> bool:
    """Return ``True`` if the pool with the given name exists, ``False`` otherwise."""
    try:
        conn.storagePoolLookupByName(name)
        return True
    except libvirt.libvirtError:
        return False
