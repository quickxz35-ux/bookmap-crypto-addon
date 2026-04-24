import os
import re
import sys


def pick_script(service_name: str) -> str:
    canonical_name = re.sub(r"[\s\-]+", "_", (service_name or "").strip().lower())

    if canonical_name in {"hyperscreener", "wallet_analyst"}:
        return "analyst_wallet.py"
    if canonical_name in {"wallet_scout", "mobula", "dmobula"}:
        return "scout_wallet.py"
    if canonical_name in {"sentiment_scout", "scout_sentiment"}:
        return "scout_sentiment.py"
    if canonical_name in {"derivatives_scout", "scout_derivatives"}:
        return "scout_derivatives.py"
    if canonical_name in {"validation_scout", "scout_whale"}:
        return "scout_whale.py"
    if canonical_name in {"decision_router", "onchain_decision_router"}:
        return "outbox_processor.py"
    if canonical_name in {"council_analyst", "crypto_council"}:
        return "council_analyst.py"
    if canonical_name in {"hypertracker_scout", "hypertracker", "hypertracker_analyst"}:
        return "hypertracker_scout.py"
    if canonical_name == "analyst_narrative":
        return "analyst_narrative.py"
    if canonical_name == "analyst_technical":
        return "analyst_technical.py"
    if canonical_name == "analyst_long_term":
        return "analyst_long_term.py"
    if canonical_name == "analyst_scalping":
        return "analyst_scalping.py"
    if canonical_name in {"postman", "outbox_processor"}:
        return "outbox_processor.py"

    raise SystemExit(f"Unknown Railway service '{service_name}'")


def main() -> None:
    service_name = os.getenv("WORKER_ROLE") or os.getenv("RAILWAY_SERVICE_NAME") or ""
    script = pick_script(service_name)
    python_bin = sys.executable or "python3"
    os.execv(python_bin, [python_bin, script])


if __name__ == "__main__":
    main()
