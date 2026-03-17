"""End-to-end backup lifecycle tests with real container and hook objects.

Unlike test_backup_lifecycle.py (which mocks hooks.execute_hooks entirely)
and test_hooks.py (which tests hooks in isolation), these tests exercise
the FULL start_backup_process() flow with real Container objects and real
hook logic.  Only the I/O boundary is mocked:

    commands.run           →  records local shell commands (hooks + restic)
    commands.docker_exec   →  records docker exec calls (hooks into containers)
    utils.stop_containers  →  records container stop operations
    utils.start_containers →  records container start operations
    restic.backup_from_stdin → records database dump operations

Everything above that boundary runs for real:

    hooks.parse_hooks_from_labels  → label parsing from real Container._labels
    hooks.collect_hooks            → symmetric ordering (setup / teardown)
    hooks.execute_hooks            → iteration, abort / continue logic
    hooks._execute_hook            → context resolution (local vs. docker exec)
    hooks._run_local               → delegates to commands.run (mocked)
    hooks._run_in_container        → delegates to commands.docker_exec (mocked)
    restic.backup_files            → delegates to commands.run (mocked)
    RunningContainers              → container discovery from fixture data
    containers_for_backup          → ordered backup logic

This catches bugs that neither test file alone would find:

- Hook context resolution errors (which container gets exec'd into)
- Symmetric hook ordering (pre: global→targets, post: targets→global)
- Post/error hooks running after container restart (not before)
- Label parsing through to actual command execution
- Interaction between ordered backup and hook ordering
"""

import os
import unittest
from unittest import mock

import pytest

from restic_compose_backup.containers import RunningContainers
from restic_compose_backup.cli import start_backup_process
from . import fixtures
from .conftest import BaseTestCase

pytestmark = pytest.mark.unit

list_containers_func = "restic_compose_backup.utils.list_containers"

# Predictable container IDs for target containers.
# These must NOT start with the mocked hostname (backup_hash[:8]).
WEB_ID = "w" * 64
DB_ID = "d" * 64
ALPHA_ID = "a" * 64
BETA_ID = "b" * 64


class EndToEndBackupTests(BaseTestCase):
    """End-to-end lifecycle tests using real Container/Hook objects.

    The call_log records every I/O operation in a readable string format::

        "local: echo global-pre"          hook running locally (commands.run)
        "exec@web: echo web-pre"          hook docker-exec'd into "web"
        "stop_containers"                 containers stopped
        "start_containers"                containers restarted
        "restic_backup_files"             volume backup (restic via commands.run)
        "backup_from_stdin@db"            database dump (restic.backup_from_stdin)

    Tests assert the exact call_log sequence (or relative ordering) to
    verify the full orchestration pipeline.
    """

    def setUp(self):
        self.call_log = []
        self.restic_exit_code = 0
        self.failing_local_hooks = {}  # {cmd_string: exit_code}
        self.id_to_service = {}

        # Track patches explicitly — mock.patch.stopall() would also kill
        # the hostname patcher from BaseTestCase.setUpClass.
        self._patches = [
            mock.patch(
                "restic_compose_backup.commands.run",
                side_effect=self._mock_commands_run,
            ),
            mock.patch(
                "restic_compose_backup.commands.docker_exec",
                side_effect=self._mock_docker_exec,
            ),
            mock.patch(
                "restic_compose_backup.cli.utils.stop_containers",
                side_effect=self._mock_stop,
            ),
            mock.patch(
                "restic_compose_backup.cli.utils.start_containers",
                side_effect=self._mock_start,
            ),
            mock.patch(
                "restic_compose_backup.restic.backup_from_stdin",
                side_effect=self._mock_backup_from_stdin,
            ),
            mock.patch("restic_compose_backup.cli.status"),
            mock.patch("os.stat", return_value=True),
            mock.patch.dict(
                os.environ, {"BACKUP_PROCESS_CONTAINER": "true"}
            ),
        ]
        for patch in self._patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self._patches):
            patch.stop()

    # ------------------------------------------------------------------ #
    # I/O mock implementations                                           #
    # ------------------------------------------------------------------ #

    def _mock_commands_run(self, cmd):
        """Distinguish restic commands from local hook commands.

        Both go through commands.run but produce different call_log entries:
        - restic: ``["restic", "-r", "test", "--verbose", "backup", ...]``
        - hook:   ``["sh", "-c", "echo something"]``
        """
        if cmd and cmd[0] == "restic":
            self.call_log.append("restic_backup_files")
            return self.restic_exit_code
        hook_cmd = cmd[2] if len(cmd) >= 3 else " ".join(cmd)
        self.call_log.append(f"local: {hook_cmd}")
        return self.failing_local_hooks.get(hook_cmd, 0)

    def _mock_docker_exec(self, container_id, cmd, **kwargs):
        """Record which container was exec'd into, with the command."""
        service = self.id_to_service.get(
            container_id, f"unknown({container_id[:12]})"
        )
        hook_cmd = cmd[2] if len(cmd) >= 3 else " ".join(cmd)
        self.call_log.append(f"exec@{service}: {hook_cmd}")
        return 0

    def _mock_stop(self, containers):
        self.call_log.append("stop_containers")

    def _mock_start(self, containers):
        self.call_log.append("start_containers")

    def _mock_backup_from_stdin(self, repository, filename, container_id,
                                source_command, environment=None):
        service = self.id_to_service.get(
            container_id, f"unknown({container_id[:12]})"
        )
        self.call_log.append(f"backup_from_stdin@{service}")
        return 0

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _build_running_containers(self, container_defs):
        """Create real RunningContainers from fixture definitions.

        Also populates ``self.id_to_service`` so call_log entries
        show readable service names instead of raw container IDs.
        """
        with mock.patch(
            list_containers_func,
            fixtures.containers(containers=container_defs),
        ):
            running = RunningContainers()

        self.id_to_service = {
            running.this_container.id: running.this_container.service_name,
        }
        for container in running.containers:
            self.id_to_service[container.id] = container.service_name

        return running

    def _make_config(self):
        """Create a mock Config that skips maintenance."""
        cfg = mock.MagicMock()
        cfg.repository = "test"
        cfg.maintenance_schedule = "0 3 * * *"
        return cfg

    # ------------------------------------------------------------------ #
    # Scenario 1: Full happy path                                        #
    # ------------------------------------------------------------------ #

    def test_full_happy_path_with_hooks_on_backup_and_target(self):
        """Complete successful backup with hooks on both backup and target.

        Verifies the exact sequence::

            pre(backup) → pre(web) → stop → restic backup → start →
            post(web) → post(backup) → finally(backup)

        This tests symmetric ordering, context resolution, and restart
        happening before post/finally hooks.
        """
        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "echo global-pre",
            "stack-back.hooks.post.1.cmd": "echo global-post",
            "stack-back.hooks.finally.1.cmd": "echo global-finally",
        }
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {
                "stack-back.volumes": "true",
                "stack-back.volumes.stop-during-backup": "true",
                "stack-back.hooks.pre.1.cmd": "echo web-pre",
                "stack-back.hooks.post.1.cmd": "echo web-post",
            },
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        self.assertEqual(self.call_log, [
            "local: echo global-pre",       # pre: backup first (setup)
            "exec@web: echo web-pre",        # pre: target second
            "stop_containers",               # stop web
            "restic_backup_files",           # backup volumes
            "start_containers",              # restart web
            "exec@web: echo web-post",       # post: target first (teardown)
            "local: echo global-post",       # post: backup second
            "local: echo global-finally",    # finally: backup
        ])

    # ------------------------------------------------------------------ #
    # Scenario 2: Post hooks must run after container restart             #
    # ------------------------------------------------------------------ #

    def test_post_hooks_always_run_after_container_restart(self):
        """Post and finally hooks must execute AFTER stopped containers restart.

        This is the bug found during review: post hooks were originally
        in the try block, running before the finally block restarted
        containers.
        """
        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.post.1.cmd": "echo global-post",
        }
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {
                "stack-back.volumes": "true",
                "stack-back.volumes.stop-during-backup": "true",
                "stack-back.hooks.post.1.cmd": "echo web-post",
            },
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        restart_idx = self.call_log.index("start_containers")
        post_web_idx = self.call_log.index("exec@web: echo web-post")
        post_global_idx = self.call_log.index("local: echo global-post")

        self.assertGreater(
            post_web_idx, restart_idx,
            "Web post hook must run after containers are restarted",
        )
        self.assertGreater(
            post_global_idx, restart_idx,
            "Global post hook must run after containers are restarted",
        )

    # ------------------------------------------------------------------ #
    # Scenario 3: Context resolution — all cases                         #
    # ------------------------------------------------------------------ #

    def test_backup_hook_without_context_runs_locally(self):
        """A backup container hook without explicit context runs locally.

        Current behavior: backup-container hooks with no context run via
        commands.run() (local subprocess) rather than docker exec.  This
        is functionally equivalent inside the backup process container
        but uses a different code path than target-container hooks.
        """
        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "echo local-test",
        }
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {"stack-back.volumes": "true"},
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        self.assertIn("local: echo local-test", self.call_log)
        self.assertNotIn("exec@backup: echo local-test", self.call_log)

    def test_target_hook_without_context_execs_into_own_container(self):
        """A target container hook without explicit context execs into itself.

        The hook is defined on 'web', so it must docker-exec into the web
        container — not run locally in the backup process container.
        """
        container_defs = self.createContainers()
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {
                "stack-back.volumes": "true",
                "stack-back.hooks.pre.1.cmd": "echo self-exec",
            },
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        self.assertIn("exec@web: echo self-exec", self.call_log)
        self.assertNotIn("local: echo self-exec", self.call_log)

    def test_context_override_backup_hook_execs_into_target(self):
        """A backup container hook with explicit context execs into the named service."""
        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "echo ctx-override",
            "stack-back.hooks.pre.1.context": "web",
        }
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {"stack-back.volumes": "true"},
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        self.assertIn("exec@web: echo ctx-override", self.call_log)
        self.assertNotIn("local: echo ctx-override", self.call_log)

    def test_cross_container_context_web_hook_execs_into_db(self):
        """A hook defined on 'web' with context='db' execs into the db container."""
        container_defs = self.createContainers()
        container_defs += [
            {
                "id": WEB_ID,
                "service": "web",
                "labels": {
                    "stack-back.volumes": "true",
                    "stack-back.hooks.pre.1.cmd": "echo cross-ctx",
                    "stack-back.hooks.pre.1.context": "db",
                },
                "mounts": [
                    {"Source": "web_data", "Destination": "/data", "Type": "volume"},
                ],
            },
            {
                "id": DB_ID,
                "service": "db",
                "image": "mysql:8",
                "labels": {"stack-back.mysql": "true"},
                "env": ["MYSQL_ROOT_PASSWORD=secret"],
                "mounts": [
                    {"Source": "mysql_data", "Destination": "/var/lib/mysql", "Type": "volume"},
                ],
            },
        ]

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        self.assertIn("exec@db: echo cross-ctx", self.call_log)
        self.assertNotIn("exec@web: echo cross-ctx", self.call_log)
        self.assertNotIn("local: echo cross-ctx", self.call_log)

    def test_unknown_hook_context_triggers_failure(self):
        """A hook referencing a non-existent service triggers the error path."""
        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "echo bad-ctx",
            "stack-back.hooks.pre.1.context": "nonexistent",
            "stack-back.hooks.error.1.cmd": "echo global-error",
            "stack-back.hooks.finally.1.cmd": "echo global-finally",
        }
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {"stack-back.volumes": "true"},
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)

        with self.assertRaises(SystemExit):
            start_backup_process(self._make_config(), containers)

        # Bad context fails the hook → no backup → error + finally
        self.assertNotIn("restic_backup_files", self.call_log)
        self.assertIn("local: echo global-error", self.call_log)
        self.assertIn("local: echo global-finally", self.call_log)

    # ------------------------------------------------------------------ #
    # Scenario 4: Backup failure — error hooks, not post hooks           #
    # ------------------------------------------------------------------ #

    def test_backup_failure_fires_error_hooks_not_post(self):
        """When volume backup fails, error hooks fire; post hooks do not.

        Also verifies symmetric teardown ordering: target error hooks
        run before backup-container error hooks.
        """
        self.restic_exit_code = 1

        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.post.1.cmd": "echo global-post",
            "stack-back.hooks.error.1.cmd": "echo global-error",
            "stack-back.hooks.finally.1.cmd": "echo global-finally",
        }
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {
                "stack-back.volumes": "true",
                "stack-back.volumes.stop-during-backup": "true",
                "stack-back.hooks.error.1.cmd": "echo web-error",
            },
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)

        with self.assertRaises(SystemExit):
            start_backup_process(self._make_config(), containers)

        self.assertEqual(self.call_log, [
            "stop_containers",
            "restic_backup_files",           # fails (exit code 1)
            "start_containers",              # restart before hooks
            "exec@web: echo web-error",      # error: target first (teardown)
            "local: echo global-error",      # error: backup second
            "local: echo global-finally",    # finally always
        ])
        self.assertNotIn("local: echo global-post", self.call_log)

    def test_error_hooks_run_after_container_restart(self):
        """On failure, error hooks must run after containers are restarted."""
        self.restic_exit_code = 1

        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.error.1.cmd": "echo global-error",
        }
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {
                "stack-back.volumes": "true",
                "stack-back.volumes.stop-during-backup": "true",
                "stack-back.hooks.error.1.cmd": "echo web-error",
            },
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)

        with self.assertRaises(SystemExit):
            start_backup_process(self._make_config(), containers)

        restart_idx = self.call_log.index("start_containers")
        web_error_idx = self.call_log.index("exec@web: echo web-error")
        global_error_idx = self.call_log.index("local: echo global-error")

        self.assertGreater(
            web_error_idx, restart_idx,
            "Web error hook must run after restart",
        )
        self.assertGreater(
            global_error_idx, restart_idx,
            "Global error hook must run after restart",
        )

    # ------------------------------------------------------------------ #
    # Scenario 5: Pre hook failure — skips everything                    #
    # ------------------------------------------------------------------ #

    def test_pre_hook_failure_skips_backup_and_stop(self):
        """When a pre hook aborts, no stop/backup happens; error+finally fire."""
        self.failing_local_hooks["fail-pre"] = 1

        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "fail-pre",
            "stack-back.hooks.error.1.cmd": "echo global-error",
            "stack-back.hooks.finally.1.cmd": "echo global-finally",
        }
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {
                "stack-back.volumes": "true",
                "stack-back.volumes.stop-during-backup": "true",
                "stack-back.hooks.pre.1.cmd": "echo web-pre",
            },
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)

        with self.assertRaises(SystemExit):
            start_backup_process(self._make_config(), containers)

        self.assertEqual(self.call_log, [
            "local: fail-pre",               # pre hook fails → abort
            # No web pre hook (aborted after first failure)
            # No stop_containers
            # No restic_backup_files
            "local: echo global-error",      # error fires
            "local: echo global-finally",    # finally fires
        ])

    # ------------------------------------------------------------------ #
    # Scenario 6: Database backup in lifecycle                           #
    # ------------------------------------------------------------------ #

    def test_database_backup_in_lifecycle(self):
        """Database dump runs after volume backup, before restart.

        Uses a real MysqlContainer instance (via Container.instance) with
        mocked restic.backup_from_stdin at the I/O boundary.
        """
        container_defs = self.createContainers()
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {
                "stack-back.volumes": "true",
                "stack-back.volumes.stop-during-backup": "true",
            },
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })
        container_defs.append({
            "id": DB_ID,
            "service": "db",
            "image": "mysql:8",
            "labels": {"stack-back.mysql": "true"},
            "env": ["MYSQL_ROOT_PASSWORD=secret"],
            "mounts": [
                {"Source": "mysql_data", "Destination": "/var/lib/mysql", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        volume_idx = self.call_log.index("restic_backup_files")
        db_idx = self.call_log.index("backup_from_stdin@db")
        restart_idx = self.call_log.index("start_containers")

        self.assertGreater(
            db_idx, volume_idx,
            "DB dump must run after volume backup",
        )
        self.assertGreater(
            restart_idx, db_idx,
            "Restart must run after DB dump",
        )

    # ------------------------------------------------------------------ #
    # Scenario 7: Symmetric ordering with multiple targets               #
    # ------------------------------------------------------------------ #

    def test_symmetric_ordering_multiple_targets(self):
        """Pre hooks go backup→alpha→beta; post hooks go alpha→beta→backup.

        Verifies that the backup container is correctly placed first for
        setup (pre) and last for teardown (post).  Target containers
        maintain their discovery order in both stages.
        """
        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "echo global-pre",
            "stack-back.hooks.post.1.cmd": "echo global-post",
        }
        container_defs += [
            {
                "id": ALPHA_ID,
                "service": "alpha",
                "labels": {
                    "stack-back.volumes": "true",
                    "stack-back.hooks.pre.1.cmd": "echo alpha-pre",
                    "stack-back.hooks.post.1.cmd": "echo alpha-post",
                },
                "mounts": [
                    {"Source": "a_data", "Destination": "/a", "Type": "volume"},
                ],
            },
            {
                "id": BETA_ID,
                "service": "beta",
                "labels": {
                    "stack-back.volumes": "true",
                    "stack-back.hooks.pre.1.cmd": "echo beta-pre",
                    "stack-back.hooks.post.1.cmd": "echo beta-post",
                },
                "mounts": [
                    {"Source": "b_data", "Destination": "/b", "Type": "volume"},
                ],
            },
        ]

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        # Pre hooks: backup → alpha → beta (setup order)
        pre_global = self.call_log.index("local: echo global-pre")
        pre_alpha = self.call_log.index("exec@alpha: echo alpha-pre")
        pre_beta = self.call_log.index("exec@beta: echo beta-pre")
        self.assertLess(pre_global, pre_alpha)
        self.assertLess(pre_alpha, pre_beta)

        # Post hooks: alpha → beta → backup (teardown order)
        post_alpha = self.call_log.index("exec@alpha: echo alpha-post")
        post_beta = self.call_log.index("exec@beta: echo beta-post")
        post_global = self.call_log.index("local: echo global-post")
        self.assertLess(post_alpha, post_global)
        self.assertLess(post_beta, post_global)

    # ------------------------------------------------------------------ #
    # Scenario 8: Ordered backup affects hook ordering                   #
    # ------------------------------------------------------------------ #

    def test_ordered_backup_affects_hook_order(self):
        """When ordered backup is configured, hooks follow container order.

        Order configured as beta→alpha means beta hooks run before alpha.
        """
        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.ordered": "true",
            "stack-back.order.1": "beta",
            "stack-back.order.2": "alpha",
        }
        container_defs += [
            {
                "id": ALPHA_ID,
                "service": "alpha",
                "labels": {
                    "stack-back.volumes": "true",
                    "stack-back.hooks.pre.1.cmd": "echo alpha-pre",
                    "stack-back.hooks.post.1.cmd": "echo alpha-post",
                },
                "mounts": [
                    {"Source": "a_data", "Destination": "/a", "Type": "volume"},
                ],
            },
            {
                "id": BETA_ID,
                "service": "beta",
                "labels": {
                    "stack-back.volumes": "true",
                    "stack-back.hooks.pre.1.cmd": "echo beta-pre",
                    "stack-back.hooks.post.1.cmd": "echo beta-post",
                },
                "mounts": [
                    {"Source": "b_data", "Destination": "/b", "Type": "volume"},
                ],
            },
        ]

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        # Pre hooks follow configured order: beta before alpha
        pre_beta = self.call_log.index("exec@beta: echo beta-pre")
        pre_alpha = self.call_log.index("exec@alpha: echo alpha-pre")
        self.assertLess(
            pre_beta, pre_alpha,
            "Ordered backup: beta pre should run before alpha pre",
        )

        # Post hooks follow configured order within targets: beta before alpha
        post_beta = self.call_log.index("exec@beta: echo beta-post")
        post_alpha = self.call_log.index("exec@alpha: echo alpha-post")
        self.assertLess(
            post_beta, post_alpha,
            "Ordered backup post: targets maintain configured order",
        )

    # ------------------------------------------------------------------ #
    # Scenario 9: Minimal scenario — no hooks, no stops                  #
    # ------------------------------------------------------------------ #

    def test_no_hooks_no_stop_clean_backup(self):
        """Minimal scenario: volume backup with no hooks and no stopped containers."""
        container_defs = self.createContainers()
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {"stack-back.volumes": "true"},
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        self.assertEqual(self.call_log, ["restic_backup_files"])

    # ------------------------------------------------------------------ #
    # Scenario 10: on-error=continue allows backup to proceed            #
    # ------------------------------------------------------------------ #

    def test_continue_on_error_does_not_abort_pipeline(self):
        """A pre hook with on-error=continue allows the backup to proceed."""
        self.failing_local_hooks["soft-fail"] = 1

        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "soft-fail",
            "stack-back.hooks.pre.1.on-error": "continue",
            "stack-back.hooks.pre.2.cmd": "echo second-pre",
        }
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {"stack-back.volumes": "true"},
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        # Both pre hooks ran despite first failure
        self.assertIn("local: soft-fail", self.call_log)
        self.assertIn("local: echo second-pre", self.call_log)
        # Backup proceeded
        self.assertIn("restic_backup_files", self.call_log)

    # ------------------------------------------------------------------ #
    # Scenario 11: Post hook failure triggers error hooks                #
    # ------------------------------------------------------------------ #

    def test_post_hook_failure_triggers_error_hooks(self):
        """When a post hook fails, error hooks still run."""
        self.failing_local_hooks["echo fail-post"] = 1

        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.post.1.cmd": "echo fail-post",
            "stack-back.hooks.error.1.cmd": "echo global-error",
            "stack-back.hooks.finally.1.cmd": "echo global-finally",
        }
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {"stack-back.volumes": "true"},
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)

        with self.assertRaises(SystemExit):
            start_backup_process(self._make_config(), containers)

        self.assertEqual(self.call_log, [
            "restic_backup_files",
            "local: echo fail-post",         # post hook fails
            "local: echo global-error",      # error fires
            "local: echo global-finally",    # finally fires
        ])

    # ------------------------------------------------------------------ #
    # Scenario 12: Hooks on all four stages                              #
    # ------------------------------------------------------------------ #

    def test_all_four_stages_with_failure(self):
        """All hook stages fire in correct order during a backup failure.

        pre → (backup fails) → error → finally
        No post hooks because backup failed.
        """
        self.restic_exit_code = 1

        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "echo pre",
            "stack-back.hooks.post.1.cmd": "echo post",
            "stack-back.hooks.error.1.cmd": "echo error",
            "stack-back.hooks.finally.1.cmd": "echo finally",
        }
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {"stack-back.volumes": "true"},
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)

        with self.assertRaises(SystemExit):
            start_backup_process(self._make_config(), containers)

        self.assertEqual(self.call_log, [
            "local: echo pre",
            "restic_backup_files",           # fails
            "local: echo error",             # error fires
            "local: echo finally",           # finally fires
        ])
        self.assertNotIn("local: echo post", self.call_log)

    # ------------------------------------------------------------------ #
    # Scenario 13: Multiple hooks per stage in correct order             #
    # ------------------------------------------------------------------ #

    def test_multiple_hooks_per_stage_execute_in_order(self):
        """Multiple hooks on one container execute in numerical order."""
        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.pre.3.cmd": "echo third",
            "stack-back.hooks.pre.1.cmd": "echo first",
            "stack-back.hooks.pre.2.cmd": "echo second",
        }
        container_defs.append({
            "id": WEB_ID,
            "service": "web",
            "labels": {"stack-back.volumes": "true"},
            "mounts": [
                {"Source": "web_data", "Destination": "/data", "Type": "volume"},
            ],
        })

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        first_idx = self.call_log.index("local: echo first")
        second_idx = self.call_log.index("local: echo second")
        third_idx = self.call_log.index("local: echo third")

        self.assertLess(first_idx, second_idx)
        self.assertLess(second_idx, third_idx)
        # All before backup
        backup_idx = self.call_log.index("restic_backup_files")
        self.assertLess(third_idx, backup_idx)

    # ------------------------------------------------------------------ #
    # Scenario 14: Database with hooks — full lifecycle                  #
    # ------------------------------------------------------------------ #

    def test_database_with_hooks_full_lifecycle(self):
        """Full lifecycle with a web container (stopped) and DB container (hooks).

        Verifies that DB hooks fire via docker exec into the DB container
        and that DB dump happens after volume backup.
        """
        container_defs = self.createContainers()
        container_defs[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "echo global-pre",
            "stack-back.hooks.finally.1.cmd": "echo global-finally",
        }
        container_defs += [
            {
                "id": WEB_ID,
                "service": "web",
                "labels": {
                    "stack-back.volumes": "true",
                    "stack-back.volumes.stop-during-backup": "true",
                },
                "mounts": [
                    {"Source": "web_data", "Destination": "/data", "Type": "volume"},
                ],
            },
            {
                "id": DB_ID,
                "service": "db",
                "image": "mysql:8",
                "labels": {
                    "stack-back.mysql": "true",
                    "stack-back.hooks.pre.1.cmd": "echo db-pre",
                    "stack-back.hooks.post.1.cmd": "echo db-post",
                },
                "env": ["MYSQL_ROOT_PASSWORD=secret"],
                "mounts": [
                    {"Source": "mysql_data", "Destination": "/var/lib/mysql", "Type": "volume"},
                ],
            },
        ]

        containers = self._build_running_containers(container_defs)
        start_backup_process(self._make_config(), containers)

        self.assertEqual(self.call_log, [
            "local: echo global-pre",        # pre: backup first
            "exec@db: echo db-pre",          # pre: db target
            "stop_containers",               # stop web (db NOT stopped)
            "restic_backup_files",           # backup volumes
            "backup_from_stdin@db",          # dump database
            "start_containers",              # restart web
            "exec@db: echo db-post",         # post: target first (teardown)
            "local: echo global-finally",    # finally: backup
        ])


