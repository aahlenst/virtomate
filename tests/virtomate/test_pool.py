from libvirt import virConnect

from virtomate.pool import pool_exists


class TestPoolExists:
    def test(self, test_connection: virConnect) -> None:
        assert pool_exists(test_connection, "default-pool") is True
        assert pool_exists(test_connection, "unknown") is False
