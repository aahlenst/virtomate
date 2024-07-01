virtomate guest-ping
====================

Name
----

virtomate guest-ping - Check whether the QEMU Guest Agent is running.

Synopsis
--------

**virtomate guest-ping** [*options*] *domain*

Description
-----------
:program:`virtomate guest-ping` tries to ping the QEMU Guest Agent running on *domain*. It exits with status 0 if the QEMU Guest Agent responded. If the QEMU Guest Agent did not respond, it exits with status 125.

Options
-------

.. program:: virtomate guest-ping

.. option:: -h, --help

   Display usage summary of this command and exit.

.. option:: --wait N

   Wait for *N* seconds for the QEMU Guest Agent to respond. The default is not to wait. Fractional seconds are supported, for example, ``0.5``.

Exit Status
-----------

:program:`virtomate guest-ping` exits with status 0 if the QEMU Guest Agent responded, non-zero on error.

Details about the error statuses:

1
   Indicates an operation error; a JSON error message will be printed to standard output.

2
   Indicates an usage error; usage information will be printed to standard error.

125
   The QEMU Guest Agent did not respond.

Versions
--------

Added in version 0.1.0.

Examples
--------

Print "my-domain is reachable" when the QEMU Guest Agent is reachable, print "my-domain is unreachable" if it is not:

.. code-block:: bash

   #! /usr/bin/env bash
   set -eu

   ret=0
   virtomate guest-ping my-domain || ret=$?
   case $ret in
       0)   printf "my-domain is reachable" ;;
       125) printf "my-domain is unreachable" ;;
       *)   ;;
   esac
   exit $ret

This example preserves the exit code of :code:`virtomate guest-ping my-domain` as well as the original error messages.

Wait at most 60 seconds for the QEMU Guest Agent on *my-domain* to respond:

.. code-block::

   $ virtomate guest-ping --wait 60 my-domain
   $ echo $?
   0
