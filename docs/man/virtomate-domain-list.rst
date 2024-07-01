virtomate domain-list
=====================

Name
----

virtomate domain-list - List all domains.

Synopsis
--------

**virtomate domain-list** [*options*]

Description
-----------
:program:`virtomate domain-list` lists *all* domains.

The returned JSON message is a list of :class:`virtomate.domain.DomainDescriptor`:

.. autoclass:: virtomate.domain.DomainDescriptor
   :members:

Options
-------

.. program:: virtomate domain-list

.. option:: -h, --help

   Display usage summary of this command and exit.

Versions
--------

Added in version 0.1.0.

Examples
--------

List all domains of the default hypervisor:

.. code-block::

   $ virtomate -p domain-list
   [
     {
       "name": "my-domain",
       "state": "suspended",
       "uuid": "476ef224-e1ca-4a54-9095-202b11655c80"
     }
   ]

List all domains of the system-mode daemon on the remote host 10.0.7.3:

.. code-block::

   $ virtomate -c qemu+ssh://ubuntu@10.0.7.3/system -p domain-list
   [
     {
       "name": "remote-domain",
       "state": "running",
       "uuid": "21daf60b-9031-40a9-8e97-37da2998a41b"
     }
   ]


