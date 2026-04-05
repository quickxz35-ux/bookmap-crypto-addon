from typing import Any, Dict, List, Optional

import requests

from workspace_config import WorkspaceConfig, load_workspace_config


NOTION_VERSION = "2022-06-28"


def title(value: str) -> Dict[str, Any]:
    return {"title": [{"text": {"content": value}}]}


def rich_text(value: str) -> Dict[str, Any]:
    return {"rich_text": [{"text": {"content": value}}]}


def select(value: str) -> Dict[str, Any]:
    return {"select": {"name": value}}


def number(value: float) -> Dict[str, Any]:
    return {"number": value}


def date_value(value: str) -> Dict[str, Any]:
    return {"date": {"start": value}}


def multi_select(values: List[str]) -> Dict[str, Any]:
    return {"multi_select": [{"name": item} for item in values]}


class NotionWorkspaceClient:
    def __init__(self, config: Optional[WorkspaceConfig] = None):
        self.config = config or load_workspace_config()
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.config.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }

    def is_ready(self, database_id: str) -> bool:
        return self.config.notion_enabled and bool(database_id) and not database_id.startswith("replace_with_")

    def query_database(self, database_id: str, payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not self.is_ready(database_id):
            return []
        response = requests.post(
            f"{self.base_url}/databases/{database_id}/query",
            headers=self.headers,
            json=payload or {},
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def find_page_by_title(self, database_id: str, property_name: str, value: str) -> Optional[Dict[str, Any]]:
        if not self.is_ready(database_id) or not value:
            return None
        results = self.query_database(
            database_id,
            {
                "filter": {
                    "property": property_name,
                    "title": {"equals": value},
                },
                "page_size": 1,
            },
        )
        return results[0] if results else None

    def create_page(self, database_id: str, properties: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.is_ready(database_id):
            return None
        payload = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }
        response = requests.post(
            f"{self.base_url}/pages",
            headers=self.headers,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def update_page(self, page_id: str, properties: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.config.notion_enabled:
            return None
        response = requests.patch(
            f"{self.base_url}/pages/{page_id}",
            headers=self.headers,
            json={"properties": properties},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
