from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize NaN/NA values to None across all columns."""
    return df.astype(object).where(pd.notna(df), None)


def load_employees() -> pd.DataFrame:
    return _clean_df(pd.read_csv(DATA_DIR / "employees.csv"))


def load_budgets() -> pd.DataFrame:
    return _clean_df(pd.read_csv(DATA_DIR / "department_budgets.csv"))


def load_software_catalog() -> pd.DataFrame:
    return _clean_df(pd.read_csv(DATA_DIR / "software_catalog.csv"))


def load_vendors() -> pd.DataFrame:
    return _clean_df(pd.read_csv(DATA_DIR / "vendors.csv"))


def load_purchase_history() -> pd.DataFrame:
    return _clean_df(pd.read_csv(DATA_DIR / "purchase_history.csv"))


def load_requests() -> list[dict]:
    return json.loads((DATA_DIR / "requests.json").read_text(encoding="utf-8"))


def get_request(request_id: str) -> dict:
    for request in load_requests():
        if request["request_id"] == request_id:
            return request

    extra_path = ROOT / "evals" / "extra_cases.json"
    if extra_path.exists():
        try:
            extra_cases = json.loads(extra_path.read_text(encoding="utf-8"))
            for case in extra_cases:
                if case.get("request_id") == request_id and "request" in case:
                    return case["request"]
        except Exception:
            pass

    raise KeyError(f"Unknown request_id: {request_id}")


def load_policy_text() -> str:
    return (DATA_DIR / "procurement_policy.md").read_text(encoding="utf-8")
