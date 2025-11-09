import logging

from restic_compose_backup.alerts.smtp import SMTPAlert
from restic_compose_backup.alerts.discord import DiscordWebhookAlert

logger = logging.getLogger(__name__)

ALERT_INFO = ("INFO",)
ALERT_ERROR = "ERROR"
ALERT_TYPES = [ALERT_INFO, ALERT_ERROR]
BACKENDS = [SMTPAlert, DiscordWebhookAlert]


def send(subject: str = None, body: str = None, alert_type: str = "INFO"):
    """Send alert to all configured backends"""
    alert_classes = configured_alert_types()
    for instance in alert_classes:
        logger.info("Configured: %s", instance.name)
        try:
            instance.send(
                subject=f"[{alert_type}] {subject}",
                body=body,
            )
        except Exception as ex:
            logger.error(
                "Exception raised when sending alert [%s]: %s", instance.name, ex
            )
            logger.exception(ex)

    if len(alert_classes) == 0:
        logger.info("No alerts configured")


def configured_alert_types():
    """Returns a list of configured alert class instances"""
    logger.debug("Getting alert backends")
    entires = []

    for cls in BACKENDS:
        instance = cls.create_from_env()
        logger.debug(
            "Alert backend '%s' configured: %s", cls.name, instance is not None
        )
        if instance:
            entires.append(instance)

    return entires
