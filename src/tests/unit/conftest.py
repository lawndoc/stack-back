"""Shared fixtures and test base classes for unit tests"""
import os
import unittest
from unittest import mock

os.environ["RESTIC_REPOSITORY"] = "test"
os.environ["RESTIC_PASSWORD"] = "password"

from . import fixtures


class BaseTestCase(unittest.TestCase):
    """Base test case for unit tests with common setup"""
    
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
        """Create a basic backup container for tests"""
        return [
            {
                "id": self.backup_hash,
                "service": "backup",
            }
        ]
