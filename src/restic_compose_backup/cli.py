import argparse
import os
import logging

from restic_compose_backup import (
    alerts,
    backup_runner,
    log,
    restic,
)
from restic_compose_backup.config import Config
from restic_compose_backup.containers import RunningContainers
from restic_compose_backup import cron, utils

logger = logging.getLogger(__name__)


def main():
    """CLI entrypoint"""
    args = parse_args()
    config = Config()
    log.setup(level=args.log_level or config.log_level)
    containers = RunningContainers()

    # Ensure log level is propagated to parent container if overridden
    if args.log_level:
        containers.this_container.set_config_env("LOG_LEVEL", args.log_level)

    if args.action == "status":
        status(config, containers)

    elif args.action == "snapshots":
        snapshots(config, containers)

    elif args.action == "backup":
        backup(config, containers)

    elif args.action == "start-backup-process":
        start_backup_process(config, containers)

    elif args.action == "maintenance":
        maintenance(config, containers)

    elif args.action == "cleanup":
        cleanup(config, containers)

    elif args.action == "alert":
        alert(config, containers)

    elif args.action == "version":
        import restic_compose_backup

        print(restic_compose_backup.__version__)

    elif args.action == "crontab":
        crontab(config)

    elif args.action == "dump-env":
        dump_env()

    # Random test stuff here
    elif args.action == "test":
        nodes = utils.get_swarm_nodes()
        print("Swarm nodes:")
        for node in nodes:
            addr = node.attrs["Status"]["Addr"]
            state = node.attrs["Status"]["State"]
            print(" - {} {} {}".format(node.id, addr, state))


def status(config, containers):
    """Outputs the backup config for the compose setup"""
    logger.info("Status for compose project '%s'", containers.project_name)
    logger.info("Repository: '%s'", config.repository)
    logger.info("Backup currently running?: %s", containers.backup_process_running)
    logger.info(
        "Include project name in backup path?: %s",
        utils.is_true(config.include_project_name),
    )
    logger.debug(
        "Exclude bind mounts from backups?: %s",
        utils.is_true(config.exclude_bind_mounts),
    )
    logger.debug(
        f"Use cache for integrity check?: {utils.is_true(config.check_with_cache)}"
    )
    logger.info("Checking docker availability")

    utils.list_containers()

    if containers.stale_backup_process_containers:
        utils.remove_containers(containers.stale_backup_process_containers)

    logger.info("Contacting repository")
    if not restic.is_initialized(config.repository):
        logger.info("Repository is not initialized. Attempting to initialize it.")
        result = restic.init_repo(config.repository)
        if result == 0:
            logger.info("Successfully initialized repository: %s", config.repository)
        else:
            logger.error("Failed to initialize repository")

    logger.info("%s Detected Config %s", "-" * 25, "-" * 25)

    # Start making snapshots
    backup_containers = containers.containers_for_backup()
    for container in backup_containers:
        logger.info("service: %s", container.service_name)

        if container.volume_backup_enabled:
            logger.info(f" - stop during backup: {container.stop_during_backup}")
            for mount in container.filter_mounts():
                logger.info(
                    " - volume: %s -> %s",
                    mount.source,
                    container.get_volume_backup_destination(mount, "/volumes"),
                )

        if container.database_backup_enabled:
            instance = container.instance
            ping = instance.ping()
            logger.info(
                " - %s (is_ready=%s) -> %s",
                instance.container_type,
                ping == 0,
                instance.backup_destination_path(),
            )
            if ping != 0:
                logger.error(
                    "Database '%s' in service %s cannot be reached",
                    instance.container_type,
                    container.service_name,
                )

    if len(backup_containers) == 0:
        logger.info("No containers in the project has 'stack-back.*' label")

    logger.info("-" * 67)


def backup(config, containers: RunningContainers):
    """Request a backup to start"""
    # Make sure we don't spawn multiple backup processes
    if containers.backup_process_running:
        alerts.send(
            subject="Backup process container already running",
            body=(
                "A backup process container is already running. \n"
                f"Id: {containers.backup_process_container.id}\n"
                f"Name: {containers.backup_process_container.name}\n"
            ),
            alert_type="ERROR",
        )
        raise RuntimeError("Backup process already running")

    # Map all volumes from the backup container into the backup process container
    volumes = containers.this_container.volumes

    # Map volumes from other containers we are backing up
    mounts = containers.generate_backup_mounts("/volumes")
    volumes.update(mounts)

    logger.debug(
        "Starting backup container with image %s", containers.this_container.image
    )
    try:
        result = backup_runner.run(
            image=containers.this_container.image,
            command="rcb start-backup-process",
            volumes=volumes,
            environment=containers.this_container.environment,
            source_container_network=containers.this_container.network_name,
            labels={
                containers.backup_process_label: "True",
                "com.docker.compose.project": containers.project_name,
            },
        )
    except Exception as ex:
        logger.exception(ex)
        alerts.send(
            subject="Exception during backup",
            body=str(ex),
            alert_type="ERROR",
        )
        return

    logger.info("Backup container exit code: %s", result)

    # Alert the user if something went wrong
    if result != 0:
        alerts.send(
            subject="Backup process exited with non-zero code",
            body=open("backup.log").read(),
            alert_type="ERROR",
        )


def start_backup_process(config, containers):
    """The actual backup process running inside the spawned container"""
    if not utils.is_true(os.environ.get("BACKUP_PROCESS_CONTAINER")):
        logger.error(
            "Cannot run backup process in this container. Use backup command instead. "
            "This will spawn a new container with the necessary mounts."
        )
        alerts.send(
            subject="Cannot run backup process in this container",
            body=(
                "Cannot run backup process in this container. Use backup command instead. "
                "This will spawn a new container with the necessary mounts."
            ),
        )
        exit(1)

    status(config, containers)
    errors = False

    # Did we actually get any volumes mounted?
    try:
        has_volumes = os.stat("/volumes") is not None
    except FileNotFoundError:
        logger.warning("Found no volumes to back up")
        has_volumes = False

    # Warn if there is nothing to do
    if len(containers.containers_for_backup()) == 0 and not has_volumes:
        logger.error("No containers for backup found")
        exit(1)

    # stop containers labeled to stop during backup
    if len(containers.stop_during_backup_containers) > 0:
        utils.stop_containers(containers.stop_during_backup_containers)

    # back up volumes
    if has_volumes:
        try:
            logger.info("Backing up volumes")
            vol_result = restic.backup_files(config.repository, source="/volumes")
            logger.debug("Volume backup exit code: %s", vol_result)
            if vol_result != 0:
                logger.error("Volume backup exited with non-zero code: %s", vol_result)
                errors = True
        except Exception as ex:
            logger.error("Exception raised during volume backup")
            logger.exception(ex)
            errors = True

    # back up databases
    logger.info("Backing up databases")
    for container in containers.containers_for_backup():
        if container.database_backup_enabled:
            try:
                instance = container.instance
                logger.info(
                    "Backing up %s in service %s",
                    instance.container_type,
                    instance.service_name,
                )
                result = instance.backup()
                logger.debug("Exit code: %s", result)
                if result != 0:
                    logger.error("Backup command exited with non-zero code: %s", result)
                    errors = True
            except Exception as ex:
                logger.exception(ex)
                errors = True

    # restart stopped containers after backup
    if len(containers.stop_during_backup_containers) > 0:
        utils.start_containers(containers.stop_during_backup_containers)

    if errors:
        logger.error("Exit code: %s", errors)
        exit(1)

    # Only run maintenance tasks if maintenance is not scheduled
    if not config.maintenance_schedule:
        maintenance(config, containers)

    logger.info("Backup completed")


def maintenance(config, containers):
    """Run maintenance tasks"""
    logger.info("Running maintenance tasks")
    result = cleanup(config, containers)
    if result != 0:
        logger.error("Cleanup exit code: %s", result)
        exit(1)

    logger.info("Checking the repository for errors")
    check_with_cache = utils.is_true(config.check_with_cache)
    result = restic.check(config.repository, with_cache=check_with_cache)
    if result != 0:
        logger.error("Check exit code: %s", result)
        exit(1)


def cleanup(config, containers):
    """Run forget / prune to minimize storage space"""
    logger.info("Forget outdated snapshots")
    forget_result = restic.forget(
        config.repository,
        config.keep_daily,
        config.keep_weekly,
        config.keep_monthly,
        config.keep_yearly,
    )
    logger.info("Prune stale data freeing storage space")
    prune_result = restic.prune(config.repository)
    return forget_result and prune_result


def snapshots(config, containers):
    """Display restic snapshots"""
    stdout, stderr = restic.snapshots(config.repository, last=True)
    for line in stdout.decode().split("\n"):
        print(line)


def alert(config, containers):
    """Test alerts"""
    logger.info("Testing alerts")
    alerts.send(
        subject="{}: Test Alert".format(containers.project_name),
        body="Test message",
    )


def crontab(config):
    """Generate the crontab"""
    print(cron.generate_crontab(config))


def dump_env():
    """Dump all environment variables to a file that can be sourced from cron"""
    print("# This file was generated by stack-back")
    for key, value in os.environ.items():
        print("export {}='{}'".format(key, value))


def parse_args():
    parser = argparse.ArgumentParser(prog="restic_compose_backup")
    parser.add_argument(
        "action",
        choices=[
            "status",
            "snapshots",
            "backup",
            "start-backup-process",
            "maintenance",
            "alert",
            "cleanup",
            "version",
            "crontab",
            "dump-env",
            "test",
        ],
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=list(log.LOG_LEVELS.keys()),
        help="Log level",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
