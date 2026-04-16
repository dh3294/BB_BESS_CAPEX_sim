"""
plotting.py
-----------
All chart builders for the Barbados Microgrid Tool.

NOTE: This implementation uses matplotlib instead of Plotly (spec §2.1).
Plotly is listed in requirements.txt and should be used in production.
The matplotlib charts are drop-in compatible with Streamlit's st.pyplot().
TODO: Replace with Plotly Express calls once plotly is available in the environment.

Chart inventory (spec §7.3):
  1. plot_survival_curves      – Survival probability vs outage duration
  2. plot_seasonal_performance – Survival prob at d_max by outage-start hour
  3. plot_lcc_waterfall        – Annual cost waterfall: diesel vs hybrid
  4. plot_npc_comparison       – Bar chart: Pre-microgrid / Diesel / Hybrid NPC
  5. plot_est_sensitivity      – EST revenue vs regulatory risk haircut
  6. plot_bess_availability    – Survival prob for OA_B variants
"""

from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # non-interactive backend for Streamlit
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ── Colour palette ────────────────────────────────────────────────────────────
COLOUR_HYBRID  = "#1f77b4"    # blue
COLOUR_DIESEL  = "#d62728"    # red
COLOUR_EST     = "#2ca02c"    # green
COLOUR_NEUTRAL = "#7f7f7f"    # grey
COLOUR_WARN    = "#ff7f0e"    # orange

_FIG_W, _FIG_H = 10, 5        # default figure size inches


def _usd_formatter(x, pos):
    """Axis label formatter for dollar millions."""
    return f"${x/1e6:.1f}M"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Survival Probability Curves
# ─────────────────────────────────────────────────────────────────────────────

def plot_survival_curves(
    X_hybrid:  np.ndarray,
    X_diesel:  np.ndarray,
    d_max:     int  = 336,
    x_min_line: float | None = 0.90,
    title:     str  = "Islanded Survival Probability — Barbados Hybrid Microgrid",
) -> plt.Figure:
    """
    Replicates Figures 10–11 of Marqusee et al. (2021).
    X-axis: outage duration (hours).
    Y-axis: survival probability (%).
    """
    durations = np.arange(1, len(X_hybrid) + 1)

    fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))

    ax.plot(durations, X_hybrid * 100, color=COLOUR_HYBRID,
            linewidth=2.0, label="Hybrid (PV + BESS + EDG)")
    ax.plot(durations, X_diesel * 100, color=COLOUR_DIESEL,
            linewidth=2.0, linestyle="--", label="Diesel-only")

    if x_min_line is not None:
        ax.axhline(x_min_line * 100, color=COLOUR_NEUTRAL, linestyle=":",
                   linewidth=1.2, label=f"Min acceptable ({x_min_line*100:.0f}%)")

    # Milestone markers at 24h, 72h, 168h (1 wk), 336h (2 wk)
    milestones = [24, 72, 168, 336]
    for m in milestones:
        if m <= len(durations):
            ax.axvline(m, color=COLOUR_NEUTRAL, linewidth=0.5, alpha=0.4)
            ax.text(m + 1, 2, f"{m}h", fontsize=7, color=COLOUR_NEUTRAL)

    ax.set_xlabel("Outage Duration (hours)", fontsize=11)
    ax.set_ylabel("Survival Probability (%)", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlim(0, d_max)
    ax.set_ylim(-2, 102)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 2. Seasonal Performance (survival prob at d_max by outage-start hour)
# ─────────────────────────────────────────────────────────────────────────────

def plot_seasonal_performance(
    X_hourly_hybrid: np.ndarray,   # (8760,)
    X_hourly_diesel: np.ndarray,   # (8760,)
    d_max: int = 336,
    title: str = "Seasonal Survival Performance (Survival Prob at 2-Week Outage by Start Hour)",
) -> plt.Figure:
    """
    Replicates Figures 13–14 of Marqusee et al. (2021).
    X-axis: hour of year (0–8759).
    Y-axis: survival probability at d_max (%).
    """
    hours = np.arange(8760)

    fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))

    ax.plot(hours, X_hourly_hybrid * 100, color=COLOUR_HYBRID,
            linewidth=0.8, alpha=0.8, label="Hybrid")
    ax.plot(hours, X_hourly_diesel * 100, color=COLOUR_DIESEL,
            linewidth=0.8, alpha=0.8, linestyle="--", label="Diesel-only")

    # Month boundaries (approx)
    month_starts = [0, 744, 1416, 2160, 2880, 3624, 4344, 5088, 5832, 6552, 7296, 8016]
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for ms in month_starts:
        ax.axvline(ms, color=COLOUR_NEUTRAL, linewidth=0.4, alpha=0.3)
    ax.set_xticks(month_starts)
    ax.set_xticklabels(month_labels, fontsize=9)

    # Shade hurricane season Jun–Nov
    ax.axvspan(3624, 8016, alpha=0.06, color=COLOUR_WARN, label="Hurricane season (Jun–Nov)")

    ax.set_xlabel("Month", fontsize=11)
    ax.set_ylabel(f"Survival Probability at {d_max}h (%)", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylim(-2, 102)
    ax.legend(fontsize=9, loc="lower right")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 3. LCC Waterfall — annual savings by value stream
# ─────────────────────────────────────────────────────────────────────────────

def plot_lcc_waterfall(
    savings_df: pd.DataFrame,    # columns: year, est_revenue, bill_saving, avoided_fuel
    title: str = "Annual Value Streams — Hybrid vs Diesel-Only (Undiscounted)",
) -> plt.Figure:
    """
    Replicates Figures 5–9 of Marqusee et al. (2021).
    Stacked bar: year on X-axis, saving components stacked by colour.
    """
    fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))

    years = savings_df["year"].values
    est   = savings_df["est_revenue"].values / 1e3    # $k
    bill  = savings_df["bill_saving"].values  / 1e3
    fuel  = savings_df["avoided_fuel"].values / 1e3

    bars1 = ax.bar(years, est,  label="EST Revenue",         color=COLOUR_EST,     alpha=0.85)
    bars2 = ax.bar(years, bill, bottom=est, label="Bill Savings", color=COLOUR_HYBRID, alpha=0.85)
    bars3 = ax.bar(years, fuel, bottom=est + bill, label="Avoided Diesel Fuel", color=COLOUR_WARN, alpha=0.85)

    ax.set_xlabel("Year", fontsize=11)
    ax.set_ylabel("Annual Savings ($k)", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, axis="y", alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.0f}k"))
    fig.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 4. NPC Comparison Bar Chart
# ─────────────────────────────────────────────────────────────────────────────

def plot_npc_comparison(
    npc_hybrid: float,
    npc_diesel: float,
    title: str = "Net Present Cost Comparison — 20-Year Life Cycle",
) -> plt.Figure:
    """
    Replicates the NPC comparison charts (Tables 8–10) of Marqusee et al. (2021).
    Bar chart: Diesel-only vs Hybrid NPC.
    """
    labels = ["Diesel-Only", "Hybrid (PV+BESS+EDG)"]
    values = [npc_diesel / 1e6, npc_hybrid / 1e6]
    colours = [COLOUR_DIESEL, COLOUR_HYBRID]

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(labels, values, color=colours, alpha=0.85, width=0.5)

    # Value labels on bars
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.02 * max(values),
                f"${val:.2f}M", ha="center", va="bottom", fontsize=11, fontweight="bold")

    # Savings annotation
    savings = (npc_diesel - npc_hybrid) / 1e6
    if savings > 0:
        ax.annotate(
            f"Hybrid saves\n${savings:.2f}M NPC",
            xy=(1, npc_hybrid / 1e6), xytext=(1.35, (npc_diesel + npc_hybrid) / 2e6),
            fontsize=10, color=COLOUR_EST,
            arrowprops=dict(arrowstyle="->", color=COLOUR_EST),
        )

    ax.set_ylabel("Net Present Cost ($M)", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylim(0, max(values) * 1.25)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.1f}M"))
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 5. EST Revenue Sensitivity (regulatory risk haircut)
# ─────────────────────────────────────────────────────────────────────────────

def plot_est_sensitivity(
    K_I: float,
    K_B: float,
    est_energy_rate: float,
    est_capacity_rate: float,
    utilisation_rate: float,
    eta_B: float,
    T: int = 20,
    r: float = 0.07,
    title: str = "EST Revenue NPV vs Regulatory Risk Haircut",
) -> plt.Figure:
    """
    New chart: shows how EST NPV changes as regulatory risk discount is swept 0–100%.
    Helps users understand sensitivity to the FTC review outcome.
    """
    from economics import annual_est_revenue, npv as _npv

    haircuts = np.linspace(0.0, 1.0, 51)
    npvs_total = []
    npvs_cap   = []
    npvs_energy = []

    for hc in haircuts:
        cap_stream    = [annual_est_revenue(K_I, K_B, 0.0,            est_capacity_rate, 0.0,
                                            eta_B, 0.0, yr, True, hc, above_1mw=(K_I>=1000))
                         for yr in range(T + 1)]
        energy_stream = [annual_est_revenue(K_I, K_B, est_energy_rate, 0.0,              utilisation_rate,
                                            eta_B, 0.0, yr, True, hc, above_1mw=(K_I>=1000))
                         for yr in range(T + 1)]
        total_stream  = [annual_est_revenue(K_I, K_B, est_energy_rate, est_capacity_rate, utilisation_rate,
                                            eta_B, 0.0, yr, True, hc, above_1mw=(K_I>=1000))
                         for yr in range(T + 1)]

        npvs_cap.append(_npv(np.array(cap_stream),    r) / 1e6)
        npvs_energy.append(_npv(np.array(energy_stream), r) / 1e6)
        npvs_total.append(_npv(np.array(total_stream),  r) / 1e6)

    fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))
    ax.fill_between(haircuts * 100, npvs_total, alpha=0.15, color=COLOUR_EST)
    ax.plot(haircuts * 100, npvs_total,  color=COLOUR_EST,     linewidth=2, label="Total EST NPV")
    ax.plot(haircuts * 100, npvs_cap,    color=COLOUR_HYBRID,  linewidth=1.5, linestyle="--",
            label="Capacity payment only")
    ax.plot(haircuts * 100, npvs_energy, color=COLOUR_WARN,    linewidth=1.5, linestyle=":",
            label="Energy payment only")

    ax.set_xlabel("Regulatory Risk Haircut (%)", fontsize=11)
    ax.set_ylabel("EST Revenue NPV ($M)", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.2f}M"))
    fig.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 6. BESS Availability Sensitivity (Figure 16 replica)
# ─────────────────────────────────────────────────────────────────────────────

def plot_bess_availability_sensitivity(
    solar_profile: np.ndarray,
    base_params: dict,
    oa_values: list[float] | None = None,
    title: str = "Survival Probability Sensitivity to BESS Availability (OA_B)",
) -> plt.Figure:
    """
    Replicates Figure 16 of Marqusee et al. (2021).
    Shows how BESS operational availability affects the survival curve.
    """
    from reliability import run_reliability
    from solar import build_outage_weights

    if oa_values is None:
        oa_values = [0.95, 0.97, 1.00]

    colours = [COLOUR_DIESEL, COLOUR_NEUTRAL, COLOUR_HYBRID]
    outage_weights = build_outage_weights(
        mode="hurricane" if base_params.get("hurricane_weighting", True) else "uniform"
    )

    fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))

    d_max = int(base_params.get("d_max", 336))
    durations = np.arange(1, d_max + 1)

    for oa, colour in zip(oa_values, colours):
        p = base_params.copy()
        p["OA_B"] = oa
        result = run_reliability(solar_profile, p, mode="hybrid",
                                 outage_weights=outage_weights)
        ax.plot(durations, result["X"] * 100, color=colour, linewidth=1.8,
                label=f"OA_B = {oa*100:.0f}%")

    ax.set_xlabel("Outage Duration (hours)", fontsize=11)
    ax.set_ylabel("Survival Probability (%)", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.set_ylim(-2, 102)
    ax.set_xlim(0, d_max)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 7. Sensitivity Tornado Chart — Tab 3 placeholder
# ─────────────────────────────────────────────────────────────────────────────

def plot_sensitivity_tornado_placeholder() -> plt.Figure:
    """
    Placeholder for the Tab 3 Sensitivity Tornado Chart.
    Will show ±20% perturbation of each key input on NPC.
    Coming in v2.
    """
    fig, ax = plt.subplots(figsize=(_FIG_W, 5))
    ax.set_visible(False)

    fig.text(0.5, 0.65, "Sensitivity Tornado Chart", ha="center", va="center",
             fontsize=22, fontweight="bold", color="#555555")
    fig.text(0.5, 0.50, "Coming in v2", ha="center", va="center",
             fontsize=16, color=COLOUR_WARN,
             bbox=dict(boxstyle="round,pad=0.6", facecolor="#FFF3CD",
                       edgecolor=COLOUR_WARN, linewidth=2))
    fig.text(0.5, 0.35,
             "This chart will show the impact of ±20% perturbation\n"
             "in each key input variable on Net Present Cost (NPC).",
             ha="center", va="center", fontsize=11, color="#777777")

    fig.patch.set_facecolor("#FAFAFA")
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 8. LCC stacked cost breakdown
# ─────────────────────────────────────────────────────────────────────────────

def plot_lcc_cost_breakdown(
    lcc_hybrid:  pd.DataFrame,
    lcc_diesel:  pd.DataFrame,
    title: str = "Life Cycle Cost Breakdown — 20-Year Discounted",
) -> plt.Figure:
    """
    Side-by-side stacked bars for hybrid vs diesel cost categories.
    """
    categories = ["Capital", "O&M", "Electricity Bill", "EST Revenue (credit)"]

    # Sum over all years for display (note: not discounted here — use for quick read)
    def _sum(df, col):
        return df[col].sum() / 1e6

    hybrid_vals = [
        _sum(lcc_hybrid, "capex"),
        _sum(lcc_hybrid, "om"),
        _sum(lcc_hybrid, "electricity_bill"),
        -_sum(lcc_hybrid, "est_revenue"),   # est_revenue already negative in df
    ]
    diesel_vals = [
        _sum(lcc_diesel, "capex"),
        _sum(lcc_diesel, "om"),
        _sum(lcc_diesel, "electricity_bill"),
        0.0,
    ]

    colours = [COLOUR_DIESEL, COLOUR_WARN, COLOUR_NEUTRAL, COLOUR_EST]
    x = np.array([0.0, 1.0])
    width = 0.55

    fig, ax = plt.subplots(figsize=(8, 5))
    bottoms = np.zeros(2)

    for cat, colour, h_val, d_val in zip(categories, colours, hybrid_vals, diesel_vals):
        vals = np.array([d_val, h_val])
        ax.bar(x, vals, width=width, bottom=bottoms, label=cat, color=colour, alpha=0.85)
        bottoms += vals

    ax.set_xticks(x)
    ax.set_xticklabels(["Diesel-Only", "Hybrid (PV+BESS+EDG)"], fontsize=11)
    ax.set_ylabel("Undiscounted 20-Year Total ($M)", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.legend(fontsize=10, loc="upper right")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.1f}M"))
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    return fig
