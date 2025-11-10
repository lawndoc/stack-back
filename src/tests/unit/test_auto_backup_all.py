"""Unit tests for AUTO_BACKUP_ALL configuration"""
import unittest
from unittest import mock
import pytest

from restic_compose_backup import config
from restic_compose_backup.containers import RunningContainers
from . import fixtures
from .conftest import BaseTestCase

pytestmark = pytest.mark.unit

list_containers_func = "restic_compose_backup.utils.list_containers"


class AutoBackupAllTests(BaseTestCase):
    """Tests for AUTO_BACKUP_ALL configuration option"""

    def setUp(self):
        super().setUp()
        # Enable AUTO_BACKUP_ALL for each test
        self._original_auto_backup_all = config.config.auto_backup_all
        config.config.auto_backup_all = "true"

    def tearDown(self):
        # Restore original setting after each test
        config.config.auto_backup_all = self._original_auto_backup_all
        super().tearDown()

    def test_all_volumes(self):
        """Test that the AUTO_BACKUP_ALL flag works"""
        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "mounts": [
                    {
                        "Source": "/srv/files/media",
                        "Destination": "/srv/media",
                        "Type": "bind",
                    },
                    {
                        "Source": "/srv/files/stuff",
                        "Destination": "/srv/stuff",
                        "Type": "bind",
                    },
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            cnt = RunningContainers()

        web_service = cnt.get_service("web")
        self.assertNotEqual(web_service, None, msg="Web service not found")

        mounts = web_service.filter_mounts()
        print(mounts)
        self.assertEqual(len(mounts), 2)
        self.assertEqual(mounts[0].source, "/srv/files/media")
        self.assertEqual(mounts[1].source, "/srv/files/stuff")

    def test_all_databases(self):
        """Test that the AUTO_BACKUP_ALL flag intelligently handles databases based on image"""
        containers = self.createContainers()
        containers += [
            {
                "service": "mysql",
                "image": "mysql:8",
                "mounts": [
                    {
                        "Source": "/srv/mysql/data",
                        "Destination": "/var/lib/mysql",
                        "Type": "bind",
                    },
                ],
            },
            {
                "service": "mariadb",
                "image": "mariadb:11",
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
                "image": "postgres:17",
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
        mounts = mysql_service.filter_mounts()
        print(mounts)
        self.assertEqual(len(mounts), 0)

        mariadb_service = cnt.get_service("mariadb")
        self.assertNotEqual(mariadb_service, None, msg="MariaDB service not found")
        self.assertTrue(mariadb_service.mariadb_backup_enabled)
        mounts = mariadb_service.filter_mounts()
        print(mounts)
        self.assertEqual(len(mounts), 0)

        postgres_service = cnt.get_service("postgres")
        self.assertNotEqual(postgres_service, None, msg="Postgres service not found")
        self.assertTrue(postgres_service.postgresql_backup_enabled)
        mounts = postgres_service.filter_mounts()
        print(mounts)
        self.assertEqual(len(mounts), 0)

    def test_redundant_volume_label(self):
        """Test that a container has a redundant volume label should be backed up"""

        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "labels": {
                    "stack-back.volumes": True,
                },
                "mounts": [
                    {
                        "Source": "/srv/files/media",
                        "Destination": "/srv/media",
                        "Type": "bind",
                    },
                    {
                        "Source": "/srv/files/stuff",
                        "Destination": "/srv/stuff",
                        "Type": "bind",
                    },
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            cnt = RunningContainers()

        web_service = cnt.get_service("web")
        self.assertNotEqual(web_service, None, msg="Web service not found")

        mounts = web_service.filter_mounts()
        print(mounts)
        self.assertEqual(len(mounts), 2)
        self.assertEqual(mounts[0].source, "/srv/files/media")
        self.assertEqual(mounts[1].source, "/srv/files/stuff")

    def test_redundant_database_label(self):
        """Test that a container has a redundant database label should be backed up"""
        containers = self.createContainers()
        containers += [
            {
                "service": "mysql",
                "image": "mysql:8",
                "labels": {
                    "stack-back.mysql": True,
                },
                "mounts": [
                    {
                        "Source": "/srv/mysql/data",
                        "Destination": "/var/lib/mysql",
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
        mounts = mysql_service.filter_mounts()
        print(mounts)
        self.assertEqual(len(mounts), 0)

    def test_explicit_volumes_exclude(self):
        """Test that a container's volumes can be excluded from the backup"""

        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "labels": {
                    "stack-back.volumes": False,
                },
                "mounts": [
                    {
                        "Source": "/srv/files/media",
                        "Destination": "/srv/media",
                        "Type": "bind",
                    },
                    {
                        "Source": "/srv/files/stuff",
                        "Destination": "/srv/stuff",
                        "Type": "bind",
                    },
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            cnt = RunningContainers()

        web_service = cnt.get_service("web")
        self.assertNotEqual(web_service, None, msg="Web service not found")

        mounts = web_service.filter_mounts()
        print(mounts)
        self.assertEqual(len(mounts), 0)

    def test_specific_volume_exclude(self):
        """Test that a specific volume can be excluded from the backup"""

        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "labels": {
                    "stack-back.volumes.exclude": "stuff",
                },
                "mounts": [
                    {
                        "Source": "/srv/files/media",
                        "Destination": "/srv/media",
                        "Type": "bind",
                    },
                    {
                        "Source": "/srv/files/stuff",
                        "Destination": "/srv/stuff",
                        "Type": "bind",
                    },
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            cnt = RunningContainers()

        web_service = cnt.get_service("web")
        self.assertNotEqual(web_service, None, msg="Web service not found")

        mounts = web_service.filter_mounts()
        print(mounts)
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0].source, "/srv/files/media")

    def test_specific_database_exclude(self):
        """Test that a database container can be excluded from the backup"""
        containers = self.createContainers()
        containers += [
            {
                "service": "mysql",
                "labels": {
                    "stack-back.mysql": False,
                    "stack-back.volumes": False,
                },
                "mounts": [
                    {
                        "Source": "/srv/mysql/data",
                        "Destination": "/var/lib/mysql",
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
        self.assertFalse(mysql_service.mysql_backup_enabled)
        mounts = mysql_service.filter_mounts()
        print(mounts)
        self.assertEqual(len(mounts), 0)
