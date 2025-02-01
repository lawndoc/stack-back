from pathlib import Path

from restic_compose_backup.containers import Container
from restic_compose_backup.config import config, Config
from restic_compose_backup import (
    commands,
    restic,
)
from restic_compose_backup import utils


class MariadbContainer(Container):
    container_type = 'mariadb'

    def get_credentials(self) -> dict:
        """dict: get credentials for the service"""
        password = self.get_config_env('MARIADB_ROOT_PASSWORD')
        if password is not None:
            username = "root"
        else:
            username = self.get_config_env('MARIADB_USER')
            password = self.get_config_env('MARIADB_PASSWORD')
        return {
            'host': self.hostname,
            'username': username,
            'password': password,
            'port': "3306",
        }

    def ping(self) -> bool:
        """Check the availability of the service"""
        creds = self.get_credentials()

        with utils.environment('MYSQL_PWD', creds['password']):
            return commands.ping_mariadb(
                creds['host'],
                creds['port'],
                creds['username'],
            )

    def dump_command(self) -> list:
        """list: create a dump command restic and use to send data through stdin"""
        creds = self.get_credentials()
        return [
            "mysqldump",
            f"--host={creds['host']}",
            f"--port={creds['port']}",
            f"--user={creds['username']}",
            "--all-databases",
            "--no-tablespaces",
            "--single-transaction",
            "--order-by-primary",
            "--compact",
            "--force"
        ]

    def backup(self):
        config = Config()
        creds = self.get_credentials()

        with utils.environment('MYSQL_PWD', creds['password']):
            return restic.backup_from_stdin(
                config.repository,
                self.backup_destination_path(),
                self.dump_command(),
            )

    def backup_destination_path(self) -> str:
        destination = Path("/databases")

        if utils.is_true(config.include_project_name):
            project_name = self.project_name
            if project_name != "":
                destination /= project_name

        destination /= self.service_name
        destination /= "all_databases.sql"

        return destination


class MysqlContainer(Container):
    container_type = 'mysql'

    def get_credentials(self) -> dict:
        """dict: get credentials for the service"""
        password = self.get_config_env('MYSQL_ROOT_PASSWORD')
        if password is not None:
            username = "root"
        else:
            username = self.get_config_env('MYSQL_USER')
            password = self.get_config_env('MYSQL_PASSWORD')
        return {
            'host': self.hostname,
            'username': username,
            'password': password,
            'port': "3306",
        }

    def ping(self) -> bool:
        """Check the availability of the service"""
        creds = self.get_credentials()

        with utils.environment('MYSQL_PWD', creds['password']):
            return commands.ping_mysql(
                creds['host'],
                creds['port'],
                creds['username'],
            )

    def dump_command(self) -> list:
        """list: create a dump command restic and use to send data through stdin"""
        creds = self.get_credentials()
        return [
            "mysqldump",
            f"--host={creds['host']}",
            f"--port={creds['port']}",
            f"--user={creds['username']}",
            "--all-databases",
            "--no-tablespaces",
            "--single-transaction",
            "--order-by-primary",
            "--compact",
            "--force"
        ]

    def backup(self):
        config = Config()
        creds = self.get_credentials()

        with utils.environment('MYSQL_PWD', creds['password']):
            return restic.backup_from_stdin(
                config.repository,
                self.backup_destination_path(),
                self.dump_command(),
            )

    def backup_destination_path(self) -> str:
        destination = Path("/databases")

        if utils.is_true(config.include_project_name):
            project_name = self.project_name
            if project_name != "":
                destination /= project_name

        destination /= self.service_name
        destination /= "all_databases.sql"

        return destination


class PostgresContainer(Container):
    container_type = 'postgres'

    def get_credentials(self) -> dict:
        """dict: get credentials for the service"""
        return {
            'host': self.hostname,
            'username': self.get_config_env('POSTGRES_USER'),
            'password': self.get_config_env('POSTGRES_PASSWORD'),
            'port': "5432",
            'database': self.get_config_env('POSTGRES_DB'),
        }

    def ping(self) -> bool:
        """Check the availability of the service"""
        creds = self.get_credentials()
        return commands.ping_postgres(
            creds['host'],
            creds['port'],
            creds['username'],
            creds['password'],
        )

    def dump_command(self) -> list:
        """list: create a dump command restic and use to send data through stdin"""
        # NOTE: Backs up a single database from POSTGRES_DB env var
        creds = self.get_credentials()
        return [
            "pg_dump",
            f"--host={creds['host']}",
            f"--port={creds['port']}",
            f"--username={creds['username']}",
            creds['database'],
        ]

    def backup(self):
        config = Config()
        creds = self.get_credentials()

        with utils.environment('PGPASSWORD', creds['password']):
            return restic.backup_from_stdin(
                config.repository,
                self.backup_destination_path(),
                self.dump_command(),
            )

    def backup_destination_path(self) -> str:
        destination = Path("/databases")

        if utils.is_true(config.include_project_name):
            project_name = self.project_name
            if project_name != "":
                destination /= project_name

        destination /= self.service_name
        destination /= f"{self.get_credentials()['database']}.sql"

        return destination
