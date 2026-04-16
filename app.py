"""
app.py — v1.2
Barbados Hybrid Microgrid Economics Tool

Strategy for fast load:
- Economics (run_lcc) runs on startup — takes ~1s pure Python/pandas, no matplotlib
- All charts are behind a 'Show Charts' button — matplotlib imports deferred
- Reliability engine never auto-runs — on-demand only via Tab 2 button
- EST sensitivity chart removed from default view (was 1.3s alone)
"""

import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(
    page_title="Barbados Hybrid Microgrid Tool",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

import defaults as D
from economics import run_lcc, summary_table

# ─────────────────────────────────────────────────────────────────────────────
# BLUE INFO BANNER
# ─────────────────────────────────────────────────────────────────────────────
if "blp_dismissed" not in st.session_state:
    st.session_state.blp_dismissed = False

if not st.session_state.blp_dismissed:
    col_msg, col_btn = st.columns([20, 1])
    with col_msg:
        st.info(
            "**Note:** As of August 2024, BL&P has paused new PV grid connections "
            "pending additional storage deployment. BESS is currently a prerequisite "
            "for new PV interconnection approval. Confirm status with BL&P before planning."
        )
    with col_btn:
        if st.button("✕", key="dismiss_blp"):
            st.session_state.blp_dismissed = True
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR INPUTS
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.title("⚡ Microgrid Parameters")
st.sidebar.markdown("---")

if st.sidebar.button("🔄 Reset to Barbados Defaults"):
    for k in list(st.session_state.keys()):
        if k != "blp_dismissed":
            del st.session_state[k]
    st.rerun()

st.sidebar.markdown("---")

# Group 1 — Capital Costs
with st.sidebar.expander("⚙️ Group 1 — System Sizing & Capital Costs", expanded=True):
    st.markdown("**BESS**")
    K_B     = st.number_input("BESS Energy (kWh)", min_value=0.0, value=float(D.BESS_ENERGY_KWH), step=50.0, key="K_B")
    K_I     = st.number_input("BESS Power (kW)",   min_value=0.0, value=float(D.BESS_POWER_KW),   step=25.0, key="K_I")
    c_B_e   = st.slider("BESS Energy Capex ($/kWh)", 50, 400, int(D.BESS_ENERGY_CAPEX), key="c_B_e")
    c_B_p   = st.slider("BESS Power Capex ($/kW)",   50, 600, int(D.BESS_POWER_CAPEX),  key="c_B_p")
    c_B_e_r = st.slider("BESS Replacement Capex yr-10 ($/kWh)", 25, 200, int(D.BESS_REPLACE_CAPEX), key="c_B_e_r")
    c_B_om  = st.slider("BESS Fixed O&M ($/kW/yr)", 5, 30, int(D.BESS_OM), key="c_B_om")

    st.markdown("**PV**")
    K_S     = st.number_input("PV Capacity (kW)", min_value=0.0, value=float(D.PV_CAPACITY_KW), step=50.0, key="K_S")
    c_PV    = st.slider("PV Capex ($/kW)", 500, 2000, int(D.PV_CAPEX), key="c_PV")
    c_PV_om = st.slider("PV O&M ($/kW/yr)", 5, 20, int(D.PV_OM), key="c_PV_om")

    st.markdown("**EDGs**")
    N      = st.selectbox("Number of EDGs", list(range(1, 21)), index=D.N_EDGS - 1, key="N")
    K_G    = st.selectbox("EDG Capacity per Unit (kW)", [250, 500, 750, 1000], index=2, key="K_G")
    c_G    = st.slider("EDG Capex ($/kW)", 400, 1200, int(D.EDG_CAPEX), key="c_G")
    c_G_om = st.slider("EDG O&M ($/kW/yr)", 5, 20, int(D.EDG_OM), key="c_G_om")

    st.markdown("**Infrastructure**")
    c_MG    = st.number_input("Microgrid Capex ($k)", min_value=0.0, value=float(D.MICROGRID_CAPEX/1000), step=100.0, key="c_MG") * 1000
    c_MG_om = st.number_input("Microgrid O&M ($k/yr)", min_value=0.0, value=float(D.MICROGRID_OM/1000),   step=10.0,  key="c_MG_om") * 1000

# Group 2 — Site & Load
with st.sidebar.expander("🏭 Group 2 — Site & Load", expanded=False):
    L_peak = st.number_input("Peak Campus Load (kW)", min_value=0.0, value=float(D.PEAK_LOAD_KW), step=100.0, key="L_peak")
    f_crit = st.slider("Critical Load Fraction (%)", 20, 100, int(D.CRITICAL_LOAD_FRACTION * 100), key="f_crit") / 100.0

    st.markdown("**BL&P Tariff**")
    tariff_tier = st.radio("Tariff Tier", ["Large Power", "Secondary Voltage"], index=0, key="tariff_tier")
    td = D.get_tariff_defaults(tariff_tier)
    e_base  = st.number_input("Base Energy Charge ($/kWh)", value=td["e_base"], step=0.001, format="%.4f", key="e_base")
    e_fca   = st.slider("FCA ($/kWh)", 0.10, 0.30, float(D.E_FCA), step=0.001, format="%.3f", key="e_fca")
    st.metric("Total Rate ($/kWh)", f"${e_base + e_fca:.4f}")
    d_rate  = st.number_input("Demand Charge ($/kVA/mo)", value=td["d_rate"], step=0.01, format="%.2f", key="d_rate")
    c_fixed = st.number_input("Fixed Charge ($/mo)", value=td["c_fixed"], step=1.0, key="c_fixed")
    pf      = st.slider("Power Factor", 0.80, 1.00, float(D.POWER_FACTOR), step=0.01, key="pf")

    st.markdown("**Fuel**")
    f_diesel = st.slider("Diesel Cost ($/gal)", 3.0, 10.0, float(D.DIESEL_COST), step=0.01, key="f_diesel")
    HR       = st.number_input("EDG Heat Rate (btu/kWh)", min_value=8000.0, value=float(D.EDG_HEAT_RATE), step=100.0, key="HR")

# Group 3 — Financial
with st.sidebar.expander("💰 Group 3 — Financial Parameters", expanded=False):
    T_analysis = st.selectbox("Analysis Period (years)", [15, 20, 25], index=1, key="T_analysis")
    r          = st.slider("Discount Rate (%)", 4, 15, int(D.DISCOUNT_RATE * 100), key="r") / 100.0
    i_gen      = st.slider("General Inflation (%/yr)", 1, 5, int(D.INFLATION_RATE * 100), key="i_gen") / 100.0
    i_e_base   = st.slider("Base Rate Escalation (%/yr)", 0, 4, int(D.E_BASE_ESCALATION * 100), key="i_e_base") / 100.0
    i_fca      = st.slider("FCA Escalation (%/yr)", -5, 10, int(D.FCA_ESCALATION * 100), key="i_fca") / 100.0
    i_f        = st.slider("Diesel Escalation (%/yr)", 1, 6, int(D.DIESEL_ESCALATION * 100), key="i_f") / 100.0
    i_est      = st.slider("EST Escalation (%/yr)", 0, 3, int(D.EST_ESCALATION * 100), key="i_est") / 100.0
    ITC        = st.slider("Import Tax Incentive (%)", 0, 30, int(D.ITC * 100), key="ITC") / 100.0
    est_utilisation = st.slider("EST Dispatch Utilisation (%)", 50, 100, int(D.EST_UTILISATION_RATE * 100), key="est_utilisation") / 100.0
    est_reg_risk    = st.slider("EST Regulatory Risk Discount >1MW (%)", 0, 100, 0, key="est_reg_risk") / 100.0

# Group 4 — Reliability (hidden, on demand only)
with st.sidebar.expander("🔧 Group 4 — Reliability (Tab 2 only)", expanded=False):
    st.caption("Only used when you click Run Reliability on Tab 2.")
    MTTF    = st.slider("EDG MTTF (hrs)", 500, 3000, int(D.EDG_MTTF), step=50, key="MTTF")
    FTS     = st.slider("EDG Failure-to-Start (%)", 0.05, 0.30, float(D.EDG_FTS * 100), step=0.01, key="FTS") / 100.0
    OA_G    = st.slider("EDG Availability (%)", 95, 100, int(D.EDG_AVAILABILITY * 100), key="OA_G") / 100.0
    OA_B    = st.slider("BESS Availability (%)", 95, 100, int(D.BESS_AVAILABILITY * 100), key="OA_B") / 100.0
    eta_B   = st.slider("BESS Round-Trip Efficiency (%)", 80, 95, int(D.BESS_RTE * 100), key="eta_B") / 100.0
    SOC_min = st.slider("BESS Min SOC (%)", 10, 30, int(D.BESS_SOC_MIN * 100), key="SOC_min") / 100.0
    M       = st.selectbox("Battery Bins (M)", [50, 100, 200], index=1, key="M")
    d_max   = st.slider("Max Outage Duration (hrs)", 24, 336, D.D_MAX, step=24, key="d_max")
    X_min   = st.slider("Min Acceptable Survival (%)", 80, 99, int(D.X_MIN * 100), key="X_min") / 100.0

st.sidebar.markdown("---")
run_econ_btn = st.sidebar.button("▶ Run Economics", type="primary", use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# Params dict
# ─────────────────────────────────────────────────────────────────────────────
params = dict(
    K_B=K_B, K_I=K_I, K_S=K_S, N=N, K_G=float(K_G),
    c_B_e=float(c_B_e), c_B_p=float(c_B_p), c_B_e_r=float(c_B_e_r),
    c_B_om=float(c_B_om), c_PV_om=float(c_PV_om), c_G_om=float(c_G_om),
    c_PV=float(c_PV), c_G=float(c_G), c_MG=float(c_MG), c_MG_om=float(c_MG_om),
    L_peak=L_peak, f_crit=f_crit,
    e_base=e_base, e_fca=e_fca, d_rate=d_rate, c_fixed=c_fixed, pf=pf,
    f_diesel=f_diesel, HR=HR, deg_PV=D.PV_DEGRADATION,
    T=T_analysis, r=r, i_gen=i_gen, i_e_base=i_e_base,
    i_fca=i_fca, i_f=i_f, i_est=i_est, ITC=ITC,
    est_eligible=True, est_utilisation=est_utilisation,
    est_regulatory_risk_discount=est_reg_risk,
    MTTF=float(MTTF), FTS=FTS, OA_G=OA_G, OA_B=OA_B,
    eta_B=eta_B, SOC_min=SOC_min, M=M, d_max=d_max,
    hurricane_weighting=True, lat=D.SOLAR_LAT, lon=D.SOLAR_LON,
)

# ─────────────────────────────────────────────────────────────────────────────
# Economics — runs on first load and on button press
# ─────────────────────────────────────────────────────────────────────────────
def _run_econ(params):
    econ = run_lcc(params)
    st.session_state["econ"] = econ
    st.session_state["params_run"] = params.copy()
    st.session_state["econ_done"] = True

if "econ_done" not in st.session_state:
    _run_econ(params)

if run_econ_btn:
    _run_econ(params)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN PANEL
# ─────────────────────────────────────────────────────────────────────────────
st.title("⚡ Barbados Hybrid Microgrid Resilience & Economics Tool")
st.caption(
    "Life-cycle economics of PV + BESS + EDG hybrid microgrids for the Barbados market. "
    "Methodology: Marqusee, Becker & Ericson (2021), *Advances in Applied Energy* Vol. 3."
)

tab1, tab2, tab3 = st.tabs(["💵 Economics", "📊 Reliability (on demand)", "🌪️ Sensitivity (v2)"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — ECONOMICS (instant, no matplotlib)
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    if not st.session_state.get("econ_done"):
        st.info("Calculating…")
        st.stop()

    econ = st.session_state["econ"]
    p    = st.session_state["params_run"]

    npc_h   = econ["npc_hybrid"]
    npc_d   = econ["npc_diesel"]
    savings = npc_d - npc_h
    pb      = econ["payback_year"]

    # ── Top metrics ───────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hybrid NPC",      f"${npc_h/1e6:.2f}M", help=f"{p['T']}-year net present cost")
    c2.metric("Diesel-Only NPC", f"${npc_d/1e6:.2f}M")
    c3.metric("Hybrid Saves",    f"${savings/1e6:.2f}M",
              delta=f"${savings/1e6:.2f}M", delta_color="normal" if savings > 0 else "inverse")
    c4.metric("Simple Payback",  f"{pb} yrs" if pb else ">20 yrs")

    # ── EST tier ──────────────────────────────────────────────────────────────
    est = econ["est_tier"]
    if p["K_I"] >= 1000:
        st.warning(f"⚠️ EST tier **{est['tier']}** (>1 MW) — subject to FTC regulatory review.")
    else:
        st.success(
            f"✅ EST tier: **{est['tier']}** — "
            f"Energy **${econ['est_energy_rate']:.3f}/kWh** | "
            f"Capacity **${econ['est_capacity_rate']:.2f}/kW/mo**"
        )

    st.markdown("---")

    # ── Key numbers table (no matplotlib needed) ──────────────────────────────
    st.subheader("Summary")
    st.dataframe(summary_table(econ), use_container_width=True, hide_index=True)

    # ── Value streams table ───────────────────────────────────────────────────
    st.subheader("Annual Value Streams")
    wf = econ["savings_waterfall"].copy()
    wf["est_revenue"]  = wf["est_revenue"].map("${:,.0f}".format)
    wf["bill_saving"]  = wf["bill_saving"].map("${:,.0f}".format)
    wf["avoided_fuel"] = wf["avoided_fuel"].map("${:,.0f}".format)
    wf["total_saving"] = wf["total_saving"].map("${:,.0f}".format)
    wf.columns = ["Year", "EST Revenue", "Bill Saving", "Avoided Fuel", "Total Saving"]
    st.dataframe(wf, use_container_width=True, hide_index=True)

    # ── Year-by-year LCC ─────────────────────────────────────────────────────
    with st.expander("📋 Full Year-by-Year LCC Tables"):
        ch, cd = st.columns(2)
        with ch:
            st.markdown("**Hybrid**")
            st.dataframe(econ["lcc_hybrid"].style.format({
                "capex": "${:,.0f}", "om": "${:,.0f}", "electricity_bill": "${:,.0f}",
                "est_revenue": "${:,.0f}", "avoided_fuel": "${:,.0f}", "net_cost": "${:,.0f}",
            }), use_container_width=True, hide_index=True)
        with cd:
            st.markdown("**Diesel-Only**")
            st.dataframe(econ["lcc_diesel"].style.format({
                "capex": "${:,.0f}", "om": "${:,.0f}",
                "electricity_bill": "${:,.0f}", "net_cost": "${:,.0f}",
            }), use_container_width=True, hide_index=True)

    # ── Charts (lazy — only load matplotlib when user asks) ───────────────────
    st.markdown("---")
    if st.button("📈 Show Charts", key="show_charts"):
        st.session_state["show_charts"] = True

    if st.session_state.get("show_charts"):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from plotting import (plot_npc_comparison, plot_lcc_waterfall,
                               plot_lcc_cost_breakdown, plot_est_sensitivity)

        with st.spinner("Rendering charts…"):
            cl, cr = st.columns(2)
            with cl:
                st.subheader("NPC Comparison")
                st.pyplot(plot_npc_comparison(npc_h, npc_d))
            with cr:
                st.subheader("Cost Breakdown")
                st.pyplot(plot_lcc_cost_breakdown(econ["lcc_hybrid"], econ["lcc_diesel"]))

            st.subheader("Annual Value Streams")
            st.pyplot(plot_lcc_waterfall(econ["savings_waterfall"]))

            st.subheader("EST Revenue vs Regulatory Risk")
            st.pyplot(plot_est_sensitivity(
                K_I=p["K_I"], K_B=p["K_B"],
                est_energy_rate=econ["est_energy_rate"],
                est_capacity_rate=econ["est_capacity_rate"],
                utilisation_rate=p["est_utilisation"],
                eta_B=p["eta_B"], T=p["T"], r=p["r"],
            ))
            plt.close("all")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — RELIABILITY (fully on demand)
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.subheader("📊 Reliability Analysis — Markov Chain Engine")
    st.info(
        "⏱️ This runs the full Markov chain simulation — typically **2–5 minutes** "
        "on the free cloud tier. Tab 1 economics are unaffected."
    )

    if st.button("▶ Run Reliability Analysis", type="secondary"):
        from solar import get_modified_profile
        from reliability import run_both_modes

        with st.spinner("Loading solar resource…"):
            solar_profile, solar_warning, outage_weights = get_modified_profile(params)
            if solar_warning:
                st.warning(solar_warning)

        with st.spinner("Running Markov chain engine… (2–5 min)"):
            rel = run_both_modes(solar_profile, params, outage_weights=outage_weights)
            st.session_state["rel"] = rel
            st.session_state["rel_done"] = True

    if st.session_state.get("rel_done"):
        from plotting import plot_survival_curves, plot_seasonal_performance
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        rel = st.session_state["rel"]
        p   = st.session_state.get("params_run", params)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Hybrid 24h",   f"{rel['X_hybrid'][23]*100:.1f}%"  if len(rel['X_hybrid']) > 23  else "N/A")
        c2.metric("Hybrid 1-wk",  f"{rel['X_hybrid'][167]*100:.1f}%" if len(rel['X_hybrid']) > 167 else "N/A")
        c3.metric("Diesel 24h",   f"{rel['X_diesel'][23]*100:.1f}%"  if len(rel['X_diesel']) > 23  else "N/A")
        adv = (rel['X_hybrid'][23] - rel['X_diesel'][23]) * 100 if len(rel['X_hybrid']) > 23 else 0
        c4.metric("Hybrid Advantage", f"+{adv:.1f}pp")

        st.pyplot(plot_survival_curves(rel["X_hybrid"], rel["X_diesel"],
                                       d_max=p.get("d_max", 168)))
        st.pyplot(plot_seasonal_performance(rel["X_hourly_hybrid"], rel["X_hourly_diesel"],
                                             d_max=p.get("d_max", 168)))
        plt.close("all")

        stats_h = rel["stats_hybrid"]["X"]
        stats_d = rel["stats_diesel"]["X"]
        st.dataframe(pd.DataFrame({
            "Metric":      ["Mean (%)", "Min (%)", "P5 (%)", "P10 (%)", "P90 (%)", "P95 (%)"],
            "Hybrid":      [f"{v*100:.1f}" for v in [stats_h["mean"], stats_h["min"], stats_h["p5"],
                                                      stats_h["p10"], stats_h["p90"], stats_h["p95"]]],
            "Diesel-Only": [f"{v*100:.1f}" for v in [stats_d["mean"], stats_d["min"], stats_d["p5"],
                                                      stats_d["p10"], stats_d["p90"], stats_d["p95"]]],
        }), use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — SENSITIVITY (placeholder)
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.subheader("🌪️ Sensitivity Analysis — Coming in v2")
    st.markdown(
        "A tornado chart showing ±20% perturbation impact on NPC for: "
        "diesel price, EST rates, BESS capex, PV capex, discount rate, FCA escalation, critical load fraction."
    )
    st.dataframe(pd.DataFrame({
        "Variable":   ["Diesel fuel cost", "EST energy rate", "EST capacity rate",
                       "BESS energy capex", "PV capex", "FCA escalation", "Discount rate"],
        "Default":    ["$6.44/gal", "$0.187/kWh", "$20.98/kW/mo",
                       "$165/kWh", "$1,100/kW", "2.0%/yr", "7%"],
        "±20% Range": ["$5.15–$7.73", "$0.150–$0.224", "$16.78–$25.18",
                       "$132–$198", "$880–$1,320", "1.6–2.4%", "5.6–8.4%"],
    }), use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "Methodology: Marqusee, Becker & Ericson (2021) · "
    "Defaults: BL&P (2022), FTC (2023), Ember (2025), NREL (2025) · "
    "EST: FTC Decision June 28 2023 · v1.2 · April 2026"
)
