virtomate pool-list
===================

Name
----

virtomate pool-list - List all storage pools.

Synopsis
--------

**virtomate pool-list** [*options*]

Description
-----------
:program:`virtomate pool-list` lists *all* storage pools.

The returned JSON message has the following structure:

.. autoclass:: virtomate.pool.PoolDescriptor
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
