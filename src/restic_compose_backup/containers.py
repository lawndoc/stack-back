import os
import logging
from pathlib import Path
from typing import List

from restic_compose_backup import enums, utils
from restic_compose_backup.config import config

logger = logging.getLogger(__name__)

VOLUME_TYPE_BIND = "bind"
VOLUME_TYPE_VOLUME = "volume"


class Container:
    """Represents a docker container"""

    container_type = None

    def __init__(self, data: dict):
        self._data = data
        self._state = data.get("State")
        self._config = data.get("Config")
        self._mounts = [Mount(mnt, container=self) for mnt in data.get("Mounts")]

        if not self._state:
            raise ValueError("Container meta missing State")
        if self._config is None:
            raise ValueError("Container meta missing Config")

        self._labels = self._config.get("Labels")
        if self._labels is None:
            raise ValueError("Container meta missing Config->Labels")

        self._include = self._parse_pattern(self.get_label(enums.LABEL_VOLUMES_INCLUDE))
        self._exclude = self._parse_pattern(self.get_label(enums.LABEL_VOLUMES_EXCLUDE))

    @property
    def instance(self) -> "Container":
        """Container: Get a service specific subclass instance"""
        # TODO: Do this smarter in the future (simple registry)
        if self.database_backup_enabled:
            from restic_compose_backup import containers_db

            if self.mariadb_backup_enabled:
                return containers_db.MariadbContainer(self._data)
            if self.mysql_backup_enabled:
                return containers_db.MysqlContainer(self._data)
            if self.postgresql_backup_enabled:
                return containers_db.PostgresContainer(self._data)
        else:
            return self

    @property
    def id(self) -> str:
        """str: The id of the container"""
        return self._data.get("Id")

    @property
    def hostname(self) -> str:
        """Hostname of the container"""
        return self.get_config("Hostname", default=self.id[0:12])

    @property
    def image(self) -> str:
        """Image name"""
        return self.get_config("Image")

    @property
    def name(self) -> str:
        """Container name"""
        return self._data["Name"].replace("/", "")

    @property
    def service_name(self) -> str:
        """Name of the container/service"""
        return self.get_label(
            "com.docker.compose.service", default=""
        ) or self.get_label("com.docker.swarm.service.name", default="")

    @property
    def backup_process_label(self) -> str:
        """str: The unique backup process label for this project"""
        return f"{enums.LABEL_BACKUP_PROCESS}-{self.project_name}"

    @property
    def project_name(self) -> str:
        """str: Name of the compose setup"""
        return self.get_label("com.docker.compose.project", default="")

    @property
    def stack_name(self) -> str:
        """str: Name of the stack is present"""
        return self.get_label("com.docker.stack.namespace")

    @property
    def is_oneoff(self) -> bool:
        """Was this container started with run command?"""
        return self.get_label("com.docker.compose.oneoff", default="False") == "True"

    @property
    def environment(self) -> list:
        """All configured env vars for the container as a list"""
        return self.get_config("Env")

    def remove(self):
        self._data.remove()

    def get_config_env(self, name) -> str:
        """Get a config environment variable by name"""
        # convert to dict and fetch env var by name
        data = {i[0 : i.find("=")]: i[i.find("=") + 1 :] for i in self.environment}
        return data.get(name)

    def set_config_env(self, name, value):
        """Set an environment variable"""
        env = self.environment
        new_value = f"{name}={value}"
        for i, entry in enumerate(env):
            if f"{name}=" in entry:
                env[i] = new_value
                break
        else:
            env.append(new_value)

    @property
    def volumes(self) -> dict:
        """
        Return volumes for the container in the following format:
            {'/home/user1/': {'bind': '/mnt/vol2', 'mode': 'rw'},}
        """
        volumes = {}
        for mount in self._mounts:
            volumes[mount.source] = {
                "bind": mount.destination,
                "mode": "rw",
            }

        return volumes

    @property
    def backup_enabled(self) -> bool:
        """Is backup enabled for this container?"""
        return any(
            [
                self.volume_backup_enabled,
                self.database_backup_enabled,
            ]
        )

    @property
    def volume_backup_enabled(self) -> bool:
        """bool: If the ``stack-back.volumes`` label is set"""
        label_value = self.get_label(enums.LABEL_VOLUMES_ENABLED)

        return utils.is_true(label_value) or (
            utils.is_true(config.auto_backup_all) and label_value is None
        )

    @property
    def database_backup_enabled(self) -> bool:
        """bool: Is database backup enabled in any shape or form?"""
        return any(
            [
                self.mysql_backup_enabled,
                self.mariadb_backup_enabled,
                self.postgresql_backup_enabled,
            ]
        )

    @property
    def mysql_backup_enabled(self) -> bool:
        """bool: If the ``stack-back.mysql`` label is set"""
        explicity_enabled = utils.is_true(self.get_label(enums.LABEL_MYSQL_ENABLED))
        explicity_disabled = utils.is_false(self.get_label(enums.LABEL_MYSQL_ENABLED))
        automatically_enabled = utils.is_true(
            config.auto_backup_all
        ) and self.image.startswith("mysql:")
        return explicity_enabled or (automatically_enabled and not explicity_disabled)

    @property
    def mariadb_backup_enabled(self) -> bool:
        """bool: If the ``stack-back.mariadb`` label is set"""
        explicity_enabled = utils.is_true(self.get_label(enums.LABEL_MARIADB_ENABLED))
        explicity_disabled = utils.is_false(self.get_label(enums.LABEL_MARIADB_ENABLED))
        automatically_enabled = utils.is_true(
            config.auto_backup_all
        ) and self.image.startswith("mariadb:")
        return explicity_enabled or (automatically_enabled and not explicity_disabled)

    @property
    def postgresql_backup_enabled(self) -> bool:
        """bool: If the ``stack-back.postgres`` label is set"""
        explicity_enabled = utils.is_true(self.get_label(enums.LABEL_POSTGRES_ENABLED))
        explicity_disabled = utils.is_false(
            self.get_label(enums.LABEL_POSTGRES_ENABLED)
        )
        automatically_enabled = utils.is_true(
            config.auto_backup_all
        ) and self.image.startswith("postgres:")
        return explicity_enabled or (automatically_enabled and not explicity_disabled)

    @property
    def stop_during_backup(self) -> bool:
        """bool: If the ``stack-back.volumes.stop-during-backup`` label is set"""
        return (
            utils.is_true(self.get_label(enums.LABEL_STOP_DURING_BACKUP))
            and not self.database_backup_enabled
        )

    @property
    def is_backup_process_container(self) -> bool:
        """Is this container the running backup process?"""
        return self.get_label(self.backup_process_label) == "True"

    @property
    def is_running(self) -> bool:
        """bool: Is the container running?"""
        return self._state.get("Running", False)

    def get_config(self, name, default=None):
        """Get value from config dict"""
        return self._config.get(name, default)

    def get_label(self, name, default=None):
        """Get a label by name"""
        return self._labels.get(name, None)

    def filter_mounts(self):
        """Get all mounts for this container matching include/exclude filters"""
        filtered = []
        database_mounts = ["/var/lib/mysql", "/var/lib/postgresql/data"]

        # If exclude_bind_mounts is true, only volume mounts are kept in the list of mounts
        exclude_bind_mounts = utils.is_true(config.exclude_bind_mounts)
        mounts = list(
            filter(
                lambda m: not exclude_bind_mounts or m.type == "volume", self._mounts
            )
        )

        if not self.volume_backup_enabled:
            return filtered

        if self._include:
            for mount in mounts:
                for pattern in self._include:
                    if pattern in mount.source:
                        break
                else:
                    continue

                filtered.append(mount)

        elif self._exclude:
            for mount in mounts:
                for pattern in self._exclude:
                    if pattern in mount.source:
                        break
                else:
                    filtered.append(mount)
        else:
            for mount in mounts:
                if (
                    self.database_backup_enabled
                    and mount.destination in database_mounts
                ):
                    continue
                filtered.append(mount)

        return filtered

    def volumes_for_backup(self, source_prefix="/volumes", mode="ro"):
        """Get volumes configured for backup"""
        mounts = self.filter_mounts()
        volumes = {}
        for mount in mounts:
            volumes[mount.source] = {
                "bind": self.get_volume_backup_destination(mount, source_prefix),
                "mode": mode,
            }

        return volumes

    def get_volume_backup_destination(self, mount, source_prefix) -> str:
        """Get the destination path for backups of the given mount"""
        destination = Path(source_prefix)

        if utils.is_true(config.include_project_name):
            project_name = self.project_name
            if project_name != "":
                destination /= project_name

        destination /= self.service_name
        destination /= Path(utils.strip_root(mount.destination))

        return str(destination)

    def get_credentials(self) -> dict:
        """dict: get credentials for the service"""
        raise NotImplementedError("Base container class don't implement this")

    def ping(self) -> bool:
        """Check the availability of the service"""
        raise NotImplementedError("Base container class don't implement this")

    def backup(self):
        """Back up this service"""
        raise NotImplementedError("Base container class don't implement this")

    def backup_destination_path(self) -> str:
        """Return the path backups will be saved at"""
        raise NotImplementedError("Base container class don't implement this")

    def dump_command(self) -> list:
        """list: create a dump command restic and use to send data through stdin"""
        raise NotImplementedError("Base container class don't implement this")

    def _parse_pattern(self, value: str) -> List[str]:
        """list: Safely parse include/exclude pattern from user"""
        if not value:
            return None

        if type(value) is not str:
            return None

        value = value.strip()
        if len(value) == 0:
            return None

        return value.split(",")

    def __eq__(self, other):
        """Compare container by id"""
        if other is None:
            return False

        if not isinstance(other, Container):
            return False

        return self.id == other.id

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "<Container {}>".format(self.name)


class Mount:
    """Represents a volume mount (volume or bind)"""

    def __init__(self, data, container=None):
        self._data = data
        self._container = container

    @property
    def container(self) -> Container:
        """The container this mount belongs to"""
        return self._container

    @property
    def type(self) -> str:
        """bind/volume"""
        return self._data.get("Type")

    @property
    def name(self) -> str:
        """Name of the mount"""
        return self._data.get("Name")

    @property
    def source(self) -> str:
        """Source of the mount. Volume name or path"""
        return self._data.get("Source")

    @property
    def destination(self) -> str:
        """Destination path for the volume mount in the container"""
        return self._data.get("Destination")

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return str(self._data)

    def __hash__(self):
        """Uniqueness for a volume"""
        if self.type == VOLUME_TYPE_VOLUME:
            return hash(self.name)
        elif self.type == VOLUME_TYPE_BIND:
            return hash(self.source)
        else:
            raise ValueError("Unknown volume type: {}".format(self.type))


class RunningContainers:
    def __init__(self):
        all_containers = utils.list_containers()
        self.containers = []
        self.this_container = None
        self.backup_process_container = None
        self.stale_backup_process_containers = []
        self.stop_during_backup_containers = []

        # Find the container we are running in.
        # If we don't have this information we cannot continue
        for container_data in all_containers:
            if container_data.get("Id").startswith(os.environ["HOSTNAME"]):
                self.this_container = Container(container_data)

        if not self.this_container:
            raise ValueError("Cannot find metadata for backup container")

        # Gather all running containers in the current compose setup
        for container_data in all_containers:
            container = Container(container_data)

            # Gather stale backup process containers
            if (
                self.this_container.image == container.image
                and not container.is_running
                and container.is_backup_process_container
            ):
                self.stale_backup_process_containers.append(container)

            # We only care about running containers after this point
            if not container.is_running:
                continue

            # Gather stop during backup containers
            if container.stop_during_backup:
                if config.swarm_mode:
                    self.stop_during_backup_containers.append(container)
                else:
                    if container.project_name == self.this_container.project_name:
                        self.stop_during_backup_containers.append(container)

            # Detect running backup process container
            if container.is_backup_process_container:
                self.backup_process_container = container

            # --- Determine what containers should be evaluated

            # If not swarm mode we need to filter in compose project
            if not config.swarm_mode:
                if container.project_name != self.this_container.project_name:
                    continue

            # Containers started manually are not included
            if container.is_oneoff:
                continue

            # Do not include the backup process container
            if container == self.backup_process_container:
                continue

            self.containers.append(container)

    @property
    def project_name(self) -> str:
        """str: Name of the compose project"""
        return self.this_container.project_name

    @property
    def backup_process_label(self) -> str:
        """str: The backup process label for this project"""
        return self.this_container.backup_process_label

    @property
    def backup_process_running(self) -> bool:
        """Is the backup process container running?"""
        return self.backup_process_container is not None

    def containers_for_backup(self):
        """Obtain all containers with backup enabled"""
        return [container for container in self.containers if container.backup_enabled]

    def generate_backup_mounts(self, dest_prefix="/volumes") -> dict:
        """Generate mounts for backup for the entire compose setup"""
        mounts = {}
        for container in self.containers_for_backup():
            if container.volume_backup_enabled:
                mounts.update(
                    container.volumes_for_backup(source_prefix=dest_prefix, mode="ro")
                )

        return mounts

    def get_service(self, name) -> Container:
        """Container: Get a service by name"""
        for container in self.containers:
            if container.service_name == name:
                return container

        return None
