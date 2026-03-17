"""Unit tests for backup lifecycle orchestration in start_backup_process().

These tests verify the correct ordering of operations during a backup run:

    pre hooks → stop containers → backup → restart containers →
    post hooks (on success) / error hooks (on failure) → finally hooks

The ordering is critical because:
- Pre hooks may exec into containers (e.g., enable maintenance mode)
- Containers may be stopped during backup for filesystem consistency
- Post/error/finally hooks need containers running to exec into them

A previous bug had post hooks executing before stopped containers were
restarted.  These tests use a call_log pattern to assert the exact
sequence of operations and would have caught that bug.
"""

import os
import unittest
from unittest import mock

import pytest

from restic_compose_backup import hooks
from restic_compose_backup.cli import start_backup_process

pytestmark = pytest.mark.unit


class BackupLifecycleTests(unittest.TestCase):
    """Tests for operation ordering in start_backup_process().

    Uses a shared call_log list that records the order of operations.
    Each mocked dependency appends its name when called.  Tests then
    assert the exact sequence (or relative ordering) of entries.
    """

    def setUp(self):
        self.call_log = []

        # Patch all external dependencies of start_backup_process
        self.mock_status = mock.patch(
            "restic_compose_backup.cli.status"
        ).start()
        self.mock_collect = mock.patch(
            "restic_compose_backup.cli.hooks.collect_hooks"
        ).start()
        self.mock_execute = mock.patch(
            "restic_compose_backup.cli.hooks.execute_hooks"
        ).start()
        self.mock_stop = mock.patch(
            "restic_compose_backup.cli.utils.stop_containers"
        ).start()
        self.mock_start = mock.patch(
            "restic_compose_backup.cli.utils.start_containers"
        ).start()
        self.mock_backup = mock.patch(
            "restic_compose_backup.cli.restic.backup_files"
        ).start()
        self.mock_stat = mock.patch("os.stat").start()
        mock.patch.dict(
            os.environ, {"BACKUP_PROCESS_CONTAINER": "true"}
        ).start()

        # Defaults: volumes exist, all operations succeed
        self.mock_stat.return_value = True
        self.mock_collect.side_effect = self._collect_one_hook_per_stage
        self.mock_execute.side_effect = self._execute_and_record()
        self.mock_backup.side_effect = self._record("backup_volumes", 0)
        self.mock_stop.side_effect = self._record("stop_containers")
        self.mock_start.side_effect = self._record("start_containers")

    def tearDown(self):
        mock.patch.stopall()

    # ----- helpers -----

    def _collect_one_hook_per_stage(self, stage, backup_container, targets):
        """Return a single hook for each stage so every stage appears in the log."""
        return [hooks.Hook(stage=stage, order=1, cmd=f"echo {stage}")]

    def _execute_and_record(self, failing_stage=None):
        """Side effect for execute_hooks that records the stage name.

        If *failing_stage* matches, the hook returns False (abort).
        """
        def side_effect(hook_list, containers):
            if not hook_list:
                return True
            stage = hook_list[0].stage
            self.call_log.append(f"hooks:{stage}")
            return stage != failing_stage
        return side_effect

    def _record(self, name, return_value=None):
        """Create a side effect that appends *name* to the call log."""
        def side_effect(*args, **kwargs):
            self.call_log.append(name)
            return return_value
        return side_effect

    def _create_mock_containers(self, has_stop_during_backup=True,
                                has_database=False):
        """Build a mock RunningContainers for lifecycle testing."""
        containers = mock.MagicMock()
        containers.this_container._labels = {}

        backup_target = mock.MagicMock()
        backup_target.database_backup_enabled = has_database
        if has_database:
            backup_target.instance.backup.side_effect = (
                self._record("backup_database", 0)
            )
            backup_target.instance.container_type = "mysql"
            backup_target.instance.service_name = "db"
            backup_target.instance.project_name = "test"
        containers.containers_for_backup.return_value = [backup_target]

        if has_stop_during_backup:
            containers.stop_during_backup_containers = [mock.MagicMock()]
        else:
            containers.stop_during_backup_containers = []

        return containers

    def _create_mock_config(self):
        """Build a mock Config that skips maintenance."""
        config = mock.MagicMock()
        config.maintenance_schedule = "0 3 * * *"  # non-empty skips maintenance
        return config

    # ----- lifecycle ordering tests -----

    def test_successful_backup_lifecycle_order(self):
        """Happy path: pre → stop → backup → restart → post → finally."""
        config = self._create_mock_config()
        containers = self._create_mock_containers()

        start_backup_process(config, containers)

        self.assertEqual(self.call_log, [
            "hooks:pre",
            "stop_containers",
            "backup_volumes",
            "start_containers",
            "hooks:post",
            "hooks:finally",
        ])

    def test_post_hooks_run_after_container_restart(self):
        """Post hooks must execute after stopped containers are restarted.

        This test would have caught the original bug where post hooks
        ran inside the try block before the finally block restarted
        containers.
        """
        config = self._create_mock_config()
        containers = self._create_mock_containers()

        start_backup_process(config, containers)

        restart_position = self.call_log.index("start_containers")
        post_position = self.call_log.index("hooks:post")
        finally_position = self.call_log.index("hooks:finally")

        self.assertGreater(
            post_position, restart_position,
            "Post hooks must run after containers are restarted",
        )
        self.assertGreater(
            finally_position, restart_position,
            "Finally hooks must run after containers are restarted",
        )

    def test_error_hooks_run_after_container_restart(self):
        """On backup failure, error hooks must still run after restart."""
        config = self._create_mock_config()
        containers = self._create_mock_containers()
        self.mock_backup.side_effect = self._record("backup_volumes", 1)

        with self.assertRaises(SystemExit):
            start_backup_process(config, containers)

        restart_position = self.call_log.index("start_containers")
        error_position = self.call_log.index("hooks:error")

        self.assertGreater(
            error_position, restart_position,
            "Error hooks must run after containers are restarted",
        )

    def test_pre_hook_failure_skips_backup_and_stop(self):
        """When a pre hook aborts, no backup runs and containers are not stopped."""
        config = self._create_mock_config()
        containers = self._create_mock_containers()
        self.mock_execute.side_effect = (
            self._execute_and_record(failing_stage="pre")
        )

        with self.assertRaises(SystemExit):
            start_backup_process(config, containers)

        self.assertIn("hooks:pre", self.call_log)
        self.assertNotIn("stop_containers", self.call_log)
        self.assertNotIn("backup_volumes", self.call_log)
        self.assertNotIn("hooks:post", self.call_log)
        self.assertIn("hooks:error", self.call_log)
        self.assertIn("hooks:finally", self.call_log)

    def test_backup_failure_triggers_error_not_post(self):
        """On backup failure: error hooks run, post hooks do not."""
        config = self._create_mock_config()
        containers = self._create_mock_containers()
        self.mock_backup.side_effect = self._record("backup_volumes", 1)

        with self.assertRaises(SystemExit):
            start_backup_process(config, containers)

        self.assertIn("hooks:pre", self.call_log)
        self.assertIn("backup_volumes", self.call_log)
        self.assertNotIn("hooks:post", self.call_log)
        self.assertIn("hooks:error", self.call_log)
        self.assertIn("hooks:finally", self.call_log)

    def test_post_hook_failure_triggers_error_hooks(self):
        """When post hooks fail, error hooks still run."""
        config = self._create_mock_config()
        containers = self._create_mock_containers()
        self.mock_execute.side_effect = (
            self._execute_and_record(failing_stage="post")
        )

        with self.assertRaises(SystemExit):
            start_backup_process(config, containers)

        self.assertEqual(self.call_log, [
            "hooks:pre",
            "stop_containers",
            "backup_volumes",
            "start_containers",
            "hooks:post",
            "hooks:error",
            "hooks:finally",
        ])

    def test_containers_always_restarted_on_failure(self):
        """Stopped containers are restarted even when backup fails."""
        config = self._create_mock_config()
        containers = self._create_mock_containers()
        self.mock_backup.side_effect = self._record("backup_volumes", 1)

        with self.assertRaises(SystemExit):
            start_backup_process(config, containers)

        self.assertIn("stop_containers", self.call_log)
        self.assertIn("start_containers", self.call_log)

    def test_no_stop_when_no_stop_during_backup_containers(self):
        """Without stop-during-backup containers, stop/start are skipped."""
        config = self._create_mock_config()
        containers = self._create_mock_containers(has_stop_during_backup=False)

        start_backup_process(config, containers)

        self.assertEqual(self.call_log, [
            "hooks:pre",
            "backup_volumes",
            "hooks:post",
            "hooks:finally",
        ])

    def test_database_backup_runs_between_volumes_and_restart(self):
        """Database dumps run after volume backup but before container restart."""
        config = self._create_mock_config()
        containers = self._create_mock_containers(has_database=True)

        start_backup_process(config, containers)

        volume_position = self.call_log.index("backup_volumes")
        database_position = self.call_log.index("backup_database")
        restart_position = self.call_log.index("start_containers")

        self.assertGreater(
            database_position, volume_position,
            "Database backup must run after volume backup",
        )
        self.assertGreater(
            restart_position, database_position,
            "Container restart must run after database backup",
        )

