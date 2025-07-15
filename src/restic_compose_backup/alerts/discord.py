import os
import logging

import requests
from restic_compose_backup.alerts.base import BaseAlert

logger = logging.getLogger(__name__)


class DiscordWebhookAlert(BaseAlert):
    name = "discord_webhook"
    success_codes = [200]

    def __init__(self, webhook_url):
        self.url = webhook_url

    @classmethod
    def create_from_env(cls):
        instance = cls(os.environ.get("DISCORD_WEBHOOK"))

        if instance.properly_configured:
            return instance

        return None

    @property
    def properly_configured(self) -> bool:
        return isinstance(self.url, str) and self.url.startswith("https://")

    def send(self, subject: str = None, body: str = None, alert_type: str = None):
        """Send basic webhook request. Max embed size is 6000"""
        logger.info("Triggering discord webhook")
        # NOTE: The title size is 2048
        #       The max description size is 2048
        #       Total embed size limit is 6000 characters (per embed)
        data = {
            "embeds": [
                {
                    "title": subject[-256:],
                    "description": body[-2048:] if body else "",
                },
            ]
        }
        response = requests.post(self.url, params={"wait": True}, json=data)
        if response.status_code not in self.success_codes:
            logger.error(
                "Discord webhook failed: %s: %s", response.status_code, response.content
            )
        else:
            logger.info("Discord webhook successful")
