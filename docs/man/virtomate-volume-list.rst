virtomate volume-list
=====================

Name
----

virtomate volume-list - List all volumes in a storage pool.

Synopsis
--------

**virtomate volume-list** [*options*] *pool*

Description
-----------
:program:`virtomate volume-list` lists *all* volumes in the storage pool named *pool*.

The returned JSON message is a list of :class:`virtomate.volume.VolumeDescriptor`:

.. autoclass:: virtomate.volume.VolumeDescriptor
   :members:

.. autoclass:: virtomate.volume.TargetDescriptor
   :members:

.. autoclass:: virtomate.volume.BackingStoreDescriptor
   :members:

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

List all storage pools:

.. code-block::

   $ virtomate -p pool-list
   [
     {
       "active": true,
       "allocation": 42042183680,
       "available": 1956635947008,
       "capacity": 1998678130688,
       "name": "default",
       "number_of_volumes": 4,
       "persistent": true,
       "state": "running",
       "uuid": "b3f4da29-2fdb-4ca6-a59d-c66f3c9737de"
     }
   ]
