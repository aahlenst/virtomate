.. _installation:

Installation
============

Requirements
------------

Virtomate requires the following software to be present on your system:

- `Python 3.10 <https://python.org/>`_ (or newer)
- `libvirt 9.0 <https://libvirt.org/>`_ (or newer)
- `qemu-img <https://www.qemu.org/docs/master/tools/qemu-img.html>`_

It runs on Linux, macOS, and `Windows Subsystem for Linux <https://learn.microsoft.com/en-us/windows/wsl/>`_ (WSL). It should be compatible with any CPU architecture as long as its requirements are met.

With pipx
---------

:program:`pipx` installs and runs Python applications like Virtomate in isolated environments. Please see the `pipx documentation <https://pipx.pypa.io/>`_ for how to install :program:`pipx`.

To install Virtomate with :program:`pipx`, run:

.. code-block::

    $ pipx install virtomate
