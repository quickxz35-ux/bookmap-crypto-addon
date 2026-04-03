import json
from pathlib import Path
from typing import Dict, List

from local_blackbox import LocalBlackBox
from workspace_config import WorkspaceConfig, load_workspace_config


class SelectedAssetsSource:
    def __init__(self, config: WorkspaceConfig | None = None):
        self.config = config or load_workspace_config()
        self.db = LocalBlackBox(self.config.local_blackbox_path)
        self.outbox_dir = Path("runs") / "workspace_router"

    def load(self, limit: int | None = None) -> List[Dict]:
        selected_limit = limit or self.config.validation_batch_size
        source = (self.config.selected_assets_source or "blackbox").lower()
        if source == "blackbox":
            return self._from_blackbox(selected_limit)
        if source == "outbox":
            return self._from_outbox(selected_limit)
        if source == "notion":
            queued = self._from_blackbox(selected_limit)
            return queued if queued else self._from_outbox(selected_limit)
        return self._from_blackbox(selected_limit)

    def _from_blackbox(self, limit: int) -> List[Dict]:
        rows = self.db.fetch_selected_assets(limit=limit)
        for row in rows:
            payload = row.get("payload_json")
            row["payload"] = json.loads(payload) if payload else {}
        return rows

    def _from_outbox(self, limit: int) -> List[Dict]:
        if not self.outbox_dir.exists():
            return []

        selected: List[Dict] = []
        seen: set[str] = set()
        for path in sorted(self.outbox_dir.glob("*.json"), reverse=True):
            payload = json.loads(path.read_text(encoding="utf-8"))
            asset = payload.get("asset")
            if not asset or asset in seen:
                continue
            kind = "scalp" if "_scalp_" in path.name or "setup" in payload else "long_term"
            source_board = "scalp_board" if kind == "scalp" else "asset_library"
            selected.append(
                {
                    "queue_key": f"{asset.lower()}::{source_board}::{kind}",
                    "asset": asset,
                    "source_board": source_board,
                    "opportunity_type": kind,
                    "priority": "normal",
                    "status": "pending",
                    "payload": payload,
                }
            )
            seen.add(asset)
            if len(selected) >= limit:
                break
        return selected
