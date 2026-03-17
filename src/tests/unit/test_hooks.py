"""Unit tests for backup hooks and ordered backup execution"""

import unittest
from unittest import mock

import pytest

from restic_compose_backup import hooks
from restic_compose_backup.containers import RunningContainers
from . import fixtures
from .conftest import BaseTestCase

pytestmark = pytest.mark.unit

list_containers_func = "restic_compose_backup.utils.list_containers"


class HookParsingTests(BaseTestCase):
    """Tests for parse_hooks_from_labels()"""

    def test_parse_basic_hooks(self):
        labels = {
            "stack-back.hooks.pre.1.cmd": "echo before",
            "stack-back.hooks.pre.1.context": "web",
            "stack-back.hooks.pre.2.cmd": "echo also before",
        }
        result = hooks.parse_hooks_from_labels(labels, "pre")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].cmd, "echo before")
        self.assertEqual(result[0].context, "web")
        self.assertEqual(result[0].order, 1)
        self.assertEqual(result[0].on_error, "abort")
        self.assertEqual(result[1].cmd, "echo also before")
        self.assertIsNone(result[1].context)
        self.assertEqual(result[1].order, 2)

    def test_parse_on_error_continue(self):
        labels = {
            "stack-back.hooks.pre.1.cmd": "echo test",
            "stack-back.hooks.pre.1.on-error": "continue",
        }
        result = hooks.parse_hooks_from_labels(labels, "pre")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].on_error, "continue")

    def test_parse_invalid_on_error_defaults_to_abort(self):
        labels = {
            "stack-back.hooks.pre.1.cmd": "echo test",
            "stack-back.hooks.pre.1.on-error": "invalid",
        }
        result = hooks.parse_hooks_from_labels(labels, "pre")
        self.assertEqual(result[0].on_error, "abort")

    def test_parse_non_contiguous_order(self):
        labels = {
            "stack-back.hooks.pre.1.cmd": "echo first",
            "stack-back.hooks.pre.5.cmd": "echo third",
            "stack-back.hooks.pre.3.cmd": "echo second",
        }
        result = hooks.parse_hooks_from_labels(labels, "pre")
        self.assertEqual(len(result), 3)
        self.assertEqual(
            [hook.order for hook in result], [1, 3, 5]
        )

    def test_parse_missing_cmd_skipped(self):
        labels = {
            "stack-back.hooks.pre.1.context": "web",
            "stack-back.hooks.pre.2.cmd": "echo valid",
        }
        result = hooks.parse_hooks_from_labels(labels, "pre")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].order, 2)

    def test_parse_stages_isolated(self):
        labels = {
            "stack-back.hooks.pre.1.cmd": "echo pre",
            "stack-back.hooks.post.1.cmd": "echo post",
            "stack-back.hooks.error.1.cmd": "echo error",
            "stack-back.hooks.finally.1.cmd": "echo finally",
        }
        for stage in hooks.HOOK_STAGES:
            result = hooks.parse_hooks_from_labels(labels, stage)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].cmd, f"echo {stage}")

    def test_parse_empty_labels(self):
        result = hooks.parse_hooks_from_labels({"other": "value"}, "pre")
        self.assertEqual(len(result), 0)

    def test_parse_invalid_order_number(self):
        labels = {
            "stack-back.hooks.pre.abc.cmd": "echo bad",
            "stack-back.hooks.pre.1.cmd": "echo good",
        }
        result = hooks.parse_hooks_from_labels(labels, "pre")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].order, 1)


class HookCollectionTests(BaseTestCase):
    """Tests for collect_hooks()"""

    def test_backup_hooks_before_target_hooks(self):
        containers = self.createContainers()
        containers[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "echo backup-pre",
            "stack-back.hooks.post.1.cmd": "echo backup-post",
        }
        containers += [
            {
                "service": "web",
                "labels": {
                    "stack-back.volumes": True,
                    "stack-back.hooks.pre.1.cmd": "echo web-pre",
                    "stack-back.hooks.post.1.cmd": "echo web-post",
                },
                "mounts": [
                    {"Source": "data", "Destination": "/data", "Type": "volume"},
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()

        backup_list = running.containers_for_backup()

        # pre: backup container hooks first (setup)
        pre = hooks.collect_hooks("pre", running.this_container, backup_list)
        self.assertEqual(len(pre), 2)
        self.assertEqual(pre[0].cmd, "echo backup-pre")
        self.assertEqual(pre[0].source_service_name, "backup")
        self.assertEqual(pre[1].cmd, "echo web-pre")
        self.assertEqual(pre[1].source_service_name, "web")

        # post: target container hooks first (teardown)
        post = hooks.collect_hooks("post", running.this_container, backup_list)
        self.assertEqual(len(post), 2)
        self.assertEqual(post[0].cmd, "echo web-post")
        self.assertEqual(post[0].source_service_name, "web")
        self.assertEqual(post[1].cmd, "echo backup-post")
        self.assertEqual(post[1].source_service_name, "backup")

    def test_no_hooks_returns_empty(self):
        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "labels": {"stack-back.volumes": True},
                "mounts": [
                    {"Source": "d", "Destination": "/d", "Type": "volume"},
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()

        self.assertEqual(
            len(
                hooks.collect_hooks(
                    "pre", running.this_container, running.containers_for_backup()
                )
            ),
            0,
        )

    def test_multiple_targets_in_order(self):
        containers = self.createContainers()
        containers += [
            {
                "service": "alpha",
                "labels": {
                    "stack-back.volumes": True,
                    "stack-back.hooks.pre.1.cmd": "echo alpha",
                },
                "mounts": [
                    {"Source": "a", "Destination": "/a", "Type": "volume"},
                ],
            },
            {
                "service": "beta",
                "labels": {
                    "stack-back.volumes": True,
                    "stack-back.hooks.pre.1.cmd": "echo beta",
                },
                "mounts": [
                    {"Source": "b", "Destination": "/b", "Type": "volume"},
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()

        pre = hooks.collect_hooks(
            "pre", running.this_container, running.containers_for_backup()
        )
        self.assertEqual(pre[0].source_service_name, "alpha")
        self.assertEqual(pre[1].source_service_name, "beta")


class HookExecutionTests(BaseTestCase):
    """Tests for execute_hooks() and context resolution"""

    @mock.patch("restic_compose_backup.hooks._run_local")
    @mock.patch("restic_compose_backup.hooks._run_in_container")
    def test_empty_hooks_succeeds(self, mock_remote, mock_local):
        containers = self.createContainers()
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        self.assertTrue(hooks.execute_hooks([], running))
        mock_local.assert_not_called()
        mock_remote.assert_not_called()

    @mock.patch("restic_compose_backup.hooks._run_local", return_value=0)
    def test_backup_hook_runs_locally(self, mock_local):
        containers = self.createContainers()
        containers[0]["labels"] = {"stack-back.hooks.pre.1.cmd": "echo test"}
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        pre = hooks.collect_hooks(
            "pre", running.this_container, running.containers_for_backup()
        )
        self.assertTrue(hooks.execute_hooks(pre, running))
        mock_local.assert_called_once_with("echo test")

    @mock.patch("restic_compose_backup.hooks._run_in_container", return_value=0)
    def test_target_hook_uses_docker_exec(self, mock_remote):
        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "labels": {
                    "stack-back.volumes": True,
                    "stack-back.hooks.pre.1.cmd": "echo web",
                },
                "mounts": [
                    {"Source": "d", "Destination": "/d", "Type": "volume"},
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        web = running.get_service("web")
        pre = hooks.collect_hooks(
            "pre", running.this_container, running.containers_for_backup()
        )
        self.assertTrue(hooks.execute_hooks(pre, running))
        mock_remote.assert_called_once_with(web.id, "echo web")

    @mock.patch("restic_compose_backup.hooks._run_in_container", return_value=0)
    def test_explicit_context_overrides_source(self, mock_remote):
        containers = self.createContainers()
        containers[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "echo ctx",
            "stack-back.hooks.pre.1.context": "web",
        }
        containers += [
            {
                "service": "web",
                "labels": {"stack-back.volumes": True},
                "mounts": [
                    {"Source": "d", "Destination": "/d", "Type": "volume"},
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        web = running.get_service("web")
        pre = hooks.collect_hooks(
            "pre", running.this_container, running.containers_for_backup()
        )
        self.assertTrue(hooks.execute_hooks(pre, running))
        mock_remote.assert_called_once_with(web.id, "echo ctx")

    @mock.patch("restic_compose_backup.hooks._run_local", return_value=1)
    def test_abort_on_failure(self, mock_local):
        containers = self.createContainers()
        containers[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "fail",
            "stack-back.hooks.pre.2.cmd": "echo skip",
        }
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        pre = hooks.collect_hooks(
            "pre", running.this_container, running.containers_for_backup()
        )
        self.assertFalse(hooks.execute_hooks(pre, running))
        mock_local.assert_called_once_with("fail")

    @mock.patch("restic_compose_backup.hooks._run_local", side_effect=[1, 0])
    def test_continue_on_failure(self, mock_local):
        containers = self.createContainers()
        containers[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "fail",
            "stack-back.hooks.pre.1.on-error": "continue",
            "stack-back.hooks.pre.2.cmd": "echo ok",
        }
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        pre = hooks.collect_hooks(
            "pre", running.this_container, running.containers_for_backup()
        )
        self.assertTrue(hooks.execute_hooks(pre, running))
        self.assertEqual(mock_local.call_count, 2)

    @mock.patch("restic_compose_backup.hooks._run_in_container")
    def test_unknown_context_fails(self, mock_remote):
        containers = self.createContainers()
        containers[0]["labels"] = {
            "stack-back.hooks.pre.1.cmd": "echo x",
            "stack-back.hooks.pre.1.context": "nonexistent",
        }
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        pre = hooks.collect_hooks(
            "pre", running.this_container, running.containers_for_backup()
        )
        self.assertFalse(hooks.execute_hooks(pre, running))
        mock_remote.assert_not_called()

    @mock.patch(
        "restic_compose_backup.hooks._run_local", side_effect=Exception("boom")
    )
    def test_exception_treated_as_failure(self, mock_local):
        containers = self.createContainers()
        containers[0]["labels"] = {"stack-back.hooks.pre.1.cmd": "explode"}
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        pre = hooks.collect_hooks(
            "pre", running.this_container, running.containers_for_backup()
        )
        self.assertFalse(hooks.execute_hooks(pre, running))


class BackupOrderingTests(BaseTestCase):
    """Tests for ordered backup execution"""

    def test_default_unordered(self):
        containers = self.createContainers()
        containers += [
            {
                "service": "web",
                "labels": {"stack-back.volumes": True},
                "mounts": [
                    {"Source": "d", "Destination": "/d", "Type": "volume"},
                ],
            },
            {
                "service": "db",
                "labels": {"stack-back.mysql": True},
                "mounts": [
                    {
                        "Source": "m",
                        "Destination": "/var/lib/mysql",
                        "Type": "volume",
                    },
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        self.assertEqual(len(running.containers_for_backup()), 2)

    def test_ordered_containers(self):
        containers = self.createContainers()
        containers[0]["labels"] = {
            "stack-back.ordered": "true",
            "stack-back.order.1": "db",
            "stack-back.order.2": "web",
        }
        containers += [
            {
                "service": "web",
                "labels": {"stack-back.volumes": True},
                "mounts": [
                    {"Source": "d", "Destination": "/d", "Type": "volume"},
                ],
            },
            {
                "service": "db",
                "labels": {"stack-back.mysql": True},
                "mounts": [
                    {
                        "Source": "m",
                        "Destination": "/var/lib/mysql",
                        "Type": "volume",
                    },
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        backup = running.containers_for_backup()
        self.assertEqual(backup[0].service_name, "db")
        self.assertEqual(backup[1].service_name, "web")

    def test_ordered_with_gaps(self):
        containers = self.createContainers()
        containers[0]["labels"] = {
            "stack-back.ordered": "true",
            "stack-back.order.1": "db",
            "stack-back.order.5": "web",
        }
        containers += [
            {
                "service": "web",
                "labels": {"stack-back.volumes": True},
                "mounts": [
                    {"Source": "d", "Destination": "/d", "Type": "volume"},
                ],
            },
            {
                "service": "db",
                "labels": {"stack-back.mysql": True},
                "mounts": [
                    {
                        "Source": "m",
                        "Destination": "/var/lib/mysql",
                        "Type": "volume",
                    },
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        backup = running.containers_for_backup()
        self.assertEqual(backup[0].service_name, "db")
        self.assertEqual(backup[1].service_name, "web")

    def test_ordered_unknown_service_skipped(self):
        containers = self.createContainers()
        containers[0]["labels"] = {
            "stack-back.ordered": "true",
            "stack-back.order.1": "nonexistent",
            "stack-back.order.2": "web",
        }
        containers += [
            {
                "service": "web",
                "labels": {"stack-back.volumes": True},
                "mounts": [
                    {"Source": "d", "Destination": "/d", "Type": "volume"},
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        backup = running.containers_for_backup()
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0].service_name, "web")

    def test_unordered_container_appended(self):
        containers = self.createContainers()
        containers[0]["labels"] = {
            "stack-back.ordered": "true",
            "stack-back.order.1": "db",
        }
        containers += [
            {
                "service": "web",
                "labels": {"stack-back.volumes": True},
                "mounts": [
                    {"Source": "d", "Destination": "/d", "Type": "volume"},
                ],
            },
            {
                "service": "db",
                "labels": {"stack-back.mysql": True},
                "mounts": [
                    {
                        "Source": "m",
                        "Destination": "/var/lib/mysql",
                        "Type": "volume",
                    },
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        backup = running.containers_for_backup()
        self.assertEqual(len(backup), 2)
        self.assertEqual(backup[0].service_name, "db")
        self.assertEqual(backup[1].service_name, "web")

    def test_ordered_duplicate_service(self):
        containers = self.createContainers()
        containers[0]["labels"] = {
            "stack-back.ordered": "true",
            "stack-back.order.1": "web",
            "stack-back.order.2": "web",
        }
        containers += [
            {
                "service": "web",
                "labels": {"stack-back.volumes": True},
                "mounts": [
                    {"Source": "d", "Destination": "/d", "Type": "volume"},
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        backup = running.containers_for_backup()
        self.assertEqual(len(backup), 1)

    def test_ordered_true_no_labels_falls_back(self):
        containers = self.createContainers()
        containers[0]["labels"] = {"stack-back.ordered": "true"}
        containers += [
            {
                "service": "web",
                "labels": {"stack-back.volumes": True},
                "mounts": [
                    {"Source": "d", "Destination": "/d", "Type": "volume"},
                ],
            },
        ]
        with mock.patch(
            list_containers_func, fixtures.containers(containers=containers)
        ):
            running = RunningContainers()
        backup = running.containers_for_backup()
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0].service_name, "web")

