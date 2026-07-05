"""
data_provider.py — Global oil field profile database & client data ingestion
=============================================================================
Fallback database of famous global producing assets with realistic baseline
fluid traits. Supports fuzzy name search, unknown-field baseline fallback,
and CSV laboratory report import for client-specific overrides.

Designed for ogcorrosion.org — globally applicable, operator-agnostic.
"""

from __future__ import annotations

import csv
import io
from typing import Any

# ---------------------------------------------------------------------------
# Slider / session-state keys used by app.py
# ---------------------------------------------------------------------------

PROFILE_KEYS: list[str] = [
    "pressure",
    "temperature",
    "velocity",
    "water_cut",
    "gor",
    "co2",
    "h2s",
    "inhibitor_dose",
    "chem_cost",
    "inhibitor_eff",
    "use_physical",
    "measured_wall",
    "operating_days",
    "production_bpd",
    "critical_days",
]

# Standard global baseline for unrecognized / new client assets
GLOBAL_BASELINE: dict[str, float | int | bool] = {
    "pressure": 2500,
    "temperature": 85,
    "velocity": 3.5,
    "water_cut": 25,
    "gor": 600,
    "co2": 4.0,
    "h2s": 5.0,
    "inhibitor_dose": 35,
    "chem_cost": 12.50,
    "inhibitor_eff": 85,
    "use_physical": False,
    "measured_wall": 8.5,
    "operating_days": 365,
    "production_bpd": 5000,
    "critical_days": 30,
}

# ---------------------------------------------------------------------------
# Global field database — famous producing assets worldwide
# ---------------------------------------------------------------------------

GLOBAL_FIELD_DATABASE: dict[str, dict[str, float | int | bool]] = {
    "Ghawar (Saudi Arabia)": {
        "pressure": 2800,
        "temperature": 90,
        "velocity": 3.2,
        "water_cut": 25,
        "gor": 480,
        "co2": 1.5,
        "h2s": 1.2,
        "inhibitor_dose": 30,
        "chem_cost": 10.00,
        "inhibitor_eff": 88,
        "use_physical": False,
        "measured_wall": 9.0,
        "operating_days": 365,
        "production_bpd": 12000,
        "critical_days": 30,
    },
    "Prudhoe Bay (USA)": {
        "pressure": 2200,
        "temperature": 80,
        "velocity": 2.8,
        "water_cut": 40,
        "gor": 750,
        "co2": 2.2,
        "h2s": 0.05,
        "inhibitor_dose": 40,
        "chem_cost": 14.00,
        "inhibitor_eff": 86,
        "use_physical": False,
        "measured_wall": 8.8,
        "operating_days": 400,
        "production_bpd": 6000,
        "critical_days": 30,
    },
    "Brent (North Sea)": {
        "pressure": 3200,
        "temperature": 75,
        "velocity": 4.1,
        "water_cut": 15,
        "gor": 420,
        "co2": 0.8,
        "h2s": 0.01,
        "inhibitor_dose": 25,
        "chem_cost": 15.50,
        "inhibitor_eff": 90,
        "use_physical": False,
        "measured_wall": 9.2,
        "operating_days": 365,
        "production_bpd": 4500,
        "critical_days": 25,
    },
    "Sabriyah Field (KOC) - High Water Cut": {
        "pressure": 1750,
        "temperature": 72,
        "velocity": 4.2,
        "water_cut": 68,
        "gor": 350,
        "co2": 3.0,
        "h2s": 3.5,
        "inhibitor_dose": 55,
        "chem_cost": 11.50,
        "inhibitor_eff": 80,
        "use_physical": False,
        "measured_wall": 7.2,
        "operating_days": 540,
        "production_bpd": 8500,
        "critical_days": 45,
    },
    "Deep Jurassic Gas Field - HPHT Sour": {
        "pressure": 5200,
        "temperature": 138,
        "velocity": 7.8,
        "water_cut": 38,
        "gor": 2200,
        "co2": 9.5,
        "h2s": 32.0,
        "inhibitor_dose": 65,
        "chem_cost": 18.00,
        "inhibitor_eff": 72,
        "use_physical": True,
        "measured_wall": 6.8,
        "operating_days": 270,
        "production_bpd": 3200,
        "critical_days": 30,
    },
}

# Short-name aliases for fuzzy search (lowercase → canonical database key)
SEARCH_ALIASES: dict[str, str] = {
    "ghawar": "Ghawar (Saudi Arabia)",
    "saudi": "Ghawar (Saudi Arabia)",
    "prudhoe": "Prudhoe Bay (USA)",
    "prudhoe bay": "Prudhoe Bay (USA)",
    "alaska": "Prudhoe Bay (USA)",
    "brent": "Brent (North Sea)",
    "north sea": "Brent (North Sea)",
    "sabriyah": "Sabriyah Field (KOC) - High Water Cut",
    "sab": "Sabriyah Field (KOC) - High Water Cut",
    "koc": "Sabriyah Field (KOC) - High Water Cut",
    "jurassic": "Deep Jurassic Gas Field - HPHT Sour",
    "hpht": "Deep Jurassic Gas Field - HPHT Sour",
    "sour": "Deep Jurassic Gas Field - HPHT Sour",
}

# CSV parameter name → session-state key mapping (flexible client headers)
CSV_PARAM_MAP: dict[str, str] = {
    "field_name": "field_name",
    "asset_name": "field_name",
    "water_cut": "water_cut",
    "water_cut_pct": "water_cut",
    "watercut": "water_cut",
    "wc": "water_cut",
    "co2": "co2",
    "co2_mol_pct": "co2",
    "co2_percent": "co2",
    "h2s": "h2s",
    "h2s_ppm": "h2s",
    "temperature": "temperature",
    "temperature_c": "temperature",
    "temp": "temperature",
    "velocity": "velocity",
    "velocity_m_s": "velocity",
    "flow_velocity": "velocity",
    "pressure": "pressure",
    "pressure_psi": "pressure",
    "thp": "pressure",
    "gor": "gor",
    "gor_scf_bbl": "gor",
    "inhibitor_dosage_ppm": "inhibitor_dose",
    "inhibitor_dose": "inhibitor_dose",
    "inhibitor": "inhibitor_dose",
    "chemical_cost_per_liter_usd": "chem_cost",
    "chem_cost": "chem_cost",
    "chemical_cost": "chem_cost",
    "inhibitor_efficiency_pct": "inhibitor_eff",
    "inhibitor_eff": "inhibitor_eff",
    "inhibitor_efficiency": "inhibitor_eff",
    "production_bpd": "production_bpd",
    "production_rate": "production_bpd",
    "bpd": "production_bpd",
    "measured_wall_thickness_mm": "measured_wall",
    "measured_wall": "measured_wall",
    "wall_thickness": "measured_wall",
    "operating_days": "operating_days",
    "critical_days": "critical_days",
}

# Downloadable CSV template for client laboratory reports
CSV_TEMPLATE_CONTENT = """parameter,value,unit,notes
field_name,My Custom Field,,Client asset identifier
water_cut,25,%,Volumetric water cut from separator test
co2,1.5,%,CO2 mol% from gas chromatograph
h2s,1.2,ppm,H2S concentration from lab analysis
temperature,90,°C,Wellhead or downhole temperature
velocity,3.2,m/s,Superficial fluid velocity
pressure,2500,psi,Tubing head pressure
gor,600,SCF/BBL,Gas-oil ratio
inhibitor_dose,35,ppm,Filming amine injection rate
chem_cost,12.50,USD/L,Chemical unit cost for ROI calc
inhibitor_eff,85,%,Laboratory coupon efficiency
production_bpd,5000,BPD,Gross liquid production rate
measured_wall,8.5,mm,Optional UT/ILI wall thickness
operating_days,365,days,Days since last inspection
critical_days,30,days,Critical risk duration for exposure cost
"""


def list_known_fields() -> list[str]:
    """Return sorted list of all known global field names."""
    return sorted(GLOBAL_FIELD_DATABASE.keys())


def _normalize_query(query: str) -> str:
    return query.strip().lower()


def resolve_field_search(query: str) -> tuple[dict[str, Any], str, bool]:
    """
    Resolve a user search string to a field profile.

    Returns:
        (profile_dict, display_name, is_known_match)

    - Known match: loads exact global database presets
    - Unknown field: returns GLOBAL_BASELINE without crashing
    """
    normalized = _normalize_query(query)

    if not normalized:
        baseline = GLOBAL_BASELINE.copy()
        return baseline, "Global Baseline", False

    # 1. Exact canonical name match
    for canonical_name, profile in GLOBAL_FIELD_DATABASE.items():
        if normalized == canonical_name.lower():
            return profile.copy(), canonical_name, True

    # 2. Alias table match (substring)
    for alias, canonical_name in SEARCH_ALIASES.items():
        if alias in normalized or normalized in alias:
            profile = GLOBAL_FIELD_DATABASE[canonical_name]
            return profile.copy(), canonical_name, True

    # 3. Partial match against canonical names
    for canonical_name, profile in GLOBAL_FIELD_DATABASE.items():
        name_lower = canonical_name.lower()
        # Match if query appears in name or name keyword appears in query
        name_tokens = [t for t in name_lower.replace("(", " ").replace(")", " ").split() if len(t) > 2]
        if normalized in name_lower or any(token in normalized for token in name_tokens):
            return profile.copy(), canonical_name, True

    # 4. Unknown / new client asset — safe fallback
    baseline = GLOBAL_BASELINE.copy()
    display = query.strip() or "New Asset"
    return baseline, display, False


def apply_profile(profile: dict[str, Any], display_name: str) -> dict[str, Any]:
    """
    Validate and return a clean profile dict ready for session-state injection.
    Missing keys are filled from GLOBAL_BASELINE.
    """
    clean: dict[str, Any] = GLOBAL_BASELINE.copy()
    clean.update({k: v for k, v in profile.items() if k in PROFILE_KEYS})
    clean["_display_name"] = display_name
    return clean


def parse_laboratory_csv(file_bytes: bytes) -> tuple[dict[str, Any], str, list[str]]:
    """
    Parse uploaded laboratory CSV and map to engine variables.

    Accepts two formats:
      A) parameter,value[,unit]  (row-oriented — template format)
      B) header row with named columns (column-oriented)

    Returns:
        (profile_overrides, field_name, warnings)
    """
    warnings: list[str] = []
    overrides: dict[str, Any] = {}
    field_name = "Uploaded Laboratory Report"

    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]

    if not rows:
        warnings.append("CSV file is empty.")
        return overrides, field_name, warnings

    header = [cell.strip().lower() for cell in rows[0]]

    # Format A: parameter,value header
    if "parameter" in header and "value" in header:
        param_idx = header.index("parameter")
        val_idx = header.index("value")
        for row in rows[1:]:
            if len(row) <= max(param_idx, val_idx):
                continue
            raw_param = row[param_idx].strip().lower()
            raw_val = row[val_idx].strip()
            mapped = CSV_PARAM_MAP.get(raw_param)
            if mapped == "field_name":
                field_name = raw_val
                continue
            if mapped and raw_val:
                overrides[mapped] = _coerce_value(mapped, raw_val, warnings)
        return overrides, field_name, warnings

    # Format B: column-oriented (first row = headers)
    col_map: dict[int, str] = {}
    for i, col in enumerate(header):
        mapped = CSV_PARAM_MAP.get(col)
        if mapped:
            col_map[i] = mapped

    if not col_map:
        warnings.append(
            "Unrecognized CSV headers. Download the sample template and use "
            "parameter,value format."
        )
        return overrides, field_name, warnings

    # Use first data row
    if len(rows) < 2:
        warnings.append("CSV has headers but no data rows.")
        return overrides, field_name, warnings

    data_row = rows[1]
    for i, mapped_key in col_map.items():
        if i < len(data_row) and data_row[i].strip():
            if mapped_key == "field_name":
                field_name = data_row[i].strip()
            else:
                overrides[mapped_key] = _coerce_value(mapped_key, data_row[i].strip(), warnings)

    return overrides, field_name, warnings


def _coerce_value(key: str, raw: str, warnings: list[str]) -> float | int | bool:
    """Coerce CSV string to the correct Python type for a profile key."""
    lower = raw.strip().lower()
    if key == "use_physical":
        return lower in ("true", "1", "yes", "on")

    try:
        if key in ("water_cut", "gor", "inhibitor_dose", "inhibitor_eff", "production_bpd", "critical_days", "operating_days"):
            return int(float(lower))
        return float(lower)
    except ValueError:
        warnings.append(f"Could not parse '{raw}' for {key}; skipped.")
        return GLOBAL_BASELINE.get(key, 0)  # type: ignore[return-value]


def merge_profile_with_upload(
    base_profile: dict[str, Any],
    csv_overrides: dict[str, Any],
    field_name: str,
) -> dict[str, Any]:
    """Merge CSV overrides onto a base profile."""
    merged = base_profile.copy()
    merged.update(csv_overrides)
    merged["_display_name"] = field_name
    return merged


def get_csv_template_bytes() -> bytes:
    """Return UTF-8 encoded sample CSV template for download."""
    return CSV_TEMPLATE_CONTENT.encode("utf-8")
