class BaseAlert:
    name = None

    def create_from_env(self):
        return None

    @property
    def properly_configured(self) -> bool:
        return False

    def send(self, subject: str = None, body: str = None, alert_type: str = None):
        pass
