import libvirt
from libvirt import virConnect


def pool_exists(conn: virConnect, name: str) -> bool:
    """Return ``True`` if the pool with the given name exists, ``False`` otherwise."""
    try:
        conn.storagePoolLookupByName(name)
        return True
    except libvirt.libvirtError:
        return False
