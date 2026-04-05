"""
Normalize CONFIRME column values from Excel (business rules).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

# Spec targets CONFIRMÉ; exports often use CONFIRME (no accent).
CONFIRMED_STATUSES = frozenset({"CONFIRMÉ", "CONFIRME"})
EN_COURS_EXACT = "EN COURS"


def normalize_confirme_cell(val: Any) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return " ".join(str(val).strip().upper().split())


def is_confirmed_exact(val: Any) -> bool:
    return normalize_confirme_cell(val) in CONFIRMED_STATUSES


def is_en_cours(val: Any) -> bool:
    return normalize_confirme_cell(val) == EN_COURS_EXACT


def is_cancelled_status(val: Any) -> bool:
    t = normalize_confirme_cell(val)
    if not t:
        return False
    if t in ("ANNULE", "ANNULÉ", "ANNULÉE", "ANNULATION", "CANCELLED", "CANCELED"):
        return True
    if t.startswith("ANNULE") or t.startswith("ANNULÉ"):
        return True
    if "ANNUL" in t and t != EN_COURS_EXACT:
        return True
    return False
