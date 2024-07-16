virtomate domain-clone
======================

Name
----

virtomate domain-clone - Clone a domain.

Synopsis
--------

**virtomate domain-clone** [*options*] *domain* *newname*

Description
-----------
:program:`virtomate domain-clone` clones the existing domain named *domain* and names the duplicate *newname*.

For cloning to succeed, the original domain named *domain* must be shut off before it can be cloned. Furthermore, all storage volumes to be cloned, including NVRAM flash devices, must be stored in a libvirt storage pool.

Cloning is performed by duplicating all file-based storage volumes according to the option ``--mode``. All other storage volumes are left untouched, as are file-based storage volumes marked as read-only. NVRAM flash, which is typically used to load UEFI firmware, is always duplicated by creating a byte-for-byte copy, regardless of ``--mode``.

The configuration of the cloned domain is altered as follows:

* Virtual network adapters are assigned a randomly generated MAC address with the same `Organisationally Unique Identifier <https://en.wikipedia.org/wiki/Organizationally_unique_identifier>`_ (OUI) as the original.
* All ports of graphic devices are configured to be auto-allocated.

The contents of the domains will not be altered. This means that the clone inherits all properties of the original, including its host name, statically assigned IP addresses, or SSH keys. It is recommended to use `cloud-init <https://cloudinit.readthedocs.io/>`_, :manpage:`virt-customize(1)` or a similar tool to re-configure the clone.

Options
-------

.. program:: virtomate domain-clone

.. option:: -h, --help

   Display usage summary of this command and exit.

.. option:: --mode

   Define how storage volumes of the existing domain should be duplicated. ``copy`` is the default.

   .. describe:: copy

      Create a byte-for-byte copy of the original storage volume. The resulting copy is independent of the original. Copying is the slowest cloning operation, but supported by all storage formats and file systems.

   .. describe:: linked

      Create a shallow copy of the original storage volume in qcow2 format that uses the original volume as a backing file. The duplicate will only contain changes written to the duplicate thanks to qcow2's copy-on-write mechanism. Linking is the fastest cloning operation. It is compatible with any source image format and any file system. However, the **original volume can no longer be used** without making the clones unusable.

   .. describe:: reflink

      Create a shallow copy of the original storage volume by using the file system's reflink capability. The duplicate will only contain data that is not in the original. Copying with the file system's reflink capability is as fast as linking. Furthermore, the original volume can continued to be used. However, it requires a file system with reflink capability (for example, Btrfs or XFS, but not ext4). Due to a limitation of libvirt, the original and duplicate volumes must be raw files.

Versions
--------

Added in version 0.1.0.

Examples
--------

Create a linked clone of *ubuntu-24.04* named *my-clone*:

.. code-block::

   $ virtomate domain-clone --mode linked ubuntu-24.04 my-clone
