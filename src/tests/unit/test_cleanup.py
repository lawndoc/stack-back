"""Unit tests for maintenance cleanup result handling"""

from unittest import mock

import pytest

from restic_compose_backup import cli

pytestmark = pytest.mark.unit


class CleanupTests:
    """Tests for reporting failures from forget and prune."""

    @pytest.mark.parametrize(
        ("forget_result", "prune_result", "expected"),
        [
            (0, 0, 0),
            (1, 0, 1),
            (0, 1, 1),
            (1, 2, 1),
        ],
    )
    def test_cleanup_returns_failure_if_either_operation_fails(
        self, forget_result, prune_result, expected
    ):
        config = mock.Mock(
            repository="repository",
            keep_daily=1,
            keep_weekly=2,
            keep_monthly=3,
            keep_yearly=4,
        )
        containers = mock.Mock()

        with (
            mock.patch.object(
                cli.restic, "forget", return_value=forget_result
            ) as forget,
            mock.patch.object(cli.restic, "prune", return_value=prune_result) as prune,
        ):
            result = cli.cleanup(config, containers)

        assert result == expected
        forget.assert_called_once_with("repository", 1, 2, 3, 4)
        prune.assert_called_once_with("repository")
