virtomate domain-iface-list
===========================

Name
----

virtomate domain-iface-list - List all network interfaces of a running domain.

Synopsis
--------

**virtomate domain-iface-list** [*options*] *domain*

Description
-----------
:program:`virtomate domain-iface-list` lists all network interfaces of the domain named *domain*. The domain named
*domain* must be running for the operation to succeed.

The returned JSON message is a list of :class:`virtomate.domain.InterfaceDescriptor`:

.. autoclass:: virtomate.domain.InterfaceDescriptor
   :members:

.. autoclass:: virtomate.domain.AddressDescriptor
   :members:

The output might be incomplete depending on the source of the address information. See the option ``--source`` for details.

Options
-------

.. program:: virtomate domain-iface-list

.. option:: -h, --help

   Display usage summary of this command and exit.

.. option:: --source

   Select the data source that should be queried to obtain the IP addresses assigned to each network interface. ``lease`` is the default.

   .. describe:: lease

      Consult libvirt's built-in DHCP server. Statically configured addresses will not show up. Likewise, addresses assigned by an external DHCP server will not be included in the output.

   .. describe:: agent

      Query the QEMU Guest Agent for address information. Requires the QEMU Guest Agent to be running on the domain.

   .. describe:: arp

      Use the host's ARP cache to obtain address information. Due to the way ARP operates, the output may contain stale entries. Newly added interfaces show up with a delay. Furthermore, the prefix length (netmask) is always 0 because the ARP cache lacks that information.

Versions
--------

Added in version 0.1.0.

Examples
--------

List all network interfaces of the domain *ubuntu-24.04* as as they are known to libvirt's built-in DHCP server:

.. code-block::

   $ virtomate -p domain-iface-list ubuntu-24.04
   [
     {
       "addresses": [
         {
           "address": "192.168.124.151",
           "prefix": 24,
           "type": "IPv4"
         }
       ],
       "hwaddr": "52:54:00:28:1c:8c",
       "name": "vnet0"
     }
   ]

List all network interfaces of the domain *ubuntu-24.04* as as they are known to the QEMU Guest Agent installed on the guest:

.. code-block::

   $ virtomate -p domain-iface-list --source agent ubuntu-24.04
   [
     {
       "addresses": [
         {
           "address": "127.0.0.1",
           "prefix": 8,
           "type": "IPv4"
         },
         {
           "address": "::1",
           "prefix": 128,
           "type": "IPv6"
         }
       ],
       "hwaddr": "00:00:00:00:00:00",
       "name": "lo"
     },
     {
       "addresses": [
         {
           "address": "192.168.124.151",
           "prefix": 24,
           "type": "IPv4"
         },
         {
           "address": "fe80::5054:ff:fe28:1c8c",
           "prefix": 64,
           "type": "IPv6"
         }
       ],
       "hwaddr": "52:54:00:28:1c:8c",
       "name": "enp1s0"
     },
     {
       "addresses": [
         {
           "address": "192.168.122.1",
           "prefix": 24,
           "type": "IPv4"
         }
       ],
       "hwaddr": "52:54:00:97:9b:5e",
       "name": "virbr0"
     }
   ]

List all network interfaces of the domain *ubuntu-24.04* as as they are known to the host's ARP cache:

.. code-block::

   $ virtomate -p domain-iface-list --source arp ubuntu-24.04
   [
     {
       "addresses": [
         {
           "address": "192.168.124.151",
           "prefix": 0,
           "type": "IPv4"
         }
       ],
       "hwaddr": "52:54:00:28:1c:8c",
       "name": "vnet0"
     }
   ]
