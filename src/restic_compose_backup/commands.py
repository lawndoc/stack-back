import logging
from typing import List, Tuple
from subprocess import Popen, PIPE

logger = logging.getLogger(__name__)


def test():
    return run(["ls", "/volumes"])


def ping_mysql(host, port, username) -> int:
    """Check if the mysql is up and can be reached"""
    return run(
        [
            "mysqladmin",
            "ping",
            "--host",
            host,
            "--port",
            port,
            "--user",
            username,
        ]
    )


def ping_mariadb(host, port, username) -> int:
    """Check if the mariadb is up and can be reached"""
    return run([
        'mariadb-admin',
        'ping',
        '--host',
        host,
        '--port',
        port,
        '--user',
        username,
    ])


def ping_postgres(host, port, username, password) -> int:
    """Check if postgres can be reached"""
    return run(
        [
            "pg_isready",
            f"--host={host}",
            f"--port={port}",
            f"--username={username}",
        ]
    )


def run(cmd: List[str]) -> int:
    """Run a command with parameters"""
    logger.debug("cmd: %s", " ".join(cmd))
    child = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdoutdata, stderrdata = child.communicate()

    if stdoutdata.strip():
        log_std(
            "stdout",
            stdoutdata.decode(),
            logging.DEBUG if child.returncode == 0 else logging.ERROR,
        )

    if stderrdata.strip():
        log_std("stderr", stderrdata.decode(), logging.ERROR)

    logger.debug("returncode %s", child.returncode)
    return child.returncode


def run_capture_std(cmd: List[str]) -> Tuple[str, str]:
    """Run a command with parameters and return stdout, stderr"""
    logger.debug("cmd: %s", " ".join(cmd))
    child = Popen(cmd, stdout=PIPE, stderr=PIPE)
    return child.communicate()


def log_std(source: str, data: str, level: int):
    if isinstance(data, bytes):
        data = data.decode()

    if not data.strip():
        return

    log_func = logger.debug if level == logging.DEBUG else logger.error
    log_func("%s %s %s", "-" * 10, source, "-" * 10)

    lines = data.split("\n")
    if lines[-1] == "":
        lines.pop()

    for line in lines:
        log_func(line)

    log_func("-" * 28)
