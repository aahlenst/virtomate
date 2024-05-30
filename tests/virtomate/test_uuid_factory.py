import random
from uuid import UUID

from libvirt import virConnect

from tests.resources import resource_content
from virtomate import LibvirtUUIDFactory


class TestLibvirtUUIDFactory:
    def test_create(self, test_connection: virConnect) -> None:
        rnd = random.Random()
        rnd.seed(37)

        uuid_factory = LibvirtUUIDFactory(test_connection, rnd=rnd)

        assert uuid_factory.create() == UUID(hex="ef70b4c0-1773-44a3-9b95-f239ae97d9db")
        assert uuid_factory.create() == UUID(hex="bf2eb110-d788-4003-aa59-ce1e9e293641")

    def test_create_collision_avoidance(self, test_connection: virConnect) -> None:
        rnd = random.Random()
        rnd.seed(37)

        test_connection.defineXML(resource_content("simple-uefi.xml"))
        uuid_factory = LibvirtUUIDFactory(test_connection, rnd=rnd)

        assert uuid_factory.create() == UUID(hex="bf2eb110-d788-4003-aa59-ce1e9e293641")
        assert uuid_factory._attempts == 2
