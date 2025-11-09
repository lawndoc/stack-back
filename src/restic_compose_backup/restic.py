"""
Restic commands
"""

import logging
from typing import List, Tuple, Union
from subprocess import Popen, PIPE
from restic_compose_backup import commands, utils

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


def backup_from_stdin(repository: str, filename: str, container_id: str, source_command: List[str], environment: Union[dict, list] = None):
    """
    Backs up from stdin running the source_command passed in within the given container.
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

    client = utils.docker_client()

    logger.debug(f"docker exec inside container {container_id} command: {' '.join(source_command)}")

    # Create and start  source command inside the given container
    handle = client.api.exec_create(container_id, source_command, environment=environment)
    exec_id = handle.get("Id")
    stream = client.api.exec_start(exec_id, stream=True, demux=True)
    source_stderr = ""

    # Create the restic process to receive the output of the source command
    dest_process = Popen(dest_command, stdin=PIPE, stdout=PIPE, stderr=PIPE, bufsize=65536)

    # Send the output of the source command over to restic in the chunks received
    for stdout_chunk, stderr_chunk in stream:
        if stdout_chunk:
            dest_process.stdin.write(stdout_chunk)
        if stderr_chunk:
            source_stderr += stderr_chunk.decode()

    # Wait for restic to finish
    stdout, stderr = dest_process.communicate()

    # Ensure both processes exited with code 0
    source_exit = client.api.exec_inspect(exec_id).get("ExitCode")
    dest_exit = dest_process.poll()
    exit_code = source_exit or dest_exit

    if stdout:
        commands.log_std(
            "stdout", stdout, logging.DEBUG if exit_code == 0 else logging.ERROR
        )

    if source_stderr:
        commands.log_std(f"stderr ({source_command[0]})", source_stderr, logging.ERROR)

    if stderr:
        commands.log_std("stderr (restic)", stderr, logging.ERROR)

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
