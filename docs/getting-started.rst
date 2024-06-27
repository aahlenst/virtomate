.. _getting-started:

Getting Started
===============

Once you have :doc:`installed <installation>` Virtomate, you can see all commands and options by running

.. code-block::

    $ virtomate --help

To list all domains on your system, run

.. code-block::

    $ virtomate domain-list
    []

Virtomate always returns `JSON <https://www.json.org/>`_. ``[]`` is an empty list. This means that there is no domain.

Because Virtomate relies on `libvirt <https://libvirt.org/>`_, it connects to the session-mode daemon ``qemu:///session`` by default. If you want to connect to another instance, you can either define the environment variable ``LIBVIRT_DEFAULT_URI`` or use the command-line option ``-c``:

.. code-block::

    $ LIBVIRT_DEFAULT_URI=qemu:///system virtomate domain-list
    []
    $ virtomate -c qemu:///system domain-list
    []

Both are equivalent.

.. tip::

    If you get an error accessing the system-mode daemon ``qemu:///system`` as a normal user, you can either use ``sudo`` or add yourself to the user group ``libvirt``. Members of ``libvirt`` usually have password-less access to the system-mode daemon. Please refer to the documentation for your operating system.

If your virtual machines are running on a different host, you can connect to it using SSH:

.. code-block::

    $ virtomate -c qemu+ssh://ubuntu@10.0.7.3/system -p domain-list
    [{"name":"ubuntu-24.04","state":"running","uuid":"b901fbbb-1012-495d-a32d-90a8ddaa50a7"},{"name":"debian-12","state":"suspended","uuid":"5ba9232a-1694-4d8b-b40d-e32f710c22a2"}]

Here, we see a result for the first time. It is not exactly easy to read because JSON is meant to be parsed by another tool like `jq <https://jqlang.github.io/jq/>`_. But that can be changed with the command-line option ``-p`` (like in "pretty"):

.. code-block::

    $ virtomate -c qemu+ssh://ubuntu@10.0.7.3/system -p domain-list
    [
      {
        "name": "ubuntu-24.04",
        "state": "running",
        "uuid": "b901fbbb-1012-495d-a32d-90a8ddaa50a7"
      },
      {
        "name": "debian-12",
        "state": "suspended",
        "uuid": "5ba9232a-1694-4d8b-b40d-e32f710c22a2"
      }
    ]

That's much better!

As mentioned, Virtomate returns JSON that is meant to be parsed by other tools. `jq <https://jqlang.github.io/jq/>`_ is an excellent choice for that. Assume you are only interested in the name of each running virtual machine:

.. code-block::

    $ virtomate domain-list | jq 'map(select(.state | contains("running"))) | .[].name'
    "ubuntu-24.04"

You are now only an ``xargs`` away from shutting down all virtual machines that are running:

.. code-block::

    $ virtomate domain-list | jq 'map(select(.state | contains("running"))) | .[].name' | xargs -i virsh destroy --graceful {}
    Domain 'ubuntu-24.04' destroyed

That is far from everything Virtomate has to offer. Check the man pages to see what else it can do for you!
