import os
import unittest
from unittest import mock

os.environ["RESTIC_REPOSITORY"] = "test"
os.environ["RESTIC_PASSWORD"] = "password"

from restic_compose_backup import utils, config
from restic_compose_backup.containers import RunningContainers
import fixtures

list_containers_func = "restic_compose_backup.utils.list_containers"


class BaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backup_hash = fixtures.generate_sha256()

        cls.hostname_patcher = mock.patch(
            "socket.gethostname", return_value=cls.backup_hash[:8]
        )
        cls.hostname_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.hostname_patcher.stop()

    def createContainers(self):
        return [
            {
                "id": self.backup_hash,
                "service": "backup",
            }
        ]


class ResticBackupTests(BaseTestCase):
    def test_list_containers(self):
        """Test a basic container list"""
        containers = [
            {
                "service": "web",
                "labels": {
                    "moo": 1,
                },
                "mounts": [
                    {
                        "Source": "moo",
                        "Destination": "moo",
                        "Type": "bind",
                    }
                ],
            },
            {
                "service": "mysql",
            },
            {
                "service": "postgres",
            },
        ]

        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            test = utils.list_containers()

    def test_running_containers(self):
        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "labels": {
                    "stack-back.volumes": True,
                    "test": "test",
                },
                "mounts": [
                    {
                        "Source": "test",
                        "Destination": "test",
                        "Type": "bind",
                    }
                ],
            },
            {
                "service": "mysql",
            },
            {
                "service": "postgres",
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            result = RunningContainers()
            self.assertEqual(len(result.containers), 4, msg="Three containers expected")
            self.assertNotEqual(
                result.this_container, None, msg="No backup container found"
            )
            web_service = result.get_service("web")
            self.assertNotEqual(web_service, None)
            self.assertEqual(len(web_service.filter_mounts()), 1)

    def test_volumes_for_backup(self):
        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "labels": {
                    "stack-back.volumes": True,
                },
                "mounts": [
                    {
                        "Source": "test",
                        "Destination": "test",
                        "Type": "bind",
                    }
                ],
            },
            {
                "service": "mysql",
                "labels": {
                    "stack-back.mysql": True,
                },
                "mounts": [
                    {
                        "Source": "data",
                        "Destination": "data",
                        "Type": "bind",
                    }
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            cnt = RunningContainers()
            self.assertTrue(len(cnt.containers_for_backup()) == 2)
            self.assertEqual(
                cnt.generate_backup_mounts(),
                {"test": {"bind": "/volumes/web/test", "mode": "ro"}},
            )
        mysql_service = cnt.get_service("mysql")
        self.assertNotEqual(mysql_service, None, msg="MySQL service not found")
        mounts = mysql_service.filter_mounts()
        print(mounts)
        self.assertTrue(mysql_service.mysql_backup_enabled)
        self.assertEqual(len(mounts), 0)

    def test_no_volumes_for_backup(self):
        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "labels": {
                    "stack-back.volumes": True,
                },
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            cnt = RunningContainers()
            self.assertTrue(len(cnt.containers_for_backup()) == 1)
        web_service = cnt.get_service("web")
        self.assertNotEqual(web_service, None, msg="Web service not found")
        mounts = web_service.filter_mounts()
        print(mounts)
        self.assertEqual(len(mounts), 0)

    def test_databases_for_backup(self):
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

    def test_include(self):
        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "labels": {
                    "stack-back.volumes": True,
                    "stack-back.volumes.include": "media",
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

    def test_exclude(self):
        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "labels": {
                    "stack-back.volumes": True,
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
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0].source, "/srv/files/media")

    def test_find_running_backup_container(self):
        containers = self.createContainers()
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            cnt = RunningContainers()
            self.assertFalse(cnt.backup_process_running)

        containers += [
            {
                "service": "backup_runner",
                "labels": {
                    "stack-back.process-default": "True",
                },
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            cnt = RunningContainers()
            self.assertTrue(cnt.backup_process_running)

    def test_stop_container_during_backup_volume(self):
        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "labels": {
                    "stack-back.volumes": True,
                    "stack-back.volumes.include": "sqlite",
                    "stack-back.volumes.stop-during-backup": True,
                },
                "mounts": [
                    {
                        "Source": "/srv/files/media",
                        "Destination": "/srv/media",
                        "Type": "bind",
                    },
                    {
                        "Source": "/srv/files/sqlite",
                        "Destination": "/srv/sqlite",
                        "Type": "bind",
                    },
                ],
            }
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            cnt = RunningContainers()
        web_service = cnt.get_service("web")
        self.assertNotEqual(web_service, None, msg="Web service not found")
        self.assertTrue(web_service.stop_during_backup)

    def test_stop_container_during_backup_database(self):
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


class IncludeAllVolumesTests(BaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        config.config.auto_backup_all = "true"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        config.config = config.Config()

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
