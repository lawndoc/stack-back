"""
Restic commands
"""

import logging
from typing import List, Tuple
from subprocess import Popen, PIPE
from restic_compose_backup import commands

logger = logging.getLogger(__name__)


def init_repo(repository: str):
    """
    Attempt to initialize the repository.
    Doing this after the repository is initialized
    """
    return commands.run(
        restic(
            repository,
            [
                "init",
            ],
        )
    )


def backup_files(repository: str, source="/volumes"):
    return commands.run(
        restic(
            repository,
            [
                "--verbose",
                "backup",
                source,
            ],
        )
    )


def backup_from_stdin(repository: str, filename: str, source_command: List[str]):
    """
    Backs up from stdin running the source_command passed in.
    It will appear in restic with the filename (including path) passed in.
    """
    dest_command = restic(
        repository,
        [
            "backup",
            "--stdin",
            "--stdin-filename",
            filename,
        ],
    )

    # pipe source command into dest command
    source_process = Popen(source_command, stdout=PIPE, bufsize=65536)
    dest_process = Popen(
        dest_command,
        stdin=source_process.stdout,
        stdout=PIPE,
        stderr=PIPE,
        bufsize=65536,
    )
    stdout, stderr = dest_process.communicate()

    # Ensure both processes exited with code 0
    source_exit, dest_exit = source_process.poll(), dest_process.poll()
    exit_code = 0 if (source_exit == 0 and dest_exit == 0) else 1

    if stdout:
        commands.log_std(
            "stdout", stdout, logging.DEBUG if exit_code == 0 else logging.ERROR
        )

    if stderr:
        commands.log_std("stderr", stderr, logging.ERROR)

    return exit_code


def snapshots(repository: str, last=True) -> Tuple[str, str]:
    """Returns the stdout and stderr info"""
    args = ["snapshots"]
    if last:
        args.append("--latest")
        args.append("1")
    return commands.run_capture_std(restic(repository, args))


def is_initialized(repository: str) -> bool:
    """
    Checks if a repository is initialized with restic cat config.
    https://restic.readthedocs.io/en/latest/075_scripting.html#check-if-a-repository-is-already-initialized
    """
    response = commands.run(restic(repository, ["cat", "config"]))
    if response == 0:
        return True
    elif response == 10:
        return False
    else:
        logger.error("Error while checking if repository is initialized")
        exit(1)


def forget(repository: str, daily: str, weekly: str, monthly: str, yearly: str):
    return commands.run(
        restic(
            repository,
            [
                "forget",
                "--group-by",
                "paths",
                "--keep-daily",
                daily,
                "--keep-weekly",
                weekly,
                "--keep-monthly",
                monthly,
                "--keep-yearly",
                yearly,
            ],
        )
    )


def prune(repository: str):
    return commands.run(
        restic(
            repository,
            [
                "prune",
            ],
        )
    )


def check(repository: str, with_cache: bool = False):
    check_args = ["check"]
    if with_cache:
        check_args.append("--with-cache")
    return commands.run(restic(repository, check_args))


def restic(repository: str, args: List[str]):
    """Generate restic command"""
    return [
        "restic",
        "-r",
        repository,
    ] + args
