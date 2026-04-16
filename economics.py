"""
economics.py
------------
Life Cycle Cost (LCC) Engine — Section 6 of the spec, adapted from
Marqusee, Becker & Ericson (2021), Section 4.

Key Barbados adaptations:
  - No wholesale market revenue streams (no CAISO/PJM/DR).
  - Electricity rate split into stable base charge + volatile FCA.
  - Energy Storage Tariff (EST) replaces US demand-response revenues.
  - EST tier auto-selected based on BESS power capacity.
  - Demand charge modelled on BL&P non-coincident kVA billing.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# 1. NPV helper
# ─────────────────────────────────────────────────────────────────────────────

def npv(cashflows: np.ndarray, r: float) -> float:
    """
    NPV of a cashflow array (index = year 0, 1, …, T).
    Eq: NPV = sum( CF_t / (1+r)^t  for t in 0..T )
    """
    t = np.arange(len(cashflows), dtype=float)
    return float(np.sum(cashflows / (1.0 + r) ** t))


# ─────────────────────────────────────────────────────────────────────────────
# 2. EST rate tier selector
# ─────────────────────────────────────────────────────────────────────────────

def select_est_tier(bess_power_kw: float, duration_hr: int = 4) -> dict:
    """
    Return EST energy_rate [$/kWh] and capacity_rate [$/kW/mo] for the
    given BESS power capacity and storage duration (default 4-hour).
    Source: FTC Decision and Order, June 28 2023.
    """
    from defaults import EST_RATES

    if bess_power_kw < 25:
        tier_key = "2hr_lt25kw"
    elif bess_power_kw < 1000:
        tier_key = f"{duration_hr}hr_25kw_1mw"
    else:
        tier_key = f"{duration_hr}hr_1mw_10mw"

    return {
        "tier": tier_key,
        "energy_rate": EST_RATES[tier_key]["energy"],
        "capacity_rate": EST_RATES[tier_key]["capacity_per_kw_mo"],
        "above_1mw": bess_power_kw >= 1000,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Annual cashflow builders
# ─────────────────────────────────────────────────────────────────────────────

def annual_energy_savings(
    K_S: float,
    K_B: float,
    L_peak: float,
    f_crit: float,
    e_base: float,
    e_fca: float,
    i_e_base: float,
    i_fca: float,
    year: int,
    capacity_factor: float = 0.18,   # Barbados annual avg CF (~1600 kWh/kWp/yr ÷ 8760)
    self_consumption_fraction: float = 0.70,  # fraction of PV + BESS output used on-site
) -> float:
    """
    Annual retail electricity savings from PV self-consumption and BESS
    load shifting. Escalated separately for base and FCA components.

    Simplified: PV annual output × self-consumption fraction × total retail rate.
    TODO: Replace with hourly dispatch simulation for higher accuracy.
    """
    pv_annual_kwh = K_S * capacity_factor * 8760
    self_consumed_kwh = pv_annual_kwh * self_consumption_fraction

    e_base_yr = e_base * (1 + i_e_base) ** year
    e_fca_yr  = e_fca  * (1 + i_fca)   ** year
    e_total_yr = e_base_yr + e_fca_yr

    return self_consumed_kwh * e_total_yr


def annual_demand_charge_savings(
    K_I: float,
    d_rate: float,
    pf: float,
    i_e_base: float,
    year: int,
    demand_reduction_fraction: float = 0.30,   # fraction of peak demand shaved by BESS
) -> float:
    """
    Annual demand charge savings from BESS peak shaving.
    BL&P bills in kVA: kW_reduction / pf = kVA_reduction.
    Escalated at base energy escalation rate (FTC-controlled).
    """
    kva_reduced = (K_I * demand_reduction_fraction) / pf
    monthly_saving = kva_reduced * d_rate * (1 + i_e_base) ** year
    return monthly_saving * 12


def annual_est_revenue(
    K_I: float,
    K_B: float,
    est_energy_rate: float,
    est_capacity_rate: float,
    utilisation_rate: float,
    eta_B: float,
    i_est: float,
    year: int,
    est_eligible: bool = True,
    regulatory_risk_discount: float = 0.0,
    above_1mw: bool = False,
) -> float:
    """
    Annual EST revenue = capacity payment + energy export payment.

    Capacity payment:  K_I [kW] × est_capacity_rate [$/kW/mo] × 12
    Energy payment:    K_B [kWh] × eta_B × utilisation_rate × 365 × est_energy_rate

    Escalated at i_est (default 0% — contracted fixed rate).
    For >1 MW systems, apply regulatory_risk_discount haircut.
    """
    if not est_eligible:
        return 0.0

    capacity_payment = K_I * est_capacity_rate * 12
    kwh_dispatched = K_B * eta_B * utilisation_rate * 365
    energy_payment = kwh_dispatched * est_energy_rate

    total = (capacity_payment + energy_payment) * (1 + i_est) ** year

    if above_1mw:
        total *= (1.0 - regulatory_risk_discount)

    return total


def annual_avoided_diesel_fuel(
    N_hybrid: int,
    N_diesel: int,
    K_G: float,
    f_diesel: float,
    HR: float,
    capacity_factor_edg: float,
    i_f: float,
    year: int,
) -> float:
    """
    Annual savings from running fewer EDGs.
    delta_N = N_diesel - N_hybrid  (EDGs avoided in hybrid system).
    Annual fuel = delta_N × K_G × capacity_factor_edg × 8760 × HR / 3412 × $/gal

    HR: btu/kWh; diesel: ~132,000 btu/gal → gal = kWh × HR / 132000
    Escalated at diesel escalation rate i_f.
    """
    BTU_PER_GAL = 132_000.0
    delta_N = max(0, N_diesel - N_hybrid)
    kwh_per_yr = delta_N * K_G * capacity_factor_edg * 8760
    gal_per_yr = kwh_per_yr * HR / BTU_PER_GAL
    return gal_per_yr * f_diesel * (1 + i_f) ** year


def annual_fixed_om(
    K_I: float, K_S: float, K_G: float, N: int,
    c_B_om: float, c_PV_om: float, c_G_om: float,
    c_MG_om: float,
    i_gen: float, year: int,
    include_pv_bess: bool = True,
) -> float:
    """Annual fixed O&M costs, escalated at general inflation."""
    bess_om  = K_I * c_B_om  if include_pv_bess else 0.0
    pv_om    = K_S * c_PV_om if include_pv_bess else 0.0
    edg_om   = K_G * N * c_G_om
    infra_om = c_MG_om
    total_om = bess_om + pv_om + edg_om + infra_om
    return total_om * (1 + i_gen) ** year


def annual_retail_electricity_cost(
    L_peak: float,
    K_S: float,
    K_B: float,
    e_base: float,
    e_fca: float,
    d_rate: float,
    c_fixed: float,
    pf: float,
    i_e_base: float,
    i_fca: float,
    i_gen: float,
    year: int,
    include_pv_bess: bool = True,
    capacity_factor: float = 0.18,
    self_consumption_fraction: float = 0.70,
    demand_reduction_fraction: float = 0.30,
    K_I: float = 0.0,
) -> float:
    """
    Residual annual electricity bill after DER offset.
    = energy_bill + demand_bill + fixed_charge - savings_already_counted
    NOTE: energy savings counted separately; here we compute gross bill for baseline.
    """
    e_base_yr  = e_base * (1 + i_e_base) ** year
    e_fca_yr   = e_fca  * (1 + i_fca)   ** year
    d_rate_yr  = d_rate * (1 + i_e_base) ** year   # FTC-controlled, escalates with base
    c_fixed_yr = c_fixed * (1 + i_gen)  ** year

    # Approximate annual kWh load: L_peak × 8760 × load_factor
    load_factor = 0.60
    annual_kwh = L_peak * 8760 * load_factor

    if include_pv_bess:
        pv_annual = K_S * capacity_factor * 8760
        offset_kwh = pv_annual * self_consumption_fraction
        net_kwh = max(0.0, annual_kwh - offset_kwh)
        # Demand: BESS peak shaving — only applies when BESS power capacity > 0
        actual_dr = demand_reduction_fraction if K_I > 0 else 0.0
        kva_billed = (L_peak * (1 - actual_dr)) / pf
    else:
        net_kwh = annual_kwh
        kva_billed = L_peak / pf

    energy_bill  = net_kwh * (e_base_yr + e_fca_yr)
    demand_bill  = kva_billed * d_rate_yr * 12
    fixed_charge = c_fixed_yr * 12

    return energy_bill + demand_bill + fixed_charge


# ─────────────────────────────────────────────────────────────────────────────
# 4. Capital cost helper
# ─────────────────────────────────────────────────────────────────────────────

def capex_hybrid(params: dict) -> tuple[float, float]:
    """
    Returns (upfront_capex_yr0, replacement_capex_yr10) for the hybrid system.
    """
    K_I   = params["K_I"]
    K_B   = params["K_B"]
    K_S   = params["K_S"]
    N     = params["N"]
    K_G   = params["K_G"]

    c_B_e   = params["c_B_e"]
    c_B_p   = params["c_B_p"]
    c_B_e_r = params["c_B_e_r"]
    c_PV    = params["c_PV"]
    c_G     = params["c_G"]
    c_MG    = params["c_MG"]

    bess_capex  = K_B * c_B_e + K_I * c_B_p
    pv_capex    = K_S * c_PV
    edg_capex   = N   * K_G * c_G
    infra_capex = c_MG

    upfront = bess_capex + pv_capex + edg_capex + infra_capex
    replace = K_B * c_B_e_r + K_I * (c_B_p * 0.5)   # 50% of power capex at yr 10

    return upfront, replace


def capex_diesel(params: dict) -> tuple[float, float]:
    """
    Returns (upfront_capex_yr0, replacement_capex_yr10) for the diesel-only system.
    """
    N    = params["N"]
    K_G  = params["K_G"]
    c_G  = params["c_G"]
    c_MG = params["c_MG"]

    edg_capex   = N * K_G * c_G
    infra_capex = c_MG
    upfront     = edg_capex + infra_capex

    return upfront, 0.0  # no BESS replacement in diesel-only


# ─────────────────────────────────────────────────────────────────────────────
# 5. Full LCC calculation
# ─────────────────────────────────────────────────────────────────────────────

def run_lcc(params: dict) -> dict:
    """
    Run full life-cycle cost calculation for both hybrid and diesel-only systems.

    Returns dict with:
        lcc_hybrid        : pd.DataFrame  year-by-year costs/revenues, hybrid
        lcc_diesel        : pd.DataFrame  year-by-year costs/revenues, diesel-only
        npc_hybrid        : float   net present cost vs pre-microgrid baseline
        npc_diesel        : float   net present cost vs pre-microgrid baseline
        savings_waterfall : pd.DataFrame  cumulative savings by value stream
        payback_year      : int or None   first year hybrid NPC < diesel NPC
    """
    T          = int(params.get("T", 20))
    r          = float(params.get("r", 0.07))
    i_gen      = float(params.get("i_gen", 0.035))
    i_e_base   = float(params.get("i_e_base", 0.015))
    i_fca      = float(params.get("i_fca", 0.020))
    i_f        = float(params.get("i_f", 0.025))
    i_est      = float(params.get("i_est", 0.0))
    ITC        = float(params.get("ITC", 0.0))

    K_I        = float(params.get("K_I", 125.0))
    K_B        = float(params.get("K_B", 500.0))
    K_S        = float(params.get("K_S", 300.0))
    N          = int(params.get("N", 4))
    K_G        = float(params.get("K_G", 750.0))

    e_base     = float(params.get("e_base", 0.0585))
    e_fca      = float(params.get("e_fca", 0.165))
    d_rate     = float(params.get("d_rate", 13.83))
    c_fixed    = float(params.get("c_fixed", 471.75))
    pf         = float(params.get("pf", 0.85))
    L_peak     = float(params.get("L_peak", 2000.0))
    f_crit     = float(params.get("f_crit", 0.50))
    f_diesel   = float(params.get("f_diesel", 6.44))
    HR         = float(params.get("HR", 12040.0))

    c_B_om     = float(params.get("c_B_om", 14.9))
    c_PV_om    = float(params.get("c_PV_om", 12.0))
    c_G_om     = float(params.get("c_G_om", 9.3))
    c_MG_om    = float(params.get("c_MG_om", 133_000.0))

    est_eligible      = bool(params.get("est_eligible", True))
    est_utilisation   = float(params.get("est_utilisation", 0.80))
    reg_risk_discount = float(params.get("est_regulatory_risk_discount", 0.0))
    eta_B             = float(params.get("eta_B", 0.90))

    # EST rate tier
    est_info          = select_est_tier(K_I, duration_hr=4)
    est_energy_rate   = est_info["energy_rate"]
    est_capacity_rate = est_info["capacity_rate"]
    above_1mw         = est_info["above_1mw"]

    # EDG capacity factor (EDG not always running; assume 15% avg over year)
    cap_factor_edg = 0.15

    # ── Capital costs ─────────────────────────────────────────────────────────
    hybrid_capex_yr0, hybrid_replace_yr10 = capex_hybrid(params)
    diesel_capex_yr0, _                   = capex_diesel(params)

    hybrid_capex_yr0  *= (1.0 - ITC)   # apply tax incentive if any

    years = list(range(T + 1))

    # ── Year-by-year cashflows ────────────────────────────────────────────────
    rows_hybrid  = []
    rows_diesel  = []
    waterfall    = []

    for yr in years:
        # ── Common to both: annual retail electricity bill ───────────────────
        bill_diesel = annual_retail_electricity_cost(
            L_peak, 0.0, 0.0, e_base, e_fca, d_rate, c_fixed, pf,
            i_e_base, i_fca, i_gen, yr,
            include_pv_bess=False, K_I=0.0,
        )
        bill_hybrid = annual_retail_electricity_cost(
            L_peak, K_S, K_B, e_base, e_fca, d_rate, c_fixed, pf,
            i_e_base, i_fca, i_gen, yr,
            include_pv_bess=True, K_I=K_I,
        )

        # ── Hybrid-specific revenues ─────────────────────────────────────────
        est_rev = annual_est_revenue(
            K_I, K_B, est_energy_rate, est_capacity_rate,
            est_utilisation, eta_B, i_est, yr,
            est_eligible=est_eligible,
            regulatory_risk_discount=reg_risk_discount,
            above_1mw=above_1mw,
        )
        # Energy savings (separate from bill reduction above — avoids double-count)
        # Here we use bill_diesel - bill_hybrid as the implicit saving
        bill_saving = max(0.0, bill_diesel - bill_hybrid)

        avoided_fuel = annual_avoided_diesel_fuel(
            N_hybrid=max(0, N - 1),   # hybrid needs 1 fewer EDG on average
            N_diesel=N,
            K_G=K_G, f_diesel=f_diesel, HR=HR,
            capacity_factor_edg=cap_factor_edg,
            i_f=i_f, year=yr,
        )

        # ── O&M ──────────────────────────────────────────────────────────────
        om_hybrid = annual_fixed_om(
            K_I, K_S, K_G, N, c_B_om, c_PV_om, c_G_om, c_MG_om,
            i_gen, yr, include_pv_bess=True,
        )
        om_diesel = annual_fixed_om(
            0.0, 0.0, K_G, N, 0.0, 0.0, c_G_om, c_MG_om,
            i_gen, yr, include_pv_bess=False,
        )

        # ── Capital events ────────────────────────────────────────────────────
        capex_h = hybrid_capex_yr0 if yr == 0 else (hybrid_replace_yr10 if yr == 10 else 0.0)
        capex_d = diesel_capex_yr0 if yr == 0 else 0.0

        # ── Net annual cost (positive = expenditure) ─────────────────────────
        net_hybrid = capex_h + om_hybrid + bill_hybrid - est_rev - avoided_fuel
        net_diesel = capex_d + om_diesel + bill_diesel

        rows_hybrid.append({
            "year": yr,
            "capex": capex_h,
            "om": om_hybrid,
            "electricity_bill": bill_hybrid,
            "est_revenue": -est_rev,
            "avoided_fuel": -avoided_fuel,
            "net_cost": net_hybrid,
        })
        rows_diesel.append({
            "year": yr,
            "capex": capex_d,
            "om": om_diesel,
            "electricity_bill": bill_diesel,
            "net_cost": net_diesel,
        })
        waterfall.append({
            "year": yr,
            "est_revenue": est_rev,
            "bill_saving": bill_saving,
            "avoided_fuel": avoided_fuel,
            "total_saving": est_rev + bill_saving + avoided_fuel,
        })

    lcc_hybrid = pd.DataFrame(rows_hybrid)
    lcc_diesel = pd.DataFrame(rows_diesel)
    savings_df = pd.DataFrame(waterfall)

    # ── NPV / NPC ─────────────────────────────────────────────────────────────
    npc_hybrid = npv(lcc_hybrid["net_cost"].values, r)
    npc_diesel = npv(lcc_diesel["net_cost"].values, r)

    # Payback: first year where cumulative (diesel_cost - hybrid_cost) > 0
    cumulative_savings = (lcc_diesel["net_cost"] - lcc_hybrid["net_cost"]).cumsum()
    payback_rows = cumulative_savings[cumulative_savings > 0]
    payback_year = int(payback_rows.index[0]) if len(payback_rows) > 0 else None

    return {
        "lcc_hybrid":        lcc_hybrid,
        "lcc_diesel":        lcc_diesel,
        "npc_hybrid":        npc_hybrid,
        "npc_diesel":        npc_diesel,
        "savings_waterfall": savings_df,
        "payback_year":      payback_year,
        "est_tier":          est_info,
        "est_energy_rate":   est_energy_rate,
        "est_capacity_rate": est_capacity_rate,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Quick summary helper
# ─────────────────────────────────────────────────────────────────────────────

def summary_table(lcc_result: dict) -> pd.DataFrame:
    """Return a compact comparison table for display."""
    npc_h = lcc_result["npc_hybrid"]
    npc_d = lcc_result["npc_diesel"]
    pb    = lcc_result["payback_year"]

    rows = [
        {"Metric": "NPC — Hybrid System ($M)",        "Value": f"${npc_h/1e6:.2f}M"},
        {"Metric": "NPC — Diesel-Only System ($M)",   "Value": f"${npc_d/1e6:.2f}M"},
        {"Metric": "NPC Difference (Hybrid savings)", "Value": f"${(npc_d - npc_h)/1e6:.2f}M"},
        {"Metric": "Simple Payback (years)",          "Value": str(pb) if pb else ">20 yrs"},
        {"Metric": "EST Tier",                        "Value": lcc_result["est_tier"]["tier"]},
        {"Metric": "EST Energy Rate ($/kWh)",         "Value": f"${lcc_result['est_energy_rate']:.3f}"},
        {"Metric": "EST Capacity Rate ($/kW/mo)",     "Value": f"${lcc_result['est_capacity_rate']:.2f}"},
    ]
    return pd.DataFrame(rows)
