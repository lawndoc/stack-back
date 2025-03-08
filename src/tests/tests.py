import json
import os
import unittest
from unittest import mock

os.environ['RESTIC_REPOSITORY'] = "test"
os.environ['RESTIC_PASSWORD'] = "password"

from restic_compose_backup import utils, config
from restic_compose_backup.containers import RunningContainers
import fixtures

list_containers_func = 'restic_compose_backup.utils.list_containers'


class BaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up basic environment variables"""
        # os.environ['RESTIC_REPOSITORY'] = "test"
        # os.environ['RESTIC_PASSWORD'] = "password"

    def createContainers(self):
        backup_hash = fixtures.generate_sha256()
        os.environ['HOSTNAME'] = backup_hash[:8]
        return [
            {
                'id': backup_hash,
                'service': 'backup',
            }
        ]

class ResticBackupTests(BaseTestCase):
    def test_list_containers(self):
        """Test a basic container list"""
        containers = [
            {
                'service': 'web',
                'labels': {
                    'moo': 1,
                },
                'mounts': [{
                    'Source': 'moo',
                    'Destination': 'moo',
                    'Type': 'bind',
                }]
            },
            {
                'service': 'mysql',
            },
            {
                'service': 'postgres',
            },
        ]

        with mock.patch(list_containers_func, fixtures.containers(containers=containers)):
            test = utils.list_containers()

    def test_running_containers(self):
        containers = self.createContainers()
        containers += [
            {
                'service': 'web',
                'labels': {
                    'stack-back.volumes': True,
                    'test': 'test',
                },
                'mounts': [{
                    'Source': 'test',
                    'Destination': 'test',
                    'Type': 'bind',
                }]
            },
            {
                'service': 'mysql',
            },
            {
                'service': 'postgres',
            },
        ]
        with mock.patch(list_containers_func, fixtures.containers(containers=containers)):
            result = RunningContainers()
            self.assertEqual(len(result.containers), 4, msg="Three containers expected")
            self.assertNotEqual(result.this_container, None, msg="No backup container found")
            web_service = result.get_service('web')
            self.assertNotEqual(web_service, None)
            self.assertEqual(len(web_service.filter_mounts()), 1)

    def test_volumes_for_backup(self):
        containers = self.createContainers()
        containers += [
            {
                'service': 'web',
                'labels': {
                    'stack-back.volumes': True,
                },
                'mounts': [{
                    'Source': 'test',
                    'Destination': 'test',
                    'Type': 'bind',
                }]
            },
            {
                'service': 'mysql',
                'labels': {
                    'stack-back.mysql': True,
                },
                'mounts': [{
                    'Source': 'data',
                    'Destination': 'data',
                    'Type': 'bind',
                }]
            },
        ]
        with mock.patch(list_containers_func, fixtures.containers(containers=containers)):
            cnt = RunningContainers()
            self.assertTrue(len(cnt.containers_for_backup()) == 2)
            self.assertEqual(cnt.generate_backup_mounts(), {'test': {'bind': '/volumes/web/test', 'mode': 'ro'}})

    def test_include(self):
        containers = self.createContainers()
        containers += [
            {
                'service': 'web',
                'labels': {
                    'stack-back.volumes': True,
                    'stack-back.volumes.include': 'media',
                },
                'mounts': [
                    {
                        'Source': '/srv/files/media',
                        'Destination': '/srv/media',
                        'Type': 'bind',
                    },
                    {
                        'Source': '/srv/files/stuff',
                        'Destination': '/srv/stuff',
                        'Type': 'bind',
                    },
                ]
            },
        ]
        with mock.patch(list_containers_func, fixtures.containers(containers=containers)):
            cnt = RunningContainers()

        web_service = cnt.get_service('web')
        self.assertNotEqual(web_service, None, msg="Web service not found")

        mounts = web_service.filter_mounts()
        print(mounts)
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0].source, '/srv/files/media')

    def test_exclude(self):
        containers = self.createContainers()
        containers += [
            {
                'service': 'web',
                'labels': {
                    'stack-back.volumes': True,
                    'stack-back.volumes.exclude': 'stuff',
                },
                'mounts': [
                    {
                        'Source': '/srv/files/media',
                        'Destination': '/srv/media',
                        'Type': 'bind',
                    },
                    {
                        'Source': '/srv/files/stuff',
                        'Destination': '/srv/stuff',
                        'Type': 'bind',
                    },
                ]
            },
        ]
        with mock.patch(list_containers_func, fixtures.containers(containers=containers)):
            cnt = RunningContainers()

        web_service = cnt.get_service('web')
        self.assertNotEqual(web_service, None, msg="Web service not found")

        mounts = web_service.filter_mounts()
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0].source, '/srv/files/media')

    def test_find_running_backup_container(self):
        containers = self.createContainers()
        with mock.patch(list_containers_func, fixtures.containers(containers=containers)):
            cnt = RunningContainers()
            self.assertFalse(cnt.backup_process_running)

        containers += [
            {
                'service': 'backup_runner',
                'labels': {
                    'stack-back.process-default': 'True',
                },
            },
        ]
        with mock.patch(list_containers_func, fixtures.containers(containers=containers)):
            cnt = RunningContainers()
            self.assertTrue(cnt.backup_process_running)


class IncludeAllVolumesTests(BaseTestCase):
    @classmethod
    def setUpClass(cls):
        config.config.include_all_volumes = "true"

    @classmethod
    def tearDownClass(cls):
        config.config = config.Config()

    def test_basic_functionality(self):
        """Test that the INCLUDE_ALL_VOLUMES flag works"""
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

    def test_explicit_exclude(self):
        """Test that a container can be excluded from the backup"""

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
