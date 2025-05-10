import os
import logging
from typing import List, TYPE_CHECKING
from contextlib import contextmanager
import docker

if TYPE_CHECKING:
    from restic_compose_backup.containers import Container

logger = logging.getLogger(__name__)

TRUE_VALUES = ['1', 'true', 'True', 'TRUE', True, 1]
FALSE_VALUES = ['0', 'false', 'False', 'FALSE', False, 0]


def docker_client():
    """
    Create a docker client from the following environment variables::

        DOCKER_HOST=unix://tmp/docker.sock
        DOCKER_TLS_VERIFY=1
        DOCKER_CERT_PATH=''
    """
    # NOTE: Remove this fallback in 1.0
    if not os.environ.get('DOCKER_HOST'):
        os.environ['DOCKER_HOST'] = 'unix://tmp/docker.sock'

    return docker.from_env()


def list_containers() -> List[dict]:
    """
    List all containers.

    Returns:
        List of raw container json data from the api
    """
    client = docker_client()
    all_containers = client.containers.list(all=True)
    client.close()
    return [c.attrs for c in all_containers]


def get_swarm_nodes():
    client = docker_client()
    # NOTE: If not a swarm node docker.errors.APIError is raised
    #       503 Server Error: Service Unavailable
    #       ("This node is not a swarm manager. Use "docker swarm init" or
    #       "docker swarm join" to connect this node to swarm and try again.")
    try:
        return client.nodes.list()
    except docker.errors.APIError:
        return []


def remove_containers(containers: List['Container']):
    client = docker_client()
    logger.info('Attempting to delete stale backup process containers')
    for container in containers:
        logger.info(' -> deleting %s', container.name)
        try:
            c = client.containers.get(container.name)
            c.remove()
        except Exception as ex:
            logger.exception(ex)
            
def stop_containers(containers: List['Container']):
    client = docker_client()
    logger.info('Attempting to stop containers labeled to stop during backup')
    for container in containers:
        logger.info(' -> stopping %s', container.name)
        try:
            c = client.containers.get(container.name)
            c.stop()
        except Exception as ex:
            logger.exception(ex)
            
def start_containers(containers: List['Container']):
    client = docker_client()
    logger.info('Attempting to restart containers that were stopped during backup')
    for container in containers:
        logger.info(' -> starting %s', container.name)
        try:
            c = client.containers.get(container.name)
            c.start()
        except Exception as ex:
            logger.exception(ex)


def is_true(value):
    """
    Evaluates the truthfullness of a bool value in container labels
    """
    return value in TRUE_VALUES


def is_false(value):
    """
    Evaluates the falseness of a bool value in container labels
    """
    return value in FALSE_VALUES


def strip_root(path):
    """
    Removes the root slash in a path.
    Example: /srv/data becomes srv/data
    """
    path = path.strip()
    if path.startswith('/'):
        return path[1:]

    return path


@contextmanager
def environment(name, value):
    """Tempset env var"""
    old_val = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old_val is None:
            del os.environ[name]
        else:
            os.environ[name] = old_val
