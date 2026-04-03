from typing import Optional

import requests

from workspace_config import WorkspaceConfig, load_workspace_config


class SlackWorkspaceClient:
    def __init__(self, config: Optional[WorkspaceConfig] = None):
        self.config = config or load_workspace_config()
        self.headers = {
            "Authorization": f"Bearer {self.config.slack_token}",
            "Content-Type": "application/json",
        }

    def send_message(self, channel: str, text: str) -> bool:
        if not self.config.slack_enabled or not channel or channel.startswith("replace_with_"):
            return False
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers=self.headers,
            json={"channel": channel, "text": text},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        return bool(payload.get("ok"))
