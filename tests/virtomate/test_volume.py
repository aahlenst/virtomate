import libvirt
import pytest
from libvirt import virConnect

from virtomate.volume import list_volumes


class TestListVolumes:
    def test_list_volumes_empty_pool(self, test_connection: virConnect) -> None:
        assert list_volumes(test_connection, "default-pool") == []

    def test_list_volumes_nonexistent_pool(self, test_connection: virConnect) -> None:
        with pytest.raises(libvirt.libvirtError) as ex:
            list_volumes(test_connection, "does-not-exist")

        assert (
            str(ex.value)
            == "Storage pool not found: no storage pool with matching name 'does-not-exist'"
        )

    def test_list_volumes(self, test_connection: virConnect) -> None:
        raw_volume_xml = """
        <volume>
            <name>raw-volume</name>
            <capacity unit="bytes">10737418240</capacity>
            <target>
                <format type="raw"/>
            </target>
        </volume>
        """

        linked_volume_xml = """
        <volume>
            <name>linked-volume</name>
            <capacity unit="bytes">10737418240</capacity>
            <target>
                <format type="qcow2"/>
            </target>
            <backingStore>
                <path>/default-pool/my-volume</path>
                <format type='raw'/>
            </backingStore>
        </volume>
        """

        default_pool = test_connection.storagePoolLookupByName("default-pool")
        default_pool.createXML(raw_volume_xml)
        default_pool.createXML(linked_volume_xml)

        assert list_volumes(test_connection, "default-pool") == [
            {
                "allocation": 10737418240,
                "backing_store": {
                    "format_type": "raw",
                    "path": "/default-pool/my-volume",
                },
                "capacity": 10737418240,
                "key": "/default-pool/linked-volume",
                "name": "linked-volume",
                "physical": None,
                "target": {
                    "format_type": "qcow2",
                    "path": "/default-pool/linked-volume",
                },
                "type": "file",
            },
            {
                "allocation": 10737418240,
                "backing_store": None,
                "capacity": 10737418240,
                "key": "/default-pool/raw-volume",
                "name": "raw-volume",
                "physical": None,
                "target": {
                    "format_type": "raw",
                    "path": "/default-pool/raw-volume",
                },
                "type": "file",
            },
        ]
