import logging
import os
from typing import Iterable, Optional, Sequence

from local_blackbox import LocalBlackBox


logger = logging.getLogger(__name__)


def _is_enabled(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def run_worker_smoke_check(
    worker_name: str,
    *,
    required_tables: Sequence[str] = (),
    required_env: Iterable[str] = (),
    strict: Optional[bool] = None,
) -> bool:
    strict_mode = _is_enabled(os.getenv("WORKER_SMOKE_CHECK_STRICT")) if strict is None else strict
    enabled = os.getenv("WORKER_SMOKE_CHECK", "true")
    if not _is_enabled(enabled):
        return True

    logger.info("🔎 Running startup smoke check for %s", worker_name)
    ok = True

    missing_env = [name for name in required_env if not str(os.getenv(name) or "").strip()]
    if missing_env:
        ok = False
        logger.warning("⚠️ %s missing env vars: %s", worker_name, ", ".join(sorted(missing_env)))

    try:
        db = LocalBlackBox()
        ph = db.qmark
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {ph}", (1,))
            cursor.fetchone()
            for table_name in required_tables:
                cursor.execute(
                    f"""
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_name = {ph}
                    """
                    if db.is_postgres
                    else f"SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = {ph}",
                    (table_name,),
                )
                if not cursor.fetchone():
                    ok = False
                    logger.warning("⚠️ %s expected table missing: %s", worker_name, table_name)
    except Exception as exc:
        ok = False
        logger.warning("⚠️ %s startup smoke check hit an infrastructure issue: %s", worker_name, exc)

    if ok:
        logger.info("✅ %s startup smoke check passed", worker_name)
        return True

    if strict_mode:
        raise RuntimeError(f"{worker_name} startup smoke check failed")
    logger.warning("⚠️ %s startup smoke check finished with warnings; continuing in non-strict mode", worker_name)
    return False
