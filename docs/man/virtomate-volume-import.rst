virtomate volume-import
=======================

Name
----

virtomate volume-import - Import a local file into a storage pool.

Synopsis
--------

**virtomate volume-import** [*options*] *file* *pool* [*newname*]

Description
-----------
:program:`virtomate volume-import` imports *file*, stored on the computer running :program:`virtomate`, into the storage pool named *pool*, optionally renaming the volume to *newname*.

The format of *file* is retained as is its sparseness. The `QEMU Disk Image Utility <https://www.qemu.org/docs/master/tools/qemu-img.html>`_ :program:`qemu-img` is required to be on ``PATH`` to determine the storage format of the file to be imported.

Options
-------

.. program:: virtomate pool-list

.. option:: -h, --help

   Display usage summary of this command and exit.

Versions
--------

Added in version 0.1.0.

Examples
--------

Import the ISO of Debian 12, located in the current working directory, into the storage pool ``boot``, keeping its name:

.. code-block::

   $ virtomate volume-import debian-12.6.0-amd64-netinst.iso boot

Import the image ``disk.qcow2``, located in ``~/Downloads``, into the storage pool ``default`` while renaming it to ``my-virtual-machine.qcow2``:

.. code-block::

   $ virtomate volume-import ~/Downloads/disk.iso default my-virtual-machine.qcow2
