"""Unit tests for container operations"""

import unittest
from unittest import mock
import pytest

from restic_compose_backup import utils
from restic_compose_backup.containers import RunningContainers
from . import fixtures
from .conftest import BaseTestCase

pytestmark = pytest.mark.unit

list_containers_func = "restic_compose_backup.utils.list_containers"


class ContainerOperationTests(BaseTestCase):
    """Tests for basic container operations and detection"""

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
        """Test detection and parsing of running containers"""
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

    def test_find_running_backup_container(self):
        """Test detection of running backup process container"""
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
