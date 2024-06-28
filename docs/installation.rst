.. _installation:

Installation
============

Requirements
------------

Virtomate requires the following software to be present on your system in order to run:

- `Python 3.10 <https://python.org/>`_ (or newer)
- `libvirt 9.0 <https://libvirt.org/>`_ (or newer)
- `qemu-img <https://www.qemu.org/docs/master/tools/qemu-img.html>`_

It works on Linux, macOS, and `Windows Subsystem for Linux <https://learn.microsoft.com/en-us/windows/wsl/>`_ (WSL) running on any CPU architecture as long as Virtomate's requirements are met.

With pipx
---------

:program:`pipx` installs and runs Python applications like Virtomate in isolated environments. Please see the `pipx documentation <https://pipx.pypa.io/>`_ for how to install ``pipx``.

.. code-block::

    $ pipx install -U virtomate
