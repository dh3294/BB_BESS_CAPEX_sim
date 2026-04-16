"""
defaults.py
-----------
Barbados-specific default parameter values.
All values sourced from Appendix B of the specification document.
Currency: USD (BBD / 2 at fixed 2:1 peg).
"""

# ─────────────────────────────────────────────
# Group 1: System Sizing & Capital Costs
# ─────────────────────────────────────────────
BESS_ENERGY_KWH: float = 500.0          # K_B  [kWh]
BESS_POWER_KW: float = 125.0            # K_I  [kW]
BESS_ENERGY_CAPEX: float = 165.0        # c_B_e [$/kWh]  Ember 2025 + island premium
BESS_POWER_CAPEX: float = 372.0         # c_B_p [$/kW]   NREL 2025 bottom-up
BESS_REPLACE_CAPEX: float = 83.0        # c_B_e_r [$/kWh] 50% of energy capex
BESS_OM: float = 14.9                   # c_B_om [$/kW/yr] 4% of power capex
BESS_AVAILABILITY: float = 0.97         # OA_B  [fraction]

PV_CAPACITY_KW: float = 300.0           # K_S   [kW]
PV_CAPEX: float = 1100.0               # c_PV  [$/kW]  IRENA 2024 Caribbean
PV_OM: float = 12.0                    # c_PV_om [$/kW/yr]
PV_DEGRADATION: float = 0.005          # deg_PV [fraction/yr]

N_EDGS: int = 4                        # N     [count]
EDG_CAPACITY_KW: float = 750.0         # K_G   [kW per unit]
EDG_CAPEX: float = 750.0              # c_G   [$/kW]
EDG_OM: float = 9.3                   # c_G_om [$/kW/yr]

MICROGRID_CAPEX: float = 4_000_000.0   # c_MG  [$]  (spec says $k flat = 4000 k)
MICROGRID_OM: float = 133_000.0        # c_MG_om [$/yr]

# ─────────────────────────────────────────────
# Group 2: Site & Load
# ─────────────────────────────────────────────
PEAK_LOAD_KW: float = 2000.0           # L_peak [kW]
CRITICAL_LOAD_FRACTION: float = 0.50   # f_crit [fraction]

# Large Power tariff (BL&P, September 16 2022 – USD values)
LARGE_POWER = {
    "e_base": 0.0585,    # $/kWh
    "d_rate": 13.83,     # $/kVA/mo
    "c_fixed": 471.75,   # $/mo
}

# Secondary Voltage tariff (BL&P, September 16 2022 – USD values)
SECONDARY_VOLTAGE = {
    "e_base": 0.069,     # $/kWh
    "d_rate": 13.21,     # $/kVA/mo
    "c_fixed": 47.25,    # $/mo
}

TARIFF_TIER: str = "Large Power"       # default tariff selection
E_BASE: float = LARGE_POWER["e_base"]  # $/kWh
E_FCA: float = 0.165                   # $/kWh  2024 annual avg (BBD~$0.33/kWh ÷ 2)
D_RATE: float = LARGE_POWER["d_rate"]  # $/kVA/mo
C_FIXED: float = LARGE_POWER["c_fixed"]  # $/mo
POWER_FACTOR: float = 0.85             # BL&P billing pf

DIESEL_COST: float = 6.44             # f_diesel [$/gal]  BBD$3.40/L × 3.785 ÷ 2
EDG_HEAT_RATE: float = 12040.0        # HR  [btu/kWh]

SOLAR_LAT: float = 13.10              # degrees N
SOLAR_LON: float = -59.62             # degrees W
SOLAR_TILT: float = 13.0             # degrees (≈ latitude)
SOLAR_LOSSES: float = 14.0           # %

HURRICANE_WEIGHTING: bool = True
HURRICANE_MONTHS: list = [6, 7, 8, 9, 10, 11]   # Jun–Nov (1-indexed)
# Hurricane irradiance depression multipliers: {day_offset: fraction_of_TMY}
HURRICANE_IRRADIANCE = {1: 0.20, 2: 0.40, 3: 0.70}  # Cole et al. 2020

# ─────────────────────────────────────────────
# Group 3: Financial Parameters
# ─────────────────────────────────────────────
ANALYSIS_PERIOD: int = 20             # T  [years]
DISCOUNT_RATE: float = 0.07           # r  [fraction]
INFLATION_RATE: float = 0.035         # i_gen [fraction/yr]
E_BASE_ESCALATION: float = 0.015      # i_e_base [fraction/yr]
FCA_ESCALATION: float = 0.020         # i_fca [fraction/yr]
DIESEL_ESCALATION: float = 0.025      # i_f [fraction/yr]
EST_ESCALATION: float = 0.00          # i_est [fraction/yr]  contracted fixed
ITC: float = 0.00                     # ITC  [fraction] no current Barbados ITC

# ─────────────────────────────────────────────
# Group 4: Reliability & Performance
# ─────────────────────────────────────────────
EDG_MTTF: float = 1662.0             # MTTF [hrs]  Marqusee et al. 2021 Table 1
EDG_FTS: float = 0.0013              # FTS  [fraction] – spec says 0.13%; Table 1 value
EDG_AVAILABILITY: float = 0.9998     # OA_G [fraction]

BESS_RTE: float = 0.90               # eta_B [fraction]  Ember 2025 LFP
BESS_SOC_MIN: float = 0.20           # SOC_min [fraction]
BATTERY_BINS: int = 100              # M  [bins] — lowered from 200 for cloud performance

D_MAX: int = 168                     # d_max [hrs]  1 week (lowered from 336 for cloud performance)
X_MIN: float = 0.90                  # minimum acceptable survival probability

OUTAGE_DISTRIBUTION: str = "Hurricane-weighted"   # default mode

# ─────────────────────────────────────────────
# EST Tariff Rates (FTC Decision, June 28 2023)
# All in USD (BBD ÷ 2)
# ─────────────────────────────────────────────
EST_RATES = {
    "2hr_lt25kw":   {"energy": 0.338, "capacity_per_kw_mo": 28.39},
    "3hr_25kw_1mw": {"energy": 0.202, "capacity_per_kw_mo": 16.98},
    "3hr_1mw_10mw": {"energy": 0.146, "capacity_per_kw_mo": 12.31},
    "4hr_25kw_1mw": {"energy": 0.187, "capacity_per_kw_mo": 20.98},
    "4hr_1mw_10mw": {"energy": 0.135, "capacity_per_kw_mo": 15.17},
}

# Default tier for the tool's representative system (4-hr, 25kW–1MW)
EST_DEFAULT_ENERGY_RATE: float = 0.187      # $/kWh
EST_DEFAULT_CAPACITY_RATE: float = 20.98    # $/kW/mo
EST_UTILISATION_RATE: float = 0.80          # fraction of daily cycles dispatched to grid
EST_REGULATORY_RISK_DISCOUNT: float = 0.0   # haircut for <1MW systems
EST_ELIGIBLE: bool = True                   # always assumed True per spec v1

# ─────────────────────────────────────────────
# PVWatts API
# ─────────────────────────────────────────────
PVWATTS_URL = "https://developer.nlr.gov/api/pvwatts/v8.json"
PVWATTS_DATASET = "nsrdb"

# ─────────────────────────────────────────────
# Derived computed values (display-only helpers)
# ─────────────────────────────────────────────
def total_retail_rate(e_base: float = E_BASE, e_fca: float = E_FCA) -> float:
    """e_rate = e_base + e_fca  [$/kWh]"""
    return e_base + e_fca


def est_tier(bess_power_kw: float, duration_hr: int = 4) -> str:
    """Return the EST rate tier key for a given BESS power capacity and duration."""
    if bess_power_kw < 25:
        return "2hr_lt25kw"
    elif bess_power_kw < 1000:
        return f"{duration_hr}hr_25kw_1mw"
    else:
        return f"{duration_hr}hr_1mw_10mw"


def get_tariff_defaults(tier: str) -> dict:
    """Return tariff defaults dict for a given BL&P tier name."""
    if tier == "Large Power":
        return LARGE_POWER.copy()
    elif tier == "Secondary Voltage":
        return SECONDARY_VOLTAGE.copy()
    else:
        raise ValueError(f"Unknown tariff tier: {tier}")
