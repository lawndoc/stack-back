"""Unit tests for repository URL redaction in log output"""

import pytest

from restic_compose_backup.utils import redact_repo_url
from .conftest import BaseTestCase

pytestmark = pytest.mark.unit


class RepositoryRedactionTests(BaseTestCase):
    """Ensure passwords embedded in the repository URL are never logged in clear text."""

    def test_rest_http_basic_auth_is_redacted(self):
        """HTTP basic auth credentials in a rest: backend are masked."""
        repo = "rest:http://user:s3cr3t@backup.example.com:8000/repo"
        self.assertEqual(
            redact_repo_url(repo),
            "rest:http://user:***@backup.example.com:8000/repo",
        )

    def test_rest_https_basic_auth_is_redacted(self):
        self.assertEqual(
            redact_repo_url("rest:https://u:p@host:8000/repo"),
            "rest:https://u:***@host:8000/repo",
        )

    def test_password_with_slash_is_redacted(self):
        """A '/' in the password must still be masked (no silent leak)."""
        self.assertEqual(
            redact_repo_url("rest:http://u:p/ass@host:8000/x"),
            "rest:http://u:***@host:8000/x",
        )

    def test_password_with_at_is_redacted(self):
        """An '@' in the password must still be masked (no silent leak)."""
        self.assertEqual(
            redact_repo_url("rest:http://u:p@ss@host:8000/x"),
            "rest:http://u:***@host:8000/x",
        )

    def test_sftp_without_url_scheme_is_unchanged(self):
        """sftp backends authenticate via ssh keys/agent and carry no inline URL
        password, so a bare ``sftp:`` spec (no scheme://) is returned unchanged."""
        self.assertEqual(
            redact_repo_url("sftp:user:pass@host:/srv/restic-repo"),
            "sftp:user:pass@host:/srv/restic-repo",
        )

    def test_repository_without_credentials_is_unchanged(self):
        """Repository strings without embedded secrets must be returned verbatim."""
        for repo in [
            "rest:http://backup.example.com:8000/repo",
            "sftp:user@host:/srv/restic-repo",
            "s3:s3.amazonaws.com/bucket",
            "azure:container/path",
            "/mnt/restic",
            "",
        ]:
            with self.subTest(repo=repo):
                self.assertEqual(redact_repo_url(repo), repo)

    def test_secret_is_not_leaked(self):
        """The cleartext password must never appear in the redacted output."""
        self.assertNotIn("s3cr3t", redact_repo_url("rest:http://u:s3cr3t@h:8000/x"))
