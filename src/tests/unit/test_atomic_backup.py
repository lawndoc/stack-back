"""Unit tests for atomic backup feature (ATOMIC_BACKUP env var)"""

import os
import unittest
from unittest import mock
from pathlib import Path
import pytest

from restic_compose_backup.config import Config
from restic_compose_backup.containers import RunningContainers
from restic_compose_backup import restic, utils
from . import fixtures
from .conftest import BaseTestCase

pytestmark = pytest.mark.unit

list_containers_func = "restic_compose_backup.utils.list_containers"


class AtomicBackupConfigTests(BaseTestCase):
    """Tests for ATOMIC_BACKUP configuration"""

    def test_atomic_backup_default_false(self):
        """ATOMIC_BACKUP defaults to False when not set"""
        env = os.environ.copy()
        env.pop("ATOMIC_BACKUP", None)
        with mock.patch.dict(os.environ, env, clear=True):
            config = Config(check=False)
        self.assertFalse(utils.is_true(config.atomic_backup))

    def test_atomic_backup_enabled(self):
        """ATOMIC_BACKUP can be enabled via env var"""
        with utils.environment("ATOMIC_BACKUP", "true"):
            config = Config(check=False)
        self.assertTrue(utils.is_true(config.atomic_backup))

    def test_atomic_backup_enabled_numeric(self):
        """ATOMIC_BACKUP accepts '1' as truthy"""
        with utils.environment("ATOMIC_BACKUP", "1"):
            config = Config(check=False)
        self.assertTrue(utils.is_true(config.atomic_backup))


class AtomicBackupDumpPathTests(BaseTestCase):
    """Tests that dump_to_file destination paths match backup_destination_path"""

    def _make_mariadb_container(self, project="default", service="mariadb"):
        """Helper to create a MariaDB container instance."""
        containers = self.createContainers()
        containers.append(
            {
                "service": service,
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
                "env": [
                    "MARIADB_ROOT_PASSWORD=secret",
                ],
            },
        )
        with mock.patch(
            list_containers_func,
            fixtures.containers(project=project, containers=containers),
        ):
            cnt = RunningContainers()
        svc = cnt.get_service(service)
        return svc.instance

    def _make_mysql_container(self, project="default", service="mysql"):
        """Helper to create a MySQL container instance."""
        containers = self.createContainers()
        containers.append(
            {
                "service": service,
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
                "env": [
                    "MYSQL_ROOT_PASSWORD=secret",
                ],
            },
        )
        with mock.patch(
            list_containers_func,
            fixtures.containers(project=project, containers=containers),
        ):
            cnt = RunningContainers()
        svc = cnt.get_service(service)
        return svc.instance

    def _make_postgres_container(self, project="default", service="postgres"):
        """Helper to create a PostgreSQL container instance."""
        containers = self.createContainers()
        containers.append(
            {
                "service": service,
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
                "env": [
                    "POSTGRES_USER=pguser",
                    "POSTGRES_PASSWORD=pgpass",
                    "POSTGRES_DB=mydb",
                ],
            },
        )
        with mock.patch(
            list_containers_func,
            fixtures.containers(project=project, containers=containers),
        ):
            cnt = RunningContainers()
        svc = cnt.get_service(service)
        return svc.instance

    def test_mariadb_backup_destination_path(self):
        """MariaDB dump path lives under /databases/"""
        instance = self._make_mariadb_container()
        path = Path(str(instance.backup_destination_path()))
        self.assertIn("databases", path.parts)
        self.assertEqual(path.name, "all_databases.sql")

    def test_mysql_backup_destination_path(self):
        """MySQL dump path lives under /databases/"""
        instance = self._make_mysql_container()
        path = Path(str(instance.backup_destination_path()))
        self.assertIn("databases", path.parts)
        self.assertEqual(path.name, "all_databases.sql")

    def test_postgres_backup_destination_path(self):
        """PostgreSQL dump path lives under /databases/"""
        instance = self._make_postgres_container()
        path = Path(str(instance.backup_destination_path()))
        self.assertIn("databases", path.parts)
        self.assertTrue(path.name.endswith(".sql"))

    def test_mariadb_dump_to_file_calls_docker_exec_to_file(self):
        """dump_to_file() delegates to commands.docker_exec_to_file with correct args"""
        instance = self._make_mariadb_container()
        with mock.patch(
            "restic_compose_backup.commands.docker_exec_to_file", return_value=0
        ) as mock_exec:
            result = instance.dump_to_file()
        self.assertEqual(result, 0)
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        # Verify file_path matches backup_destination_path
        self.assertEqual(
            call_args[0][2], str(instance.backup_destination_path())
        )
        # Verify MYSQL_PWD is passed
        self.assertIn("MYSQL_PWD", call_args[1].get("environment", {}))

    def test_mysql_dump_to_file_calls_docker_exec_to_file(self):
        """dump_to_file() delegates to commands.docker_exec_to_file with correct args"""
        instance = self._make_mysql_container()
        with mock.patch(
            "restic_compose_backup.commands.docker_exec_to_file", return_value=0
        ) as mock_exec:
            result = instance.dump_to_file()
        self.assertEqual(result, 0)
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        self.assertEqual(
            call_args[0][2], str(instance.backup_destination_path())
        )
        self.assertIn("MYSQL_PWD", call_args[1].get("environment", {}))

    def test_postgres_dump_to_file_calls_docker_exec_to_file(self):
        """dump_to_file() delegates to commands.docker_exec_to_file with correct args"""
        instance = self._make_postgres_container()
        with mock.patch(
            "restic_compose_backup.commands.docker_exec_to_file", return_value=0
        ) as mock_exec:
            result = instance.dump_to_file()
        self.assertEqual(result, 0)
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        self.assertEqual(
            call_args[0][2], str(instance.backup_destination_path())
        )


class ResticBackupFilesTests(BaseTestCase):
    """Tests for restic.backup_files accepting single and multiple sources"""

    @mock.patch("restic_compose_backup.commands.run", return_value=0)
    def test_single_source_string(self, mock_run):
        """backup_files with a string source passes it as a single path"""
        restic.backup_files("repo", source="/volumes")
        cmd = mock_run.call_args[0][0]
        self.assertIn("/volumes", cmd)
        # Only one source path
        idx = cmd.index("backup")
        sources = cmd[idx + 1 :]
        self.assertEqual(sources, ["/volumes"])

    @mock.patch("restic_compose_backup.commands.run", return_value=0)
    def test_multiple_sources_list(self, mock_run):
        """backup_files with a list passes all paths to restic"""
        restic.backup_files("repo", source=["/volumes", "/databases"])
        cmd = mock_run.call_args[0][0]
        idx = cmd.index("backup")
        sources = cmd[idx + 1 :]
        self.assertEqual(sources, ["/volumes", "/databases"])

    @mock.patch("restic_compose_backup.commands.run", return_value=0)
    def test_single_source_default(self, mock_run):
        """backup_files default source is /volumes"""
        restic.backup_files("repo")
        cmd = mock_run.call_args[0][0]
        idx = cmd.index("backup")
        sources = cmd[idx + 1 :]
        self.assertEqual(sources, ["/volumes"])



