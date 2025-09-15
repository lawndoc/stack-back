import logging
import os

logger = logging.getLogger(__name__)


class Config:
    default_backup_command = "source /.env && rcb backup > /proc/1/fd/1"
    default_crontab_schedule = "0 2 * * *"
    default_maintenance_command = "source /.env && rcb maintenance > /proc/1/fd/1"

    """Bag for config values"""

    def __init__(self, check=True):
        # Mandatory values
        self.repository = os.environ.get("RESTIC_REPOSITORY")
        self.password = os.environ.get("RESTIC_REPOSITORY")
        self.check_with_cache = os.environ.get("CHECK_WITH_CACHE") or False
        self.cron_schedule = (
            os.environ.get("CRON_SCHEDULE") or self.default_crontab_schedule
        )
        self.cron_command = (
            os.environ.get("CRON_COMMAND") or self.default_backup_command
        )
        self.maintenance_schedule = os.environ.get("MAINTENANCE_SCHEDULE") or ""
        self.maintenance_command = (
            os.environ.get("MAINTENANCE_COMMAND") or self.default_maintenance_command
        )
        self.swarm_mode = os.environ.get("SWARM_MODE") or False
        self.include_project_name = os.environ.get("INCLUDE_PROJECT_NAME") or False
        self.exclude_bind_mounts = os.environ.get("EXCLUDE_BIND_MOUNTS") or False
        self.include_all_compose_projects = os.environ.get("INCLUDE_ALL_COMPOSE_PROJECTS") or False
        self.include_all_volumes = os.environ.get("INCLUDE_ALL_VOLUMES") or False
        if self.include_all_volumes:
            logger.warning(
                "INCLUDE_ALL_VOLUMES will be deprecated in the future in favor of AUTO_BACKUP_ALL. Please update your environment variables."
            )
        self.auto_backup_all = (
            os.environ.get("AUTO_BACKUP_ALL") or self.include_all_volumes
        )

        # Log
        self.log_level = os.environ.get("LOG_LEVEL")

        # forget / keep
        self.keep_daily = (
            os.environ.get("RESTIC_KEEP_DAILY") or os.environ.get("KEEP_DAILY") or "7"
        )
        self.keep_weekly = (
            os.environ.get("RESTIC_KEEP_WEEKLY") or os.environ.get("KEEP_WEEKLY") or "4"
        )
        self.keep_monthly = (
            os.environ.get("RESTIC_KEEP_MONTHLY")
            or os.environ.get("KEEP_MONTHLY")
            or "12"
        )
        self.keep_yearly = (
            os.environ.get("RESTIC_KEEP_YEARLY") or os.environ.get("KEEP_YEARLY") or "3"
        )

        if check:
            self.check()

    def check(self):
        if not self.repository:
            raise ValueError("RESTIC_REPOSITORY env var not set")

        if not self.password:
            raise ValueError("RESTIC_REPOSITORY env var not set")


config = Config()
