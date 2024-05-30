import random

from libvirt import virConnect
import pytest

from tests.resources import resource_content
from virtomate import LibvirtMACFactory


class TestLibvirtMACFactory:
    def test_create_from(self, test_connection: virConnect) -> None:
        rnd = random.Random()
        rnd.seed(37)

        mac_factory = LibvirtMACFactory(test_connection, rnd=rnd)

        assert mac_factory.create_from("52:54:00:4c:4e:25") == "52:54:00:2e:12:bd"
        assert mac_factory.create_from("52:54:00:4c:4e:25") == "52:54:00:e0:37:e9"
        assert mac_factory.create_from("00:00:00:00:00:00") == "00:00:00:90:c1:d8"

        with pytest.raises(ValueError) as excinfo:
            mac_factory.create_from("_")

        assert str(excinfo.value) == "Invalid MAC address: _"

        with pytest.raises(ValueError) as excinfo:
            mac_factory.create_from("z0:00:00:00:00:00")

        assert str(excinfo.value) == "Invalid MAC address: z0:00:00:00:00:00"

    def test_create_from_collision_avoidance(self, test_connection: virConnect) -> None:
        rnd = random.Random()
        rnd.seed(37)

        test_connection.defineXML(resource_content("simple-uefi.xml"))
        mac_factory = LibvirtMACFactory(test_connection, rnd=rnd)

        assert mac_factory.create_from("52:54:00:4c:4e:25") == "52:54:00:e0:37:e9"
        assert mac_factory._attempts == 2
