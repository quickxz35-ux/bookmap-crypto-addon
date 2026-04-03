import argparse
import json

from analyst_long_term import LongTermCoinAnalyst
from analyst_scalping import ScalpingAnalyst
from correlation_analyst import CorrelationAnalyst
from decision_router import DecisionRouter
from scalp_tracker import ScalpTracker
from validation_scout import ValidationScout


def run_scalp(asset: str, write_outputs: bool) -> dict:
    setup = ScalpingAnalyst().analyze(asset)
    validation = ValidationScout().validate(asset, source_board="scalp_board")
    tracker = ScalpTracker().refresh(setup)
    correlation = CorrelationAnalyst().correlate(setup, validation)
    result = {
        "setup": setup,
        "validation": validation,
        "tracker": tracker,
        "correlation": correlation,
    }
    if write_outputs:
        result["route"] = DecisionRouter().route_scalp(setup, tracker, correlation)
    return result


def run_long_term(asset: str, write_outputs: bool) -> dict:
    coin_view = LongTermCoinAnalyst().analyze(asset)
    validation = ValidationScout().validate(asset, source_board="asset_library")
    correlation = CorrelationAnalyst().correlate(coin_view, validation)
    result = {
        "coin_view": coin_view,
        "validation": validation,
        "correlation": correlation,
    }
    if write_outputs:
        result["route"] = DecisionRouter().route_long_term(coin_view, validation, correlation)
    return result


def run_validation_queue(limit: int | None = None) -> dict:
    validations = ValidationScout().validate_selected_assets(limit=limit)
    return {
        "count": len(validations),
        "validations": validations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the crypto workspace agent layer.")
    parser.add_argument("mode", choices=["scalp", "long_term", "validate_queue"])
    parser.add_argument("asset", nargs="?", help="Coin / symbol to evaluate")
    parser.add_argument("--write", action="store_true", help="Persist outputs and attempt workspace routing")
    parser.add_argument("--limit", type=int, default=None, help="Optional batch limit for queue-driven validation")
    args = parser.parse_args()

    if args.mode == "scalp":
        if not args.asset:
            parser.error("asset is required for scalp mode")
        result = run_scalp(args.asset, args.write)
    elif args.mode == "long_term":
        if not args.asset:
            parser.error("asset is required for long_term mode")
        result = run_long_term(args.asset, args.write)
    else:
        result = run_validation_queue(limit=args.limit)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
