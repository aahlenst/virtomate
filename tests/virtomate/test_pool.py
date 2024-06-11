from libvirt import virConnect

from virtomate.pool import pool_exists, list_pools


class TestPoolExists:
    def test(self, test_connection: virConnect) -> None:
        assert pool_exists(test_connection, "default-pool") is True
        assert pool_exists(test_connection, "unknown") is False


class TestListPools:
    def test(self, test_connection: virConnect) -> None:
        # 2 GiB
        raw_volume_xml = """
        <volume>
            <name>raw-volume</name>
            <capacity unit="bytes">2147483648</capacity>
            <target>
                <format type="raw"/>
            </target>
        </volume>
        """

        assert list_pools(test_connection) == [
            {
                "active": True,
                "allocation": 0,
                "available": 107374182400,
                "capacity": 107374182400,
                "name": "default-pool",
                "number_of_volumes": 0,
                "persistent": True,
                "state": "running",
                "uuid": "dfe224cb-28fb-8dd0-c4b2-64eb3f0f4566",
            }
        ]

        default_pool = test_connection.storagePoolLookupByName("default-pool")
        default_pool.createXML(raw_volume_xml)

        assert list_pools(test_connection) == [
            {
                "active": True,
                "allocation": 2147483648,
                "available": 105226698752,
                "capacity": 107374182400,
                "name": "default-pool",
                "number_of_volumes": 1,
                "persistent": True,
                "state": "running",
                "uuid": "dfe224cb-28fb-8dd0-c4b2-64eb3f0f4566",
            }
        ]

        default_pool.destroy()

        assert list_pools(test_connection) == [
            {
                "active": False,
                "allocation": 2147483648,
                "available": 105226698752,
                "capacity": 107374182400,
                "name": "default-pool",
                "number_of_volumes": None,
                "persistent": True,
                "state": "inactive",
                "uuid": "dfe224cb-28fb-8dd0-c4b2-64eb3f0f4566",
            }
        ]

        default_pool.delete()
        default_pool.undefine()

        assert list_pools(test_connection) == []
