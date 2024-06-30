virtomate guest-run
===================

Name
----

virtomate guest-run - Run a program in a domain through the QEMU Guest Agent.

Synopsis
--------

**virtomate guest-run** [*options*] *domain* *program* [*arguments*]

Description
-----------
:program:`virtomate guest-run` runs *program* with the given *arguments* in *domain*. *program* is started by the QEMU Guest Agent running in *domain* on behalf of :program:`virtomate guest-run`. The results of the program are returned as JSON message with the following structure:

.. autoclass:: virtomate.guest.RunResult
   :members:

:program:`virtomate guest-run` waits for *program* to complete before returning a result.

The exit status of :program:`virtomate guest-run` is unaffected by the exit status of *program*. :program:`virtomate guest-run` will only exit with a non-zero status if it could not start *program*, for example, because it does not exist or the QEMU Guest Agent is not running.

*program* is started by the QEMU Guest Agent using an :manpage:`exit(3)`-like function. This means no shell is involved when starting *program*. To use shell-builtins like ``|`` in your command to run in *domain*, you have to explicitly invoke a shell as *program*. Please see the examples below for how to do it.

While you can pass standard input to *program* and receive standard output as well as standard error, note that those are completely buffered in memory before being transferred back and forth between the host and the guest. Consequently, it would be very inefficient to transfer larger volumes of data between the host and the guest. Furthermore, the amount of data that can be transferred between the host and the guest is limited to a few megabytes by libvirt.

QEMU Guest Agent itself limits the size of standard output and standard error to 16 megabytes. If standard output or standard error were larger, QEMU Guest Agent would truncate them and indicate that in the result.

Options
-------

.. program:: virtomate guest-run

.. option:: -h, --help

   Display usage summary of this command and exit.

.. option:: -e, --encode

   Encode output with Base64.

.. option:: --stdin

   Consume standard input and pass it to *program*. Due to way QEMU Guest Agent operates, standard input is buffered in memory before being passed to *program* at once.

Versions
--------

Added in version 0.1.0.

Examples
--------

Run :code:`echo -n "Hello World"` on *my-domain*:

.. code-block::

   $ virtomate -p guest-run my-domain -- echo -n "Hello World"
   {
     "exit_code": 0,
     "signal": null,
     "stderr": null,
     "stderr_truncated": false,
     "stdout": "Hello World",
     "stdout_truncated": false
   }

.. note::

   The double dash (``--``) signifies the end of command options. It is required to distinguish options meant for :program:`virtomate` from those for *program* to be run in the guest. While the exact position of ``--`` does not matter, it is recommended to place it directly before *program*.

Run :code:`echo -n "Hello World"` on *my-domain* and return standard output and standard error encoded with Base64:

.. code-block::

   $ virtomate -p guest-run --encode my-domain -- echo -n "Hello World"
   {
     "exit_code": 0,
     "signal": null,
     "stderr": null,
     "stderr_truncated": false,
     "stdout": "SGVsbG8gV29ybGQ=",
     "stdout_truncated": false
   }

:code:`echo -n 'SGVsbG8gV29ybGQ=' | base64 -d` prints "Hello World".

If you run a program that fails, its exit status and standard error are included in the JSON message. The exit status of :program:`virtomate guest-run` remains 0 because Virtomate could successfully start the program:

.. code-block::

   $ virtomate -p guest-run my-domain -- cat /does/not/exist
   {
     "exit_code": 1,
     "signal": null,
     "stderr": "cat: /does/not/exist: No such file or directory\n",
     "stderr_truncated": false,
     "stdout": null,
     "stdout_truncated": false
   }

This is different from trying to run a program that cannot be started:

.. code-block::

   $ virtomate -p guest-run my-domain -- /does/not/exist
   {
     "message": "internal error: unable to execute QEMU agent command 'guest-exec': Guest agent command failed, error was 'Failed to execute child process \u201c/does/not/exist\u201d (No such file or directory)'",
     "type": "libvirtError"
   }

Because the program ``/does/not/exist`` does not exist, :program:`virtomate guest-run` cannot start it. Hence, it returns an error and the exit status is 1.

To run a shell command, you have to invoke the shell explicitly. For example, to count the characters in the string "Hello World", run:

.. code-block::

   $ virtomate -p guest-run my-domain -- \
       /usr/bin/env bash -c 'printf "Hello World" | wc -m'
   {
     "exit_code": 0,
     "signal": null,
     "stderr": null,
     "stderr_truncated": false,
     "stdout": "11\n",
     "stdout_truncated": false
   }

You can also print "Hello World" on the guest and count the characters in the guest by passing "Hello World" via standard input to :manpage:`wc(1)`:

.. code-block::

   $ printf "Hello World" | virtomate -p guest-run --stdin my-domain -- wc -m
   {
     "exit_code": 0,
     "signal": null,
     "stderr": null,
     "stderr_truncated": false,
     "stdout": "11\n",
     "stdout_truncated": false
   }
