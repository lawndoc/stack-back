"""Unit tests for redaction of secrets in command logging"""

from unittest import mock

import pytest

from restic_compose_backup import commands
from .conftest import BaseTestCase

pytestmark = pytest.mark.unit

REPO_WITH_PASSWORD = "rest:http://user:s3cr3t@host:8000/repo"


class CommandRedactionTests(BaseTestCase):
    """restic invocations must never log the repository password, even at DEBUG."""

    def _fake_process(self):
        proc = mock.MagicMock()
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0
        return proc

    def test_run_does_not_log_repository_password(self):
        """commands.run() must redact the repository URL in its debug log."""
        cmd = ["restic", "-r", REPO_WITH_PASSWORD, "snapshots"]
        with mock.patch(
            "restic_compose_backup.commands.Popen", return_value=self._fake_process()
        ):
            with self.assertLogs(
                "restic_compose_backup.commands", level="DEBUG"
            ) as log:
                commands.run(cmd)
        output = "\n".join(log.output)
        self.assertNotIn("s3cr3t", output)
        self.assertIn("***", output)

    def test_run_capture_std_does_not_log_repository_password(self):
        """commands.run_capture_std() must redact the repository URL in its debug log."""
        cmd = ["restic", "-r", REPO_WITH_PASSWORD, "snapshots"]
        with mock.patch(
            "restic_compose_backup.commands.Popen", return_value=self._fake_process()
        ):
            with self.assertLogs(
                "restic_compose_backup.commands", level="DEBUG"
            ) as log:
                commands.run_capture_std(cmd)
        output = "\n".join(log.output)
        self.assertNotIn("s3cr3t", output)
