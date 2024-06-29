virtomate
=========

Name
----

virtomate - Automate libvirt.

Synopsis
--------

**virtomate** [*global options*] *command* [*command options*]

Description
-----------

:program:`virtomate` is a command line utility to automate virtual machines with libvirt. In contrast to :manpage:`virsh(1)` it returns JSON to be processed by other tools. Furthermore, it provides advanced commands to clone domains, run programs on domains, or import volumes. :program:`virtomate` is not meant as a replacement for :manpage:`virsh(1)` but to complement it.

:program:`virtomate` uses libvirt. As such, it can manage virtual machines on the same computer it is running on as well on remote hosts. See the option ``-c`` for further information.

No matter whether a :program:`virtomate` command succeeds or fails, :program:`virtomate` prints JSON to standard output (stdout), if any. Standard error (stderr) is reserved for diagnostic output. To distinguish between a standard and error response, examine the exit status of :program:`virtomate`.

* A status of **0** indicates success. This means that you can expect a standard response.
* A status of **1** indicates a :program:`virtomate` error and a standardised error message with the following structure will be printed to standard output:

   .. autoclass:: virtomate.ErrorMessage
      :members:
* A status of **2** indicates a usage error. Usage information will be printed to standard error.

Options
-------

.. program:: virtomate

.. option:: -c URI, --connection URI

   Use ``URI`` to connect to the hypervisor instead of using the default. See the `libvirt documentation <https://libvirt.org/uri.html>`_ for details about the hypervisor selection logic.

.. option:: -h, --help

   Display usage summary and exit.

.. option:: -l LEVEL, --log LEVEL

   Enable logging to ``stderr`` and log all messages of ``LEVEL`` and above. Valid options are: ``debug``, ``info``, ``warning``, ``error``, ``critical``.

.. option:: -p, --pretty

   Enable pretty-printing of the JSON output.

.. option:: -v, --version

   Display Virtomate's version and exit.

Commands
--------

+---------------------------------------------------------+------------------------------------------------+
| Command                                                 | Description                                    |
+=========================================================+================================================+
| :doc:`domain-list <virtomate-domain-list>`              | List all domains.                              |
+---------------------------------------------------------+------------------------------------------------+
| :doc:`domain-clone <virtomate-domain-clone>`            | Clone a domain.                                |
+---------------------------------------------------------+------------------------------------------------+
| :doc:`domain-iface-list <virtomate-domain-iface-list>`  | List network interfaces of a running domain.   |
+---------------------------------------------------------+------------------------------------------------+
| guest-ping                                              | Ping the QEMU Guest Agent of a running domain. |
+---------------------------------------------------------+------------------------------------------------+
| guest-run                                               | Run a program in the running domain.           |
+---------------------------------------------------------+------------------------------------------------+
| pool-list                                               | List all storage pools.                        |
+---------------------------------------------------------+------------------------------------------------+
| volume-list                                             | List all storage volumes.                      |
+---------------------------------------------------------+------------------------------------------------+
| volume-import                                           | Import a local file into a storage pool.       |
+---------------------------------------------------------+------------------------------------------------+

Exit Status
-----------

:program:`virtomate` exits with status 0 on success, non-zero on error.

Details about the error statuses:

1
   Indicates an operation error; a JSON error message will be printed to standard output.

2
   Indicates an usage error; usage information will be printed to standard error.

Environment
-----------

.. describe:: LIBVIRT_DEFAULT_URI

   Set the URI of the hypervisor :program:`virtomate` connects to. See the `libvirt documentation <https://libvirt.org/uri.html>`_ for supported URIs.

Versions
--------

Added in version 0.1.0.

Examples
--------

Use the system-mode daemon ``qemu:///system`` for all further interactions in the current session:

.. code-block::

   $ export LIBVIRT_DEFAULT_URI=qemu:///system
   $ virtomate domain-list
   [{"name":"my-domain","state":"suspended","uuid":"476ef224-e1ca-4a54-9095-202b11655c80"}]

Connect to a remote host:

.. code-block::

   $ virtomate -c qemu+ssh://ubuntu@10.0.7.3/system domain-list
   [{"name":"remote-domain","state":"running","uuid":"21daf60b-9031-40a9-8e97-37da2998a41b"}]

Pretty-print the output:

.. code-block::

   $ virtomate -p domain-list
   [
     {
       "name": "my-domain",
       "state": "suspended",
       "uuid": "476ef224-e1ca-4a54-9095-202b11655c80"
     }
   ]

Result in case of an error:

.. code-block::

   $ virtomate domain-iface-list unknown
   {"type":"NotFoundError","message":"Domain 'unknown' does not exist"}
   $ echo $?
   1
