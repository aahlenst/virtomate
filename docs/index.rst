:orphan:

Virtomate
=========

Virtomate is a handy command-line application for automating virtual machines with `libvirt <https://libvirt.org/>`_. It features a scripting-friendly interface with JSON output. Furthermore, it reduces complex tasks like cloning virtual machines or importing volumes to a single step. Virtomate runs on any Unix-like system with Python 3.10 and libvirt 9.0 (or newer) installed.

**PyPI package name**: :pypi:`virtomate`

At a Glance
-----------

Accomplish complex tasks like cloning virtual machines with ease:

.. code-block::

    $ virtomate domain-clone --mode linked ubuntu-24.04 my-clone

Or run a command on the guest without SSH:

.. code-block::

    $ virtomate -p guest-run ubuntu-24.04 -- apt-get update
    {
      "exit_code": 0,
      "signal": null,
      "stderr": null,
      "stderr_truncated": false,
      "stdout": "Hit:1 http://archive.ubuntu.com/ubuntu noble InRelease\nHit:2 http://archive.ubuntu.com/ubuntu noble-updates InRelease\nHit:3 http://archive.ubuntu.com/ubuntu noble-backports InRelease\nHit:4 http://security.ubuntu.com/ubuntu noble-security InRelease\nReading package lists...\n",
      "stdout_truncated": false
    }

Virtomate's scripting-friendly interface makes automating administrative tasks a breeze. Pipe its JSON output to `jq <https://github.com/jqlang/jq>`_ to extract the information you need and combine it with any other tool. Emptying a storage pool becomes a single line of code:

.. code-block::

    $ virtomate volume-list boot | jq '.[].name' | xargs -i virsh vol-delete {} --pool boot

Even if virtual machines are running on a remote host, don't let that stop you. Virtomate can connect to other hosts using `remote URIs <https://libvirt.org/uri.html>`_:

.. code-block::

    $ virtomate -c qemu+ssh://ubuntu@10.0.7.3/system -p domain-list
    [
      {
        "name": "ubuntu-24.04",
        "state": "running",
        "uuid": "b901fbbb-1012-495d-a32d-90a8ddaa50a7"
      }
    ]

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Documentation

   installation
   getting-started
   man/index

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Project

   Source Code <https://github.com/aahlenst/virtomate>
