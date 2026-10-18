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

from . import config as _config
from .analyst_bundle import build_analyst_bundle, write_analyst_bundle
from .compare import compare_weights
from .config import DATA_DIR, MIN_TURNOVER
from .data_quality import validate_for_optimize
from .data_sources import (
    DataSourceError,
    FixtureDataSource,
    get_data_source,
    redact_local_path,
    validate_user_price_csv,
)
from .events import EventIngestGateError, ingest_events
from .io_util import atomic_write_json
from .locks import PipelineLockError, pipeline_lock
from .numeric import (
    NumericValidationError,
    require_finite_number,
    require_nonnegative_finite,
)
from .pipeline import current_weights_or_empty, run_optimize
from .portfolio_adapter import PortfolioAdapterError, adapt_analyst_csv
from .portfolio_ready import check_portfolio_ready
from .portfolio_state import HoldingsValidationError, load_holdings, save_holdings
from .reporting import write_report
from .run_journal import finish_run, load_run, start_run
from .settings import get_data_source_name, iss_enabled, runtime_cache_path

LAST_TARGET_PATH = DATA_DIR / "outbox" / "last_target.json"


class TargetValidationError(ValueError):
    """Целевой портфель непригоден для compare (нет success=true)."""


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
            report = validate_for_optimize(
                df,
                source_name=src.name,
                max_staleness_days=args.max_staleness_days,
            )
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
            if src.name == "market":
                raise DataSourceError(
                    "update-data refuses market self-refresh: runtime cache is not "
                    "an approved upstream quote source "
                    "(code=MARKET_UPDATE_NO_UPSTREAM). "
                    "Use MOEX_DATA_SOURCE=fixture until a cleared feed exists."
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
    """Явный запуск оптимизации (требует --allow-optimize).

    last_target.json перезаписывается только при success=true после QC.
    """
    if not args.allow_optimize:
        _print_json(
            {
                "error": "refusing to optimize without --allow-optimize",
                "hint": "pass --allow-optimize after reviewing data source policy",
            },
            stream=sys.stderr,
        )
        return 2

    try:
        max_weight = require_finite_number(args.max_weight, "max_weight")
        if not (0.0 < max_weight <= 1.0):
            raise NumericValidationError(
                f"max_weight must be in (0, 1], got {max_weight}"
            )
    except NumericValidationError as e:
        _print_json({"error": str(e), "code": "INVALID_MAX_WEIGHT"}, stream=sys.stderr)
        return 2

    run = start_run(
        "optimize",
        params={
            "mode": args.mode,
            "max_weight": max_weight,
            "source": get_data_source_name(),
            "iss_enabled": iss_enabled(),
        },
    )
    try:
        with pipeline_lock("pipeline"):
            src = get_data_source()
            prices = src.load_prices()
            qc = validate_for_optimize(
                prices,
                source_name=src.name,
                max_staleness_days=args.max_staleness_days,
            )
            if not qc["ok"]:
                payload = {
                    "success": False,
                    "error": "data quality check failed before optimize",
                    "code": "DATA_QUALITY_FAILED",
                    "validation": qc,
                    "source": src.name,
                    "is_live_market": qc.get("is_live_market"),
                    "target_updated": False,
                }
                paths = write_report(
                    run_id=run["run_id"],
                    title="Optimization blocked: data quality",
                    payload=payload,
                )
                payload["report_json"] = str(paths["json"])
                payload["report_md"] = str(paths["md"])
                finish_run(
                    run["run_id"],
                    status="error",
                    result=payload,
                    error="; ".join(qc.get("issues") or []) or "data quality failed",
                )
                _print_json(payload, stream=sys.stderr)
                return 2

            # fixture/user_csv: панель уже отобрана пользователем/тестом —
            # не режем по биржевому MIN_TURNOVER. market/iss — как Streamlit.
            min_turnover = (
                0.0 if src.name in {"fixture", "user_csv"} else float(MIN_TURNOVER)
            )

            holdings = load_holdings()
            result = run_optimize(
                prices,
                max_weight=max_weight,
                mode=args.mode,
                holdings=holdings,
                min_turnover=min_turnover,
            )
            result["source"] = src.name
            result["is_live_market"] = bool(qc.get("is_live_market"))
            result["validation"] = qc
            result["target_updated"] = False

            if result.get("success") is True:
                atomic_write_json(
                    LAST_TARGET_PATH,
                    {
                        "weights": result["weights"],
                        "tickers": result["tickers"],
                        "success": True,
                        "source": src.name,
                        "is_live_market": result["is_live_market"],
                    },
                )
                result["target_path"] = str(LAST_TARGET_PATH)
                result["target_updated"] = True
            else:
                result["error"] = result.get("message") or "optimizer reported success=false"
                result["code"] = "OPTIMIZER_FAILED"

            paths = write_report(
                run_id=run["run_id"],
                title="Optimization report",
                payload=result,
            )
            result["report_json"] = str(paths["json"])
            result["report_md"] = str(paths["md"])

        code = 0 if result.get("success") is True else 2
        finish_run(
            run["run_id"],
            status="ok" if code == 0 else "error",
            result=result,
            error=None if code == 0 else result.get("message") or result.get("error"),
        )
        _print_json(result, stream=sys.stdout if code == 0 else sys.stderr)
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
        _print_json({"error": str(e), "code": "HOLDINGS_INVALID"}, stream=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 1


def cmd_check_portfolio_ready(args: argparse.Namespace) -> int:
    """Проверка готовности портфеля без optimize."""
    run = start_run(
        "check-portfolio-ready",
        params={"csv": getattr(args, "csv", "") or None},
    )
    try:
        panel = None
        if getattr(args, "panel_tickers", ""):
            panel = {
                t.strip().upper()
                for t in args.panel_tickers.split(",")
                if t.strip()
            }
        mapping = None
        if getattr(args, "isin_map", ""):
            mapping = json.loads(Path(args.isin_map).read_text(encoding="utf-8"))
        csv_path = Path(args.csv) if getattr(args, "csv", "") else None
        report = check_portfolio_ready(
            csv_path=csv_path,
            panel_tickers=panel,
            isin_to_ticker=mapping,
        )
        code = 0 if report.get("ok") else 2
        finish_run(
            run["run_id"],
            status="ok" if code == 0 else "error",
            result={"ok": report.get("ok"), "blockers": report.get("blockers")},
            error=None if code == 0 else "; ".join(report.get("blockers") or []),
        )
        _print_json(report)
        return code
    except Exception as e:  # noqa: BLE001
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 1


def cmd_import_user_prices(args: argparse.Namespace) -> int:
    """Импорт пользовательского CSV в runtime-кэш (без сети/ISS)."""
    req = [
        t.strip().upper()
        for t in (getattr(args, "require_tickers", "") or "").split(",")
        if t.strip()
    ]
    run = start_run(
        "import-user-prices",
        params={
            "csv": Path(args.csv).name,
            "skip_staleness": bool(args.skip_staleness),
            "require_tickers": req or None,
        },
    )
    try:
        with pipeline_lock("pipeline"):
            src = Path(args.csv)
            meta = validate_user_price_csv(
                src,
                require_tickers=req or None,
                redact_paths=True,
            )
            cache = runtime_cache_path()
            cache.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, cache)
            sidecar = cache.with_suffix(cache.suffix + ".meta.json")
            payload = {
                "action": "imported_user_prices",
                "source": "user_csv",
                "cache": redact_local_path(cache),
                "meta_path": redact_local_path(sidecar),
                "skip_staleness": bool(args.skip_staleness),
                "iss_enabled": iss_enabled(),
                **meta,
                "hint": (
                    "Set MOEX_DATA_SOURCE=user_csv and MOEX_USER_PRICES_PATH="
                    "<runtime_cache_path>"
                    + (
                        " MOEX_USER_CSV_SKIP_STALENESS=true"
                        if args.skip_staleness
                        else ""
                    )
                ),
            }
            # sidecar хранит и машинный абсолютный путь (локально), и redacted-копию
            sidecar_payload = {
                **payload,
                "cache_abs": str(cache.resolve()),
                "source_basename": src.name,
            }
            atomic_write_json(sidecar, sidecar_payload)
        finish_run(run["run_id"], status="ok", result=payload)
        _print_json(payload)
        return 0
    except PipelineLockError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 3
    except DataSourceError as e:
        finish_run(run["run_id"], status="blocked", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 4
    except Exception as e:  # noqa: BLE001
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 1


def cmd_adapt_portfolio(args: argparse.Namespace) -> int:
    """Read-only адаптер CSV аналитика → канон holdings (не трогает /workspace/invest)."""
    run = start_run(
        "adapt-portfolio",
        params={"csv": args.csv, "write_holdings": bool(args.write_holdings)},
    )
    try:
        with pipeline_lock("pipeline"):
            mapping: dict[str, str] | None = None
            if args.isin_map:
                mapping = json.loads(Path(args.isin_map).read_text(encoding="utf-8"))
            panel = None
            if args.panel_tickers:
                panel = {t.strip().upper() for t in args.panel_tickers.split(",") if t.strip()}
            holdings = adapt_analyst_csv(
                args.csv,
                isin_to_ticker=mapping,
                as_of=args.as_of or None,
                panel_tickers=panel,
            )
            written = None
            if args.write_holdings:
                # только CLI data/portfolio/holdings.json — не пути аналитика
                to_save = {
                    "as_of": holdings.get("as_of"),
                    "cash": holdings.get("cash", 0.0),
                    "positions": holdings.get("positions", []),
                }
                written = str(save_holdings(to_save))
                holdings["written_path"] = written
        finish_run(
            run["run_id"],
            status="ok",
            result={
                "n_positions": len(holdings.get("positions", [])),
                "file_status": holdings.get("file_status"),
                "written_path": written,
            },
        )
        _print_json(holdings)
        return 0
    except PipelineLockError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 3
    except (PortfolioAdapterError, HoldingsValidationError, OSError, json.JSONDecodeError) as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 1


def cmd_ingest_events(args: argparse.Namespace) -> int:
    """Принять JSON-события радара/inbox.

    Частичный отказ (rejected>0) → код 2, даже если часть событий принята.
    ``--source`` копирует выпуск радара в inbox, оригинал не удаляет.
    Тестовые выпуски требуют ``--test-events`` (отдельные ``*_test`` каталоги).
    """
    source = (getattr(args, "source", None) or "").strip() or None
    test_mode = bool(getattr(args, "test_events", False))
    run = start_run(
        "ingest-events",
        params={"source": source, "test_events": test_mode},
    )
    try:
        with pipeline_lock("pipeline"):
            report = ingest_events(
                source_path=source,
                keep_source=True,
                test_mode=test_mode,
                data_root=_config.DATA_DIR,
            )
        code = 0 if not report.get("partial") else 2
        finish_run(
            run["run_id"],
            status="ok" if code == 0 else "error",
            result=report,
            error=None
            if code == 0
            else f"partial ingest: accepted={report.get('accepted')} "
            f"rejected={report.get('rejected')}",
        )
        _print_json(report, stream=sys.stdout if code == 0 else sys.stderr)
        return code
    except PipelineLockError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 3
    except EventIngestGateError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json(
            {"error": str(e), "code": e.code, "ok": False},
            stream=sys.stderr,
        )
        return 2
    except FileNotFoundError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e), "code": "SOURCE_NOT_FOUND"}, stream=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 1


def cmd_build_analyst_bundle(args: argparse.Namespace) -> int:
    """Собрать пакет артефактов CLI для одноразового задания Аналитику."""
    run = start_run(
        "build-analyst-bundle",
        params={
            "target": getattr(args, "target", "") or None,
            "compare_json": getattr(args, "compare_json", "") or None,
            "validation_json": getattr(args, "validation_json", "") or None,
            "ingest_json": getattr(args, "ingest_json", "") or None,
            "test_events": bool(getattr(args, "test_events", False)),
        },
    )
    try:
        with pipeline_lock("pipeline"):
            def _load_opt(path_str: str) -> dict[str, Any] | None:
                if not path_str:
                    return None
                p = Path(path_str)
                if not p.exists():
                    raise FileNotFoundError(f"artifact not found: {p}")
                return json.loads(p.read_text(encoding="utf-8"))

            compare_payload = _load_opt(getattr(args, "compare_json", "") or "")
            validation_payload = _load_opt(getattr(args, "validation_json", "") or "")
            ingest_payload = _load_opt(getattr(args, "ingest_json", "") or "")
            run_ids = [
                x.strip()
                for x in (getattr(args, "run_ids", "") or "").split(",")
                if x.strip()
            ]
            target = (getattr(args, "target", "") or "").strip() or None
            test_mode = bool(getattr(args, "test_events", False))
            from . import events as events_mod

            if test_mode:
                events_mod.apply_event_dirs(test_mode=True)

            bundle = build_analyst_bundle(
                target_path=Path(target) if target else None,
                compare_payload=compare_payload,
                validation_payload=validation_payload,
                ingest_payload=ingest_payload,
                run_ids=run_ids,
                synthetic=not bool(getattr(args, "real_data", False)),
                notes=getattr(args, "notes", None),
            )
            out_dir = (getattr(args, "out_dir", "") or "").strip()
            paths = write_analyst_bundle(
                bundle,
                out_dir=Path(out_dir) if out_dir else None,
                bundle_id=getattr(args, "bundle_id", None) or run["run_id"],
            )
            result = {
                "ok": True,
                "bundle_id": paths["json"].stem,
                "bundle_json": str(paths["json"]),
                "bundle_md": str(paths["md"]),
                "schema": bundle.get("schema"),
                "events_count": len((bundle.get("events") or {}).get("items") or []),
                "runs_count": len(bundle.get("runs") or []),
                "holdings_status": (bundle.get("holdings") or {}).get("file_status"),
            }
        finish_run(run["run_id"], status="ok", result=result)
        _print_json(result)
        return 0
    except PipelineLockError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 3
    except ValueError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        msg = str(e)
        code = "RUN_IDS_REQUIRED" if "RUN_IDS_REQUIRED" in msg else "BUNDLE_INVALID"
        _print_json({"error": msg, "code": code}, stream=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError, HoldingsValidationError, FileNotFoundError) as e:
        finish_run(run["run_id"], status="error", error=str(e))
        msg = str(e)
        code = "RUN_NOT_FOUND" if "RUN_NOT_FOUND" in msg else None
        payload: dict[str, Any] = {"error": msg}
        if code:
            payload["code"] = code
        _print_json(payload, stream=sys.stderr)
        return 2
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
            payload = dict(record.get("result") or {})
            payload.setdefault("success", record.get("status") == "ok")
            payload.setdefault("source", get_data_source_name())
            payload["from_run_id"] = args.run_id
            # Пишем под run_id самой команды report — не перезаписываем
            # исходный отчёт optimize/compare (RESULT cur-20261010-2229 D5).
            paths = write_report(
                run_id=run["run_id"],
                title=f"Report for {args.run_id}",
                payload=payload,
            )
            out = {
                "run_id": run["run_id"],
                "from_run_id": args.run_id,
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


def _require_successful_target(target_data: dict[str, Any], target_path: Path) -> dict[str, float]:
    """Принять только target с явным success=true и конечными весами Σ=1."""
    if not isinstance(target_data, dict):
        raise TargetValidationError(
            f"invalid target file {target_path}: expected JSON object"
        )
    if target_data.get("success") is not True:
        raise TargetValidationError(
            f"target {target_path} is not a successful optimization result "
            f"(success={target_data.get('success')!r}); "
            "refusing to use failed/incomplete target as portfolio goal "
            "(code=TARGET_NOT_SUCCESSFUL)"
        )
    weights = target_data.get("weights")
    if not isinstance(weights, dict) or not weights:
        raise TargetValidationError(
            f"target {target_path} missing non-empty 'weights' "
            "(code=TARGET_MISSING_WEIGHTS)"
        )
    clean: dict[str, float] = {}
    try:
        for ticker, value in weights.items():
            if not isinstance(ticker, str) or not ticker.strip():
                raise TargetValidationError("empty ticker in target weights")
            w = require_nonnegative_finite(value, f"target.weights[{ticker}]")
            clean[ticker.strip().upper()] = w
        total = sum(clean.values())
        if abs(total - 1.0) > 1e-6:
            raise TargetValidationError(
                f"target weights sum to {total:.6f}, expected 1.0 "
                "(code=TARGET_WEIGHT_SUM)"
            )
    except NumericValidationError as e:
        raise TargetValidationError(str(e)) from e
    return clean


def cmd_compare(args: argparse.Namespace) -> int:
    """Сравнить holdings с целевыми весами (только success=true target)."""
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
            target = _require_successful_target(target_data, target_path)
            try:
                min_drift = require_nonnegative_finite(args.min_drift, "min_drift")
            except NumericValidationError:
                raise
            report = compare_weights(current, target, min_drift=min_drift)
            report["target_path"] = str(target_path)
            report["holdings_empty"] = len(current) == 0
            report["target_success"] = True
            paths = write_report(
                run_id=run["run_id"],
                title="Compare report",
                payload={"success": True, "compare": report, "source": get_data_source_name()},
            )
            report["report_json"] = str(paths["json"])
            report["report_md"] = str(paths["md"])

        finish_run(run["run_id"], status="ok", result=report)
        _print_json(report)
        return 0
    except PipelineLockError as e:
        finish_run(run["run_id"], status="error", error=str(e))
        _print_json({"error": str(e)}, stream=sys.stderr)
        return 3
    except (HoldingsValidationError, TargetValidationError, NumericValidationError) as e:
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

    p_adp = sub.add_parser(
        "adapt-portfolio",
        help="Adapt analyst CSV → holdings JSON (read-only unless --write-holdings)",
    )
    p_adp.add_argument("--csv", required=True, help="Path to analyst portfolio CSV")
    p_adp.add_argument(
        "--isin-map",
        default="",
        help="Optional JSON map {ISIN: ticker} for unambiguous resolution",
    )
    p_adp.add_argument("--as-of", default="", help="Optional as_of date for holdings")
    p_adp.add_argument(
        "--panel-tickers",
        default="",
        help="Comma-separated tickers in price panel (flags missing_from_panel)",
    )
    p_adp.add_argument(
        "--write-holdings",
        action="store_true",
        help="Write data/portfolio/holdings.json (never writes /workspace/invest)",
    )
    p_adp.set_defaults(func=cmd_adapt_portfolio)

    p_ready = sub.add_parser(
        "check-portfolio-ready",
        help="Preflight portfolio CSV/holdings without running optimizer",
    )
    p_ready.add_argument("--csv", default="", help="Analyst portfolio CSV path")
    p_ready.add_argument(
        "--isin-map",
        default="",
        help="Optional JSON map {ISIN: ticker}",
    )
    p_ready.add_argument(
        "--panel-tickers",
        default="",
        help="Comma-separated tickers expected in price panel",
    )
    p_ready.set_defaults(func=cmd_check_portfolio_ready)

    p_imp = sub.add_parser(
        "import-user-prices",
        help="Import user-provided historical price CSV into runtime cache (no ISS)",
    )
    p_imp.add_argument("--csv", required=True, help="Local price panel CSV (; TRADEDATE)")
    p_imp.add_argument(
        "--require-tickers",
        default="",
        help="Comma-separated SECID/tickers that must exist in the panel",
    )
    p_imp.add_argument(
        "--skip-staleness",
        action="store_true",
        help="Attest historical panel; pair with MOEX_USER_CSV_SKIP_STALENESS=true",
    )
    p_imp.set_defaults(func=cmd_import_user_prices)

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
        "--max-staleness-days",
        type=int,
        default=5,
        help="Max age for live market sources (ignored for fixture/synthetic)",
    )
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

    p_ing = sub.add_parser(
        "ingest-events",
        help="Ingest Corporate Radar / inbox JSON (partial reject → exit 2)",
    )
    p_ing.add_argument(
        "--source",
        default="",
        help=(
            "Path to radar release JSON (e.g. /workspace/invest/news/events_latest.json). "
            "Copied into data/inbox/events/; original is never deleted."
        ),
    )
    p_ing.add_argument(
        "--test-events",
        action="store_true",
        help=(
            "Allow test releases (is_test=true and/or TEST-EV-* ids); "
            "writes to separate *_test directories under data/"
        ),
    )
    p_ing.set_defaults(func=cmd_ingest_events)

    p_rep = sub.add_parser("report", help="Write MD/JSON report for a journal run_id")
    p_rep.add_argument("--run-id", required=True, help="Existing run_id from outbox/runs")
    p_rep.set_defaults(func=cmd_report)

    p_bun = sub.add_parser(
        "build-analyst-bundle",
        help="Assemble CLI artifacts JSON for one-shot Portfolio Analyst handoff",
    )
    p_bun.add_argument("--target", default="", help="Path to last_target.json")
    p_bun.add_argument("--compare-json", default="", help="Saved compare result JSON")
    p_bun.add_argument("--validation-json", default="", help="Saved validate-data JSON")
    p_bun.add_argument("--ingest-json", default="", help="Saved ingest-events report JSON")
    p_bun.add_argument(
        "--run-ids",
        default="",
        help=(
            "Required: comma-separated journal run_id list to embed "
            "(empty runs[] is refused)"
        ),
    )
    p_bun.add_argument(
        "--test-events",
        action="store_true",
        help="Read events from test storage (*_test paths)",
    )
    p_bun.add_argument("--out-dir", default="", help="Output directory for bundle files")
    p_bun.add_argument("--bundle-id", default="", help="Optional bundle id / filename stem")
    p_bun.add_argument("--notes", default="", help="Free-form note for the analyst")
    p_bun.add_argument(
        "--real-data",
        action="store_true",
        help="Mark bundle as non-synthetic (default: synthetic=true)",
    )
    p_bun.set_defaults(func=cmd_build_analyst_bundle)

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
