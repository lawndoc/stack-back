import logging
import os

from restic_compose_backup import utils

logger = logging.getLogger(__name__)


def run(
    image: str = None,
    command: str = None,
    volumes: dict = None,
    environment: dict = None,
    labels: dict = None,
    source_container_id: str = None,
):
    logger.info("Starting backup container")
    client = utils.docker_client()

    container = client.containers.run(
        image,
        command,
        labels=labels,
        detach=True,
        environment=environment + ["BACKUP_PROCESS_CONTAINER=true"],
        volumes=volumes,
        network_mode=f"container:{source_container_id}",  # reuse original container network for optional access to docker proxy
        working_dir=os.getcwd(),
        tty=True,
    )

    logger.info("Backup process container: %s", container.name)
    log_generator = container.logs(stdout=True, stderr=True, stream=True, follow=True)

    def readlines(stream):
        """Read stream line by line"""
        while True:
            line = ""
            while True:
                try:
                    # Make log streaming work for docker ce 17 and 18.
                    # For some reason strings are returned instead if bytes.
                    data = next(stream)
                    if isinstance(data, bytes):
                        line += data.decode()
                    elif isinstance(data, str):
                        line += data
                    if line.endswith("\n"):
                        break
                except StopIteration:
                    break
            if line:
                yield line.rstrip()
            else:
                break

    with open("backup.log", "w") as fd:
        for line in readlines(log_generator):
            fd.write(line)
            fd.write("\n")
            print(line)

    container.wait()
    container.reload()
    logger.debug("Container ExitCode %s", container.attrs["State"]["ExitCode"])
    container.remove()

    return container.attrs["State"]["ExitCode"]
