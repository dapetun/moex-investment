"""Headless CLI для интеграции с Grok Bot (без Streamlit).

Запуск: ``python -m moex_portfolio <command>``.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence

from .compare import compare_weights
from .config import DATA_DIR
from .data_quality import validate_price_panel
from .data_sources import DataSourceError, FixtureDataSource, get_data_source
from .events import ingest_events
from .locks import PipelineLockError, pipeline_lock
from .pipeline import current_weights_or_empty, run_optimize
from .portfolio_state import HoldingsValidationError, load_holdings
from .reporting import write_report
from .run_journal import finish_run, load_run, start_run
from .settings import get_data_source_name, iss_enabled, runtime_cache_path

LAST_TARGET_PATH = DATA_DIR / "outbox" / "last_target.json"

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _print_json(payload: Any, *, stream=None) -> None:
    stream = stream or sys.stdout
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str), file=stream)


def cmd_show_portfolio(_args: argparse.Namespace) -> int:
    """Показать текущие holdings (пустой портфель допустим)."""

    def _run() -> tuple[int, dict[str, Any]]:
        holdings = load_holdings()
        return 0, holdings

    # отдельный путь: успех печатаем один раз через _with_lock_journal — исправим двойной print
    run = start_run("show-portfolio")
    try:
        with pipeline_lock("pipeline"):
            holdings = load_holdings()
        _print_json(holdings)
        finish_run(
            run["run_id"],
            status="ok",
            result={"n_positions": len(holdings["positions"])},
        )
        return 0
    except PipelineLockError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 1


def cmd_validate_data(args: argparse.Namespace) -> int:
    """Проверить свежесть/полноту данных активного источника."""
    run = start_run(
        "validate-data",
        params={
            "source": get_data_source_name(),
            "max_staleness_days": args.max_staleness_days,
            "iss_enabled": iss_enabled(),
        },
    )
    try:
        with pipeline_lock("pipeline"):
            src = get_data_source()
            df = src.load_prices()
            report = validate_price_panel(
                df,
                max_staleness_days=args.max_staleness_days,
            )
            report["source"] = src.name
            report["iss_enabled"] = iss_enabled()
        code = 0 if report["ok"] else 2
        finish_run(
            run["run_id"],
            status="ok" if code == 0 else "error",
            result=report,
            error=None if code == 0 else "; ".join(report.get("issues") or []),
        )
        _print_json(report)
        return code
    except PipelineLockError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 3
    except DataSourceError as e:
        finish_run(run["run_id"], status="blocked", error=str(e))
        _print_json({"error": str(e), "source": get_data_source_name()}, stream=sys.stderr)
        return 4
    except Exception as e:  # noqa: BLE001
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 1


def cmd_update_data(_args: argparse.Namespace) -> int:
    """Обновить рабочий кэш из активного источника (fixture → runtime cache).

    ISS не вызывается, пока гейт закрыт.
    """
    run = start_run(
        "update-data",
        params={"source": get_data_source_name(), "iss_enabled": iss_enabled()},
    )
    try:
        with pipeline_lock("pipeline"):
            src = get_data_source()
            if src.name == "iss":
                raise DataSourceError(
                    "ISS update blocked until written legal clearance; "
                    "MOEX_ISS_ENABLED gate still prevents live fetch wiring"
                )
            df = src.load_prices()
            cache = runtime_cache_path()
            cache.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(src, FixtureDataSource) and src.path.exists():
                shutil.copy2(src.path, cache)
            else:
                df.to_csv(cache, sep=";")
            payload = {
                "action": "updated_runtime_cache",
                "source": src.name,
                "cache": str(cache),
                "rows": int(len(df)),
                "columns": int(len(df.columns)),
                "iss_enabled": iss_enabled(),
            }
        finish_run(run["run_id"], status="ok", result=payload)
        _print_json(payload)
        return 0
    except PipelineLockError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 3
    except DataSourceError as e:
        finish_run(run["run_id"], status="blocked", error=str(e))
        _print_json({"error": str(e), "source": get_data_source_name()}, stream=sys.stderr)
        return 4
    except Exception as e:  # noqa: BLE001
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 1


def cmd_optimize(args: argparse.Namespace) -> int:
    """Явный запуск оптимизации (требует --allow-optimize)."""
    if not args.allow_optimize:
        _print_json(
            {
                "error": "refusing to optimize without --allow-optimize",
                "hint": "pass --allow-optimize after reviewing data source policy",
            },
            stream=sys.stderr,
        )
        return 2

    run = start_run(
        "optimize",
        params={
            "mode": args.mode,
            "max_weight": args.max_weight,
            "source": get_data_source_name(),
            "iss_enabled": iss_enabled(),
        },
    )
    try:
        with pipeline_lock("pipeline"):
            src = get_data_source()
            prices = src.load_prices()
            holdings = load_holdings()
            result = run_optimize(
                prices,
                max_weight=args.max_weight,
                mode=args.mode,
                holdings=holdings,
                min_turnover=0.0,
            )
            LAST_TARGET_PATH.parent.mkdir(parents=True, exist_ok=True)
            LAST_TARGET_PATH.write_text(
                json.dumps(
                    {
                        "weights": result["weights"],
                        "tickers": result["tickers"],
                        "success": result["success"],
                        "source": src.name,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            result["target_path"] = str(LAST_TARGET_PATH)
            result["source"] = src.name
            paths = write_report(
                run_id=run["run_id"],
                title="Optimization report",
                payload=result,
            )
            result["report_json"] = str(paths["json"])
            result["report_md"] = str(paths["md"])

        code = 0 if result.get("success") else 2
        finish_run(
            run["run_id"],
            status="ok" if code == 0 else "error",
            result=result,
            error=None if code == 0 else result.get("message"),
        )
        _print_json(result)
        return code
    except PipelineLockError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 3
    except DataSourceError as e:
        finish_run(run["run_id"], status="blocked", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 4
    except HoldingsValidationError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 1


def cmd_ingest_events(_args: argparse.Namespace) -> int:
    """Принять JSON-события бота №1 из inbox."""
    run = start_run("ingest-events")
    try:
        with pipeline_lock("pipeline"):
            report = ingest_events()
        finish_run(run["run_id"], status="ok", result=report)
        _print_json(report)
        return 0 if report["rejected"] == 0 or report["accepted"] > 0 else 2
    except PipelineLockError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 1


def cmd_report(args: argparse.Namespace) -> int:
    """Сформировать/показать отчёт по run_id (из journal + target)."""
    run = start_run("report", params={"from_run": args.run_id})
    try:
        with pipeline_lock("pipeline"):
            if not args.run_id:
                raise ValueError("--run-id is required")
            record = load_run(args.run_id)
            payload = record.get("result") or {}
            payload.setdefault("success", record.get("status") == "ok")
            payload.setdefault("source", get_data_source_name())
            paths = write_report(
                run_id=args.run_id,
                title=f"Report for {args.run_id}",
                payload=payload,
            )
            out = {
                "run_id": args.run_id,
                "report_json": str(paths["json"]),
                "report_md": str(paths["md"]),
                "journal_status": record.get("status"),
            }
        finish_run(run["run_id"], status="ok", result=out)
        _print_json(out)
        return 0
    except PipelineLockError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 1


def cmd_compare(args: argparse.Namespace) -> int:
    """Сравнить holdings с целевыми весами."""
    run = start_run("compare", params={"min_drift": args.min_drift})
    try:
        with pipeline_lock("pipeline"):
            holdings = load_holdings()
            current = current_weights_or_empty(holdings)
            target_path = Path(args.target) if args.target else LAST_TARGET_PATH
            if not target_path.exists():
                raise FileNotFoundError(
                    f"target weights not found: {target_path}; run optimize first"
                )
            target_data = json.loads(target_path.read_text(encoding="utf-8"))
            target = target_data.get("weights") or target_data
            report = compare_weights(current, target, min_drift=args.min_drift)
            report["target_path"] = str(target_path)
            report["holdings_empty"] = len(current) == 0

        finish_run(run["run_id"], status="ok", result=report)
        _print_json(report)
        return 0
    except PipelineLockError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 3
    except HoldingsValidationError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moex_portfolio",
        description="MOEX portfolio headless CLI (fixtures-first; ISS gated).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="DEBUG logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show-portfolio", help="Show holdings JSON (empty OK)")
    p_show.set_defaults(func=cmd_show_portfolio)

    p_val = sub.add_parser("validate-data", help="Validate active price source freshness")
    p_val.add_argument(
        "--max-staleness-days",
        type=int,
        default=5,
        help="Max age of last bar vs today (calendar days)",
    )
    p_val.set_defaults(func=cmd_validate_data)

    p_upd = sub.add_parser("update-data", help="Refresh runtime cache from active source")
    p_upd.set_defaults(func=cmd_update_data)

    p_opt = sub.add_parser(
        "optimize",
        help="Run Max Sharpe on active source (explicit; fixtures by default)",
    )
    p_opt.add_argument(
        "--mode",
        choices=["universe", "holdings"],
        default="universe",
        help="universe=all fixture tickers; holdings=non-empty holdings only",
    )
    p_opt.add_argument("--max-weight", type=float, default=0.5)
    p_opt.add_argument(
        "--allow-optimize",
        action="store_true",
        help="Required safety flag to run optimizer",
    )
    p_opt.set_defaults(func=cmd_optimize)

    p_cmp = sub.add_parser("compare", help="Compare holdings weights vs last target")
    p_cmp.add_argument("--min-drift", type=float, default=0.05)
    p_cmp.add_argument(
        "--target",
        type=str,
        default="",
        help="Path to target weights JSON (default: last outbox target)",
    )
    p_cmp.set_defaults(func=cmd_compare)

    p_ing = sub.add_parser("ingest-events", help="Validate bot#1 JSON events from inbox")
    p_ing.set_defaults(func=cmd_ingest_events)

    p_rep = sub.add_parser("report", help="Write MD/JSON report for a journal run_id")
    p_rep.add_argument("--run-id", required=True, help="Existing run_id from outbox/runs")
    p_rep.set_defaults(func=cmd_report)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входа CLI. Возвращает код выхода."""
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        return int(code)

    _setup_logging(getattr(args, "verbose", False))
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
