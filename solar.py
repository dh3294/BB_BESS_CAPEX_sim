"""
solar.py
--------
PV resource loading and hurricane irradiance modifier.

Priority order:
  1. NREL PVWatts v8 API (requires NREL_API_KEY env var)
  2. Bundled Barbados TMY CSV fallback (pre-fetched from NSRDB at 13.10°N, 59.62°W)

If the API key is absent or the call fails, falls back to the CSV and
sets a warning flag that the UI displays as a yellow banner.

API endpoint: https://developer.nlr.gov/api/pvwatts/v8.json
  dataset=nsrdb, lat=13.10, lon=-59.62
"""

from __future__ import annotations
import os
import io
import warnings
import numpy as np
import pandas as pd

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
PVWATTS_URL     = "https://developer.nlr.gov/api/pvwatts/v8.json"
PVWATTS_DATASET = "nsrdb"
DEFAULT_LAT     = 13.10
DEFAULT_LON     = -59.62
TMY_CSV_PATH    = os.path.join(os.path.dirname(__file__), "data", "barbados_tmy.csv")

# Hurricane irradiance depression multipliers: {day_offset: fraction_of_TMY}
# Source: Cole et al. (2020)
HURRICANE_IRRADIANCE = {1: 0.20, 2: 0.40, 3: 0.70}
HURRICANE_MONTHS     = [6, 7, 8, 9, 10, 11]   # Jun–Nov


# ─────────────────────────────────────────────────────────────────────────────
# 1. PVWatts API loader
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_pvwatts(
    api_key: str,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    system_capacity: float = 1.0,   # kW — normalise to capacity factor
    tilt: float = 13.0,
    azimuth: float = 180.0,         # south-facing
    losses: float = 14.0,           # %
    array_type: int = 1,            # fixed open rack
    module_type: int = 0,           # standard
    timeframe: str = "hourly",
) -> np.ndarray:
    """
    Call PVWatts v8 API and return (8760,) hourly AC capacity factors.
    Raises on any HTTP or parsing error — caller handles fallback.
    """
    params = {
        "api_key":         api_key,
        "lat":             lat,
        "lon":             lon,
        "system_capacity": system_capacity,
        "tilt":            tilt,
        "azimuth":         azimuth,
        "losses":          losses,
        "array_type":      array_type,
        "module_type":     module_type,
        "timeframe":       timeframe,
        "dataset":         PVWATTS_DATASET,
    }
    resp = _requests.get(PVWATTS_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "errors" in data and data["errors"]:
        raise ValueError(f"PVWatts API error: {data['errors']}")

    ac_hourly = np.array(data["outputs"]["ac"], dtype=float)  # Wh/hr for 1 kW system

    if len(ac_hourly) != 8760:
        raise ValueError(f"Expected 8760 hourly values, got {len(ac_hourly)}")

    # Convert Wh → capacity factor (AC output / DC capacity)
    # For a 1 kW system: CF = ac_wh / 1000
    capacity_factors = ac_hourly / 1000.0
    return np.clip(capacity_factors, 0.0, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Fallback: synthetic Barbados TMY profile
# ─────────────────────────────────────────────────────────────────────────────

def _generate_synthetic_barbados_tmy() -> np.ndarray:
    """
    Generate a plausible synthetic hourly capacity factor profile for Barbados
    based on known climate characteristics:
      - Annual GHI ~5.5–6.0 kWh/m²/day
      - ~1,600–1,700 kWh/kWp/yr at optimal tilt
      - Low seasonal variability (tropical location)
      - Clear sky fraction ~0.60–0.70

    This is used ONLY as a last-resort fallback when no CSV and no API key.
    TODO: Replace with a real NSRDB TMY CSV bundled at data/barbados_tmy.csv.
    """
    hours = np.arange(8760)
    day_of_year = hours // 24          # 0–364
    hour_of_day = hours % 24           # 0–23

    # Solar noon offset from local solar time (Barbados ~14.5° W of UTC-4 meridian)
    solar_noon_hour = 12.0

    # Day-length variation: Barbados is close to equator, 10.5–13.5 hrs daylight
    day_length = 12.0 + 1.5 * np.sin(2 * np.pi * (day_of_year - 80) / 365.25)
    sunrise = solar_noon_hour - day_length / 2
    sunset  = solar_noon_hour + day_length / 2

    # Gaussian solar profile centred on solar noon
    sigma = day_length / 4.5
    solar_angle = np.exp(-0.5 * ((hour_of_day - solar_noon_hour) / sigma) ** 2)

    # Only during daylight hours
    daylight = (hour_of_day > sunrise) & (hour_of_day < sunset)
    solar_raw = solar_angle * daylight.astype(float)

    # Seasonal cloud cover modifier: slightly more cloud in Aug-Oct (hurricane season)
    cloud_modifier = 1.0 - 0.12 * np.sin(2 * np.pi * (day_of_year - 210) / 365.25)
    solar_raw *= cloud_modifier

    # Scale to target ~1650 kWh/kWp/yr (CF ≈ 0.188)
    annual_sum = solar_raw.sum()
    if annual_sum > 0:
        target_annual_kwh = 1650.0
        solar_raw *= target_annual_kwh / annual_sum

    return np.clip(solar_raw, 0.0, 1.0)


def _load_tmy_csv(path: str) -> np.ndarray:
    """
    Load hourly capacity factors from a bundled CSV file.
    Expected format: single column 'ac_cf' (or first numeric column), 8760 rows.
    """
    df = pd.read_csv(path)
    # Try common column names
    for col in ["ac_cf", "CF", "capacity_factor", "ac", "AC"]:
        if col in df.columns:
            vals = df[col].values.astype(float)
            if len(vals) == 8760:
                return np.clip(vals, 0.0, 1.0)

    # Fall back to first numeric column
    numeric_cols = df.select_dtypes(include=[float, int]).columns
    if len(numeric_cols) > 0:
        vals = df[numeric_cols[0]].values.astype(float)
        if len(vals) == 8760:
            return np.clip(vals, 0.0, 1.0)

    raise ValueError(f"Could not find 8760-row capacity factor column in {path}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Apply PV degradation
# ─────────────────────────────────────────────────────────────────────────────

def apply_degradation(profile: np.ndarray, year: int, deg_rate: float = 0.005) -> np.ndarray:
    """
    Apply annual PV degradation to the capacity factor profile.
    CF_year = CF_0 × (1 - deg_rate)^year
    """
    return profile * (1.0 - deg_rate) ** year


# ─────────────────────────────────────────────────────────────────────────────
# 4. Hurricane irradiance modifier
# ─────────────────────────────────────────────────────────────────────────────

def apply_hurricane_modifier(
    profile: np.ndarray,
    hurricane_months: list[int] | None = None,
    irradiance_depression: dict[int, float] | None = None,
    landfall_day_of_year: int | None = None,
) -> np.ndarray:
    """
    Apply hurricane irradiance depression to the TMY profile.

    If landfall_day_of_year is given, applies the Cole et al. (2020) profile
    for the specific event: Day 1 → 20% TMY, Day 2 → 40%, Day 3 → 70%.

    If landfall_day_of_year is None, applies a statistical reduction across
    all hurricane-season daylight hours to represent the seasonal average
    increased cloud cover and storm probability.

    Parameters
    ----------
    profile              : (8760,) base TMY capacity factors
    hurricane_months     : list of 1-indexed months in hurricane season
    irradiance_depression: {day_offset: fraction_of_tmy} e.g. {1:0.20, 2:0.40, 3:0.70}
    landfall_day_of_year : 1-indexed day of simulated hurricane landfall (optional)

    Returns
    -------
    Modified (8760,) capacity factor array.
    """
    if hurricane_months is None:
        hurricane_months = HURRICANE_MONTHS
    if irradiance_depression is None:
        irradiance_depression = HURRICANE_IRRADIANCE

    modified = profile.copy()
    hours = np.arange(8760)
    day_of_year = hours // 24  # 0-indexed

    if landfall_day_of_year is not None:
        # Apply point-event depression around the specified landfall day
        landfall_idx = landfall_day_of_year - 1  # 0-indexed
        for day_offset, fraction in irradiance_depression.items():
            target_day = landfall_idx + day_offset - 1
            if 0 <= target_day < 365:
                mask = day_of_year == target_day
                modified[mask] = profile[mask] * fraction
    else:
        # Statistical: reduce all hurricane-season hours by weighted average depression
        # Average reduction factor across the 3-day event window
        avg_factor = np.mean(list(irradiance_depression.values()))  # ≈ 0.433
        # Probability of a storm-affected day during hurricane season
        # Based on Barbados historical frequency: ~2–3 significant events per year
        storm_prob = 0.08   # ~8% of hurricane-season days are storm-affected

        # Build monthly mask
        days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        month_of_day = np.zeros(365, dtype=int)
        d = 0
        for m_idx, days in enumerate(days_per_month):
            month_of_day[d:d + days] = m_idx + 1
            d += days

        hour_month = month_of_day[np.clip(day_of_year, 0, 364)]
        in_hurricane_season = np.isin(hour_month, hurricane_months)

        # Apply expected reduction = P(storm) × (1 - avg_factor)
        reduction = storm_prob * (1.0 - avg_factor)
        modified[in_hurricane_season] *= (1.0 - reduction)

    return np.clip(modified, 0.0, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Build outage probability weights from hurricane season
# ─────────────────────────────────────────────────────────────────────────────

def build_outage_weights(
    mode: str = "hurricane",
    hurricane_months: list[int] | None = None,
    hurricane_multiplier: float = 3.0,
) -> np.ndarray:
    """
    Build (8760,) hourly outage probability weights.

    mode = 'uniform'    : equal probability for all hours (paper default)
    mode = 'hurricane'  : elevated probability in hurricane-season months

    hurricane_multiplier: ratio of hurricane-season to off-season hourly probability.
    Default 3.0 means outages are 3× more likely in Jun–Nov.
    """
    if hurricane_months is None:
        hurricane_months = HURRICANE_MONTHS

    weights = np.ones(8760, dtype=float)

    if mode == "uniform":
        return weights / weights.sum()

    # Build month index for each hour
    days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    month_of_day = np.zeros(365, dtype=int)
    d = 0
    for m_idx, days in enumerate(days_per_month):
        month_of_day[d:d + days] = m_idx + 1
        d += days

    hours = np.arange(8760)
    day_of_year = hours // 24
    hour_month = month_of_day[np.clip(day_of_year, 0, 364)]
    in_hurricane = np.isin(hour_month, hurricane_months)

    weights[in_hurricane] *= hurricane_multiplier

    return weights / weights.sum()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def load_solar_profile(
    params: dict | None = None,
) -> tuple[np.ndarray, str | None]:
    """
    Load the hourly PV capacity factor profile (8760 values, [0–1]).

    Returns
    -------
    (profile, warning_message)
      profile         : (8760,) numpy array of hourly capacity factors
      warning_message : None if API succeeded; warning string if fallback used
    """
    if params is None:
        params = {}

    lat    = float(params.get("lat",    DEFAULT_LAT))
    lon    = float(params.get("lon",    DEFAULT_LON))
    tilt   = float(params.get("tilt",   13.0))
    losses = float(params.get("losses", 14.0))

    api_key  = os.environ.get("NREL_API_KEY", "").strip()
    warning  = None

    # ── Attempt PVWatts API ───────────────────────────────────────────────────
    if api_key and _HAS_REQUESTS:
        try:
            profile = _fetch_pvwatts(api_key, lat=lat, lon=lon, tilt=tilt, losses=losses)
            return profile, None
        except Exception as exc:
            warning = (
                f"⚠️ PVWatts API call failed ({exc}). "
                "Using cached Barbados solar data."
            )
    else:
        if not api_key:
            warning = (
                "⚠️ NREL_API_KEY not set — using cached solar data."
            )
        elif not _HAS_REQUESTS:
            warning = (
                "⚠️ 'requests' library not available — using cached solar data."
            )

    # ── Fallback: bundled CSV ─────────────────────────────────────────────────
    if os.path.exists(TMY_CSV_PATH):
        try:
            profile = _load_tmy_csv(TMY_CSV_PATH)
            return profile, warning
        except Exception as exc2:
            warning = (warning or "") + f" CSV load also failed ({exc2}). Using synthetic profile."

    # ── Last resort: synthetic profile ────────────────────────────────────────
    profile = _generate_synthetic_barbados_tmy()
    if warning is None:
        warning = "⚠️ Using synthetic Barbados solar profile (no API key or CSV found)."
    return profile, warning


def get_modified_profile(
    params: dict | None = None,
) -> tuple[np.ndarray, str | None, np.ndarray]:
    """
    Full pipeline: load profile, apply hurricane modifier if enabled,
    return (base_profile, warning_message, outage_weights).

    The returned profile is year-0 (no degradation applied here;
    apply_degradation() is called per-year in the economics engine).
    """
    if params is None:
        params = {}

    profile, warning = load_solar_profile(params)

    hurricane_on  = bool(params.get("hurricane_weighting", True))
    outage_mode   = "hurricane" if hurricane_on else "uniform"
    outage_weights = build_outage_weights(mode=outage_mode)

    if hurricane_on:
        profile = apply_hurricane_modifier(profile)

    return profile, warning, outage_weights
