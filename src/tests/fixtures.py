"""Generate test fixtures"""

from datetime import datetime
import hashlib
import string
import random


def generate_sha256():
    """Generate a unique sha256"""
    h = hashlib.sha256()
    h.update(str(datetime.now().timestamp()).encode())
    return h.hexdigest()


def containers(project="default", containers=[]):
    """
    Args:
        project (str): Name of the compose project
        containers (dict):
            {
                'containers: [
                    'id': 'something'
                    'service': 'service_name',
                    'image': 'image:tag',
                    'mounts: [{
                        'Source': '/home/user/stuff',
                        'Destination': '/srv/stuff',
                        'Type': 'bind' / 'volume'
                    }],
                ]
            }
    """

    def wrapper(*args, **kwargs):
        return [
            {
                "Id": container.get("id", generate_sha256()),
                "Name": container.get("service")
                + "_"
                + "".join(random.choice(string.ascii_lowercase) for i in range(16)),
                "Config": {
                    "Image": container.get("image", "image:latest"),
                    "Labels": {
                        "com.docker.compose.oneoff": "False",
                        "com.docker.compose.project": project,
                        "com.docker.compose.service": container["service"],
                        **container.get("labels", {}),
                    },
                },
                "Mounts": container.get("mounts", []),
                "State": {
                    "Status": "running",
                    "Running": True,
                },
            }
            for container in containers
        ]

    return wrapper
