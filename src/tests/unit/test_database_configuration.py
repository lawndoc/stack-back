"""Unit tests for database backup configuration"""

import unittest
from unittest import mock
import pytest

from restic_compose_backup.containers import RunningContainers
from . import fixtures
from .conftest import BaseTestCase

pytestmark = pytest.mark.unit

list_containers_func = "restic_compose_backup.utils.list_containers"


class DatabaseConfigurationTests(BaseTestCase):
    """Tests for database backup configuration"""

    def test_databases_for_backup(self):
        """Test identifying databases marked for backup"""
        containers = self.createContainers()
        containers += [
            {
                "service": "mysql",
                "labels": {
                    "stack-back.mysql": True,
                },
                "mounts": [
                    {
                        "Source": "/srv/mysql/data",
                        "Destination": "/var/lib/mysql",
                        "Type": "bind",
                    }
                ],
            },
            {
                "service": "mariadb",
                "labels": {
                    "stack-back.mariadb": True,
                },
                "mounts": [
                    {
                        "Source": "/srv/mariadb/data",
                        "Destination": "/var/lib/mysql",
                        "Type": "bind",
                    },
                ],
            },
            {
                "service": "postgres",
                "labels": {
                    "stack-back.postgres": True,
                },
                "mounts": [
                    {
                        "Source": "/srv/postgres/data",
                        "Destination": "/var/lib/postgresql/data",
                        "Type": "bind",
                    },
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            cnt = RunningContainers()
        mysql_service = cnt.get_service("mysql")
        self.assertNotEqual(mysql_service, None, msg="MySQL service not found")
        self.assertTrue(mysql_service.mysql_backup_enabled)
        mariadb_service = cnt.get_service("mariadb")
        self.assertNotEqual(mariadb_service, None, msg="MariaDB service not found")
        self.assertTrue(mariadb_service.mariadb_backup_enabled)
        postgres_service = cnt.get_service("postgres")
        self.assertNotEqual(postgres_service, None, msg="Posgres service not found")
        self.assertTrue(postgres_service.postgresql_backup_enabled)

    def test_stop_container_during_backup_database(self):
        """Test that stop-during-backup label doesn't apply to databases"""
        containers = self.createContainers()
        containers += [
            {
                "service": "mysql",
                "labels": {
                    "stack-back.mysql": True,
                    "stack-back.volumes.stop-during-backup": True,
                },
                "mounts": [
                    {
                        "Source": "/srv/mysql/data",
                        "Destination": "/var/lib/mysql",
                        "Type": "bind",
                    }
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            cnt = RunningContainers()
        mysql_service = cnt.get_service("mysql")
        self.assertNotEqual(mysql_service, None, msg="MySQL service not found")
        self.assertTrue(mysql_service.mysql_backup_enabled)
        self.assertFalse(mysql_service.stop_during_backup)
