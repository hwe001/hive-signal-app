#!/usr/bin/env python3
"""
HIVE + QQQ + SOXS + HIVE-Only Trading Signal Dashboard.
Streamlit Community Cloud entry point.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

from hive_qqq_strategy import (
    BTC_TREND_LOOKBACK,
    HIVE_LOOKBACK,
    QQQ_TREND_LOOKBACK,
    VIX_CALM,
    VIX_CAUTION,
    VIX_DANGER,
    classify_signal as classify_hive_qqq,
)
from hive_only_strategy import classify_signal as classify_hive_only

# ── SOXS constants ────────────────────────────────────────────────────────────
SOXS_HIGH_LOOKBACK    = 20
QQQ_MA_SOXS_LOOKBACK  = 20
SOXS_VIX_CAUTION      = 35.0
SOXS_VIX_DANGER       = 45.0
SOXS_VIX_EMERGENCY    = 55.0
SOXS_NORMAL_ALLOC     = 0.50
SOXS_CAUTION_ALLOC    = 0.25
SOXS_DANGER_ALLOC     = 0.15
SOXS_EMERGENCY_ALLOC  = 0.00

# ── HIVE-only VIX/RSI thresholds (different scale from HIVE+QQQ) ────────────────
HO_VIX_CALM      = 18.0
HO_VIX_CAUTION   = 28.0
HO_VIX_ELEVATED  = 38.0
HO_VIX_DANGER    = 50.0
HO_RSI_OB        = 72.0
HO_RSI_OS        = 28.0

# ── Colour palettes ───────────────────────────────────────────────────────────
HIVE_REGIME_COLORS = {
    "bull":                 "rgba(16,185,129,0.15)",
    "caution":              "rgba(234,179,8,0.13)",
    "btc_bull_qqq_soft":    "rgba(251,191,36,0.10)",
    "btc_bear":             "rgba(239,68,68,0.13)",
    "btc_bear_vix_elevated":"rgba(220,38,38,0.18)",
    "danger":               "rgba(127,29,29,0.25)",
}
HIVE_HERO_COLORS = {
    "bull":                 "#10b981",
    "caution":              "#f59e0b",
    "btc_bull_qqq_soft":    "#f59e0b",
    "btc_bear":             "#ef4444",
    "btc_bear_vix_elevated":"#dc2626",
    "danger":               "#7f1d1d",
}

SOXS_REGIME_COLORS = {
    "normal":    "rgba(16,185,129,0.13)",
    "qqq_soft":  "rgba(251,191,36,0.10)",
    "soxs_spike":"rgba(239,68,68,0.13)",
    "caution":   "rgba(249,115,22,0.13)",
    "danger":    "rgba(220,38,38,0.18)",
    "emergency": "rgba(127,29,29,0.25)",
}
SOXS_HERO_COLORS = {
    "normal":    "#10b981",
    "qqq_soft":  "#f59e0b",
    "soxs_spike":"#ef4444",
    "caution":   "#f97316",
    "danger":    "#dc2626",
    "emergency": "#7f1d1d",
}

HO_REGIME_COLORS = {
    "bull_strong":      "rgba(16,185,129,0.18)",
    "bull":             "rgba(34,197,94,0.13)",
    "bull_cautious":    "rgba(234,179,8,0.13)",
    "btc_bull_qqq_soft":"rgba(251,191,36,0.10)",
    "btc_bear_qqq_firm":"rgba(107,114,128,0.08)",
    "bear":             "rgba(239,68,68,0.15)",
    "bear_oversold":    "rgba(249,115,22,0.13)",
    "bear_panic":       "rgba(107,114,128,0.08)",
    "danger":           "rgba(127,29,29,0.25)",
}
HO_HERO_COLORS = {
    "bull_strong":      "#10b981",
    "bull":             "#34d399",
    "bull_cautious":    "#fbbf24",
    "btc_bull_qqq_soft":"#f59e0b",
    "btc_bear_qqq_firm":"#9ca3af",
    "bear":             "#ef4444",
    "bear_oversold":    "#f97316",
    "bear_panic":       "#9ca3af",
    "danger":           "#6b7280",
}

# ── Page setup ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Trading Signal Dashboard",
    page_icon="\U0001f4ca",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.hero-card { border-radius:12px; padding:18px 22px; margin-bottom:14px; }
.hero-regime {
    font-size:0.75em; font-weight:700; opacity:0.75;
    text-transform:uppercase; letter-spacing:0.12em; margin-bottom:4px;
}
.hero-action { font-size:1.4em; font-weight:800; margin-bottom:6px; line-height:1.2; }
.hero-alloc  { font-size:0.95em; font-weight:600; opacity:0.88; margin-bottom:8px; }
.hero-reason { font-size:0.85em; opacity:0.80; line-height:1.55; }
.badge {
    display:inline-block; border-radius:5px;
    padding:2px 9px; font-size:0.76em; font-weight:700;
    margin:2px 3px 2px 0;
}
.bg { background:rgba(16,185,129,0.18); color:#10b981; border:1px solid rgba(16,185,129,0.35); }
.br { background:rgba(239,68,68,0.18);  color:#ef4444; border:1px solid rgba(239,68,68,0.35); }
.ba { background:rgba(245,158,11,0.18); color:#f59e0b; border:1px solid rgba(245,158,11,0.35); }
.bx { background:rgba(107,114,128,0.18);color:#9ca3af; border:1px solid rgba(107,114,128,0.35); }
.ts { font-size:0.72em; color:#6b7280; margin-bottom:10px; }
</style>
""", unsafe_allow_html=True)


# ── Utilities ─────────────────────────────────────────────────────────────────
def get_secret(name: str, default: str = "") -> str:
    try:
        v = st.secrets.get(name, default)
        return v if v else default
    except Exception:
        return os.getenv(name, default) or default


def password_gate() -> bool:
    pw = get_secret("SIGNAL_APP_PASSWORD")
    if not pw:
        return True
    entered = st.sidebar.text_input("Dashboard password", type="password")
    if entered == pw:
        return True
    if entered:
        st.sidebar.error("Incorrect password")
    st.info("Enter the dashboard password in the sidebar to access the signals.")
    return False


def badge(label: str, cls: str) -> str:
    return f'<span class="badge b{cls}">{label}</span>'


def hero_card(regime: str, action: str, alloc_line: str, reason: str, color: str) -> None:
    st.markdown(
        f'<div class="hero-card" style="background:{color}1a; border:1.5px solid {color}44;">'
        f'<div class="hero-regime">{regime.replace("_"," ").upper()}</div>'
        f'<div class="hero-action" style="color:{color};">{action}</div>'
        f'<div class="hero-alloc">{alloc_line}</div>'
        f'<div class="hero-reason">{reason}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _5d_ret(series: pd.Series) -> str:
    n = min(6, len(series) - 1)
    r = series.iloc[-1] / series.iloc[-1 - n] - 1
    return f"{r:+.1%}"


# ── Data fetching ─────────────────────────────────────────────────────────────
def _fetch_tickers(syms: dict[str, str], period: str) -> dict[str, pd.Series]:
    frames: dict[str, pd.Series] = {}
    for col, sym in syms.items():
        for attempt in range(3):
            try:
                hist = yf.Ticker(sym).history(period=period, auto_adjust=True)
                if not hist.empty:
                    frames[col] = hist["Close"].rename(col)
                    break
            except Exception:
                time.sleep(1 + attempt)
        if col not in frames:
            st.error(f"Could not fetch {sym}. Try refreshing.")
            st.stop()
    return frames


@st.cache_data(ttl=300)
def build_hive_data(period: str = "1y") -> pd.DataFrame:
    frames = _fetch_tickers({"HIVE":"HIVE","BTC":"BTC-USD","QQQ":"QQQ","VIX":"^VIX"}, period)
    df = pd.concat(frames.values(), axis=1).sort_index().ffill().dropna()
    df["HIVE_MA20"] = df["HIVE"].rolling(HIVE_LOOKBACK).mean()
    df["BTC_MA20"]  = df["BTC"].rolling(BTC_TREND_LOOKBACK).mean()
    df["QQQ_MA50"]  = df["QQQ"].rolling(QQQ_TREND_LOOKBACK).mean()
    return df.dropna()


@st.cache_data(ttl=300)
def build_soxs_data(period: str = "1y") -> pd.DataFrame:
    frames = _fetch_tickers({"QQQ":"QQQ","SOXS":"SOXS","VIX":"^VIX"}, period)
    df = pd.concat(frames.values(), axis=1).sort_index().ffill().dropna()
    df["QQQ_MA20"]    = df["QQQ"].rolling(20).mean()
    df["SOXS_MA5"]    = df["SOXS"].rolling(5).mean()
    df["SOXS_MA20"]   = df["SOXS"].rolling(20).mean()
    df["SOXS_HIGH20"] = df["SOXS"].rolling(SOXS_HIGH_LOOKBACK).max()
    df["SOXS_PULL"]   = df["SOXS"] / df["SOXS_HIGH20"] - 1.0
    delta = df["QQQ"].diff()
    gain  = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    df["QQQ_RSI14"] = 100 - 100 / (1 + gain / loss.replace(0, 1e-10))
    return df.dropna()


@st.cache_data(ttl=300)
def build_hive_only_data(period: str = "1y") -> pd.DataFrame:
    frames = _fetch_tickers({"HIVE":"HIVE","BTC":"BTC-USD","QQQ":"QQQ","VIX":"^VIX"}, period)
    df = pd.concat(frames.values(), axis=1).sort_index().ffill().dropna()
    df["HIVE_MA5"]  = df["HIVE"].rolling(5).mean()
    df["HIVE_MA20"] = df["HIVE"].rolling(20).mean()
    df["BTC_MA20"]  = df["BTC"].rolling(20).mean()
    df["QQQ_MA50"]  = df["QQQ"].rolling(50).mean()
    delta = df["HIVE"].diff()
    gain  = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    df["HIVE_RSI14"] = 100 - 100 / (1 + gain / loss.replace(0, 1e-10))
    return df.dropna()


# ── SOXS signal classifier ─────────────────────────────────────────────────────
def classify_soxs(row: pd.Series) -> dict:
    vix   = float(row["VIX"])
    qqq   = float(row["QQQ"])
    qma   = float(row["QQQ_MA20"])
    soxs  = float(row["SOXS"])
    sma5  = float(row["SOXS_MA5"])
    sh20  = float(row["SOXS_HIGH20"])
    pull  = float(row["SOXS_PULL"])
    rsi14 = float(row.get("QQQ_RSI14", 50))

    at_high     = soxs >= sh20 * 0.98
    below_ma    = qqq < qma
    breaking_dn = soxs < sma5 and pull <= -0.08
    base = {"qqq":qqq,"qqq_ma20":qma,"soxs":soxs,"soxs_high20":sh20,"soxs_pull":pull,"vix":vix}

    if vix >= SOXS_VIX_EMERGENCY:
        return {**base,"regime":"emergency","action":"COVER / FLATTEN SOXS SHORT","confidence":"high",
                "target_short_alloc":SOXS_EMERGENCY_ALLOC,
                "reason":"VIX in crisis territory — SOXS short tail-risk dominates. Flatten first."}
    if vix >= SOXS_VIX_DANGER:
        return {**base,"regime":"danger","action":"REDUCE SOXS SHORT / DO NOT ADD","confidence":"high",
                "target_short_alloc":SOXS_DANGER_ALLOC,
                "reason":"VIX very elevated. Reduce short exposure and wait for vol to fade."}
    if vix >= SOXS_VIX_CAUTION:
        return {**base,"regime":"caution","action":"HOLD SMALL SHORT; DO NOT ADD","confidence":"medium",
                "target_short_alloc":SOXS_CAUTION_ALLOC,
                "reason":"VIX elevated. Hold a reduced short; no new additions until VIX cools."}
    if at_high:
        if breaking_dn and not below_ma:
            return {**base,"regime":"soxs_spike","action":"START / ADD SMALL SOXS SHORT","confidence":"medium",
                    "target_short_alloc":SOXS_CAUTION_ALLOC,
                    "reason":"SOXS spiked but is rolling over while QQQ holds. Early entry window open."}
        return {**base,"regime":"soxs_spike","action":"WAIT — DO NOT SHORT VERTICAL SPIKE","confidence":"high",
                "target_short_alloc":SOXS_CAUTION_ALLOC,
                "reason":"SOXS near its 20-day high. Wait for a confirmed pullback before shorting."}
    if below_ma:
        return {**base,"regime":"qqq_soft","action":"HOLD OR REDUCE; DO NOT ADD","confidence":"medium",
                "target_short_alloc":SOXS_CAUTION_ALLOC,
                "reason":"QQQ below its 20-day MA. Avoid increasing SOXS short until QQQ reclaims trend."}
    note = " QQQ short-term overbought — scale in slowly." if rsi14 > 75 else ""
    return {**base,"regime":"normal","action":"SHORT / ADD SOXS TOWARD 50% TARGET","confidence":"medium",
            "target_short_alloc":SOXS_NORMAL_ALLOC,
            "reason":f"VIX calm, QQQ above MA20, SOXS not at panic high — good risk/reward.{note}"}


# ── Charts ────────────────────────────────────────────────────────────────────
def _regime_bands(fig: go.Figure, series: pd.Series, colors: dict, row: int = 1) -> None:
    if series.empty:
        return
    prev_reg = series.iloc[0]
    start_ts = series.index[0]
    for ts, reg in series.items():
        if reg != prev_reg:
            c = colors.get(prev_reg, "rgba(128,128,128,0.05)")
            fig.add_vrect(x0=start_ts, x1=ts, fillcolor=c, opacity=1,
                          layer="below", line_width=0, row=row, col=1)
            start_ts, prev_reg = ts, reg
    c = colors.get(prev_reg, "rgba(128,128,128,0.05)")
    fig.add_vrect(x0=start_ts, x1=series.index[-1], fillcolor=c, opacity=1,
                  layer="below", line_width=0, row=row, col=1)


_LAYOUT = dict(
    height=520, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#d1d5db", size=11),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left",
                x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
    margin=dict(l=0, r=10, t=30, b=0),
    hovermode="x unified",
)
_XAX = dict(showgrid=False, zeroline=False, color="#6b7280")
_YAX = dict(showgrid=True, gridcolor="rgba(107,114,128,0.10)", zeroline=False, color="#6b7280")


def make_hive_chart(df: pd.DataFrame, regimes: pd.Series) -> go.Figure:
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.52, 0.28, 0.20], vertical_spacing=0.03)
    _regime_bands(fig, regimes, HIVE_REGIME_COLORS)
    fig.add_trace(go.Scatter(x=df.index, y=df["HIVE"], name="HIVE",
                             line=dict(color="#60a5fa", width=1.6)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["HIVE_MA20"], name="HIVE MA20",
                             line=dict(color="#fbbf24", width=1, dash="dot")), row=1, col=1)
    transitions = regimes[regimes != regimes.shift(1)]
    for ts, reg in transitions.items():
        if ts not in df.index:
            continue
        color = HIVE_HERO_COLORS.get(reg, "#9ca3af")
        sym = "triangle-up" if reg == "bull" else ("triangle-down" if "bear" in reg or reg == "danger" else "circle")
        fig.add_trace(go.Scatter(x=[ts], y=[df.loc[ts, "HIVE"]], mode="markers", showlegend=False,
                                 marker=dict(color=color, size=8, symbol=sym,
                                             line=dict(color="white", width=1))), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["QQQ"], name="QQQ",
                             line=dict(color="#a78bfa", width=1.6)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["QQQ_MA50"], name="QQQ MA50",
                             line=dict(color="#fbbf24", width=1, dash="dot")), row=2, col=1)
    for y0, y1, c in [(0,VIX_CALM,"rgba(16,185,129,0.07)"),(VIX_CALM,VIX_CAUTION,"rgba(251,191,36,0.07)"),
                      (VIX_CAUTION,VIX_DANGER,"rgba(249,115,22,0.08)"),(VIX_DANGER,120,"rgba(220,38,38,0.10)")]:
        fig.add_hrect(y0=y0, y1=y1, fillcolor=c, layer="below", line_width=0, row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["VIX"], name="VIX",
                             line=dict(color="#f87171", width=1.5)), row=3, col=1)
    fig.update_layout(**_LAYOUT)
    fig.update_xaxes(**_XAX)
    fig.update_yaxes(**_YAX)
    fig.update_yaxes(title_text="HIVE ($)", row=1, col=1, title_font=dict(size=10))
    fig.update_yaxes(title_text="QQQ ($)", row=2, col=1, title_font=dict(size=10))
    fig.update_yaxes(title_text="VIX",     row=3, col=1, title_font=dict(size=10))
    return fig


def make_soxs_chart(df: pd.DataFrame, regimes: pd.Series) -> go.Figure:
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.42, 0.38, 0.20], vertical_spacing=0.03)
    _regime_bands(fig, regimes, SOXS_REGIME_COLORS)
    fig.add_trace(go.Scatter(x=df.index, y=df["QQQ"], name="QQQ",
                             line=dict(color="#a78bfa", width=1.6)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["QQQ_MA20"], name="QQQ MA20",
                             line=dict(color="#fbbf24", width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SOXS_HIGH20"], name="SOXS High20",
                             line=dict(color="#f87171", width=1, dash="dash")), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SOXS"], name="SOXS",
                             line=dict(color="#fb923c", width=1.6)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SOXS_MA20"], name="SOXS MA20",
                             line=dict(color="#fbbf24", width=1, dash="dot")), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["SOXS_MA5"], name="SOXS MA5",
                             line=dict(color="#4ade80", width=1, dash="dot")), row=2, col=1)
    for y0, y1, c in [(0,SOXS_VIX_CAUTION,"rgba(16,185,129,0.07)"),(SOXS_VIX_CAUTION,SOXS_VIX_DANGER,"rgba(251,191,36,0.07)"),
                      (SOXS_VIX_DANGER,SOXS_VIX_EMERGENCY,"rgba(249,115,22,0.08)"),(SOXS_VIX_EMERGENCY,120,"rgba(220,38,38,0.10)")]:
        fig.add_hrect(y0=y0, y1=y1, fillcolor=c, layer="below", line_width=0, row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["VIX"], name="VIX",
                             line=dict(color="#f87171", width=1.5)), row=3, col=1)
    fig.update_layout(**_LAYOUT)
    fig.update_xaxes(**_XAX)
    fig.update_yaxes(**_YAX)
    fig.update_yaxes(title_text="QQQ ($)",  row=1, col=1, title_font=dict(size=10))
    fig.update_yaxes(title_text="SOXS ($)", row=2, col=1, title_font=dict(size=10))
    fig.update_yaxes(title_text="VIX",      row=3, col=1, title_font=dict(size=10))
    return fig


def make_hive_only_chart(df: pd.DataFrame, regimes: pd.Series) -> go.Figure:
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.52, 0.28, 0.20], vertical_spacing=0.03)
    _regime_bands(fig, regimes, HO_REGIME_COLORS)

    # Row 1: HIVE price + MA5 + MA20 + regime transition markers
    fig.add_trace(go.Scatter(x=df.index, y=df["HIVE"], name="HIVE",
                             line=dict(color="#60a5fa", width=1.6)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["HIVE_MA20"], name="MA20",
                             line=dict(color="#fbbf24", width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["HIVE_MA5"], name="MA5",
                             line=dict(color="#4ade80", width=1, dash="dot")), row=1, col=1)
    transitions = regimes[regimes != regimes.shift(1)]
    for ts, reg in transitions.items():
        if ts not in df.index:
            continue
        color = HO_HERO_COLORS.get(reg, "#9ca3af")
        is_long  = reg in ("bull_strong", "bull", "bull_cautious", "btc_bull_qqq_soft")
        is_short = reg in ("bear", "bear_oversold")
        sym = "triangle-up" if is_long else ("triangle-down" if is_short else "circle")
        fig.add_trace(go.Scatter(x=[ts], y=[df.loc[ts, "HIVE"]], mode="markers", showlegend=False,
                                 marker=dict(color=color, size=9, symbol=sym,
                                             line=dict(color="white", width=1))), row=1, col=1)

    # Row 2: RSI-14 with overbought / oversold bands
    fig.add_hrect(y0=HO_RSI_OB, y1=100, fillcolor="rgba(239,68,68,0.07)",  layer="below", line_width=0, row=2, col=1)
    fig.add_hrect(y0=0, y1=HO_RSI_OS,  fillcolor="rgba(16,185,129,0.07)", layer="below", line_width=0, row=2, col=1)
    fig.add_hline(y=HO_RSI_OB, line=dict(color="#ef4444", width=1, dash="dot"), row=2, col=1)
    fig.add_hline(y=HO_RSI_OS, line=dict(color="#10b981", width=1, dash="dot"), row=2, col=1)
    fig.add_hline(y=50,        line=dict(color="#6b7280", width=0.5, dash="dot"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["HIVE_RSI14"], name="RSI 14",
                             line=dict(color="#c084fc", width=1.5)), row=2, col=1)

    # Row 3: VIX with HIVE-only thresholds
    for y0, y1, c in [(0,HO_VIX_CALM,"rgba(16,185,129,0.07)"),(HO_VIX_CALM,HO_VIX_CAUTION,"rgba(251,191,36,0.07)"),
                      (HO_VIX_CAUTION,HO_VIX_ELEVATED,"rgba(249,115,22,0.08)"),(HO_VIX_ELEVATED,120,"rgba(220,38,38,0.10)")]:
        fig.add_hrect(y0=y0, y1=y1, fillcolor=c, layer="below", line_width=0, row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["VIX"], name="VIX",
                             line=dict(color="#f87171", width=1.5)), row=3, col=1)

    fig.update_layout(**_LAYOUT)
    fig.update_xaxes(**_XAX)
    fig.update_yaxes(**_YAX)
    fig.update_yaxes(title_text="HIVE ($)", row=1, col=1, title_font=dict(size=10))
    fig.update_yaxes(title_text="RSI 14",   row=2, col=1, title_font=dict(size=10), range=[0, 100])
    fig.update_yaxes(title_text="VIX",      row=3, col=1, title_font=dict(size=10))
    return fig


# ── AI briefs ──────────────────────────────────────────────────────────────────
def generate_ai_brief(prompt: str) -> str:
    api_key = get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        return "Add `ANTHROPIC_API_KEY` to Streamlit secrets to enable the AI brief."
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        with client.messages.stream(
            model="claude-opus-4-8",
            max_tokens=600,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            msg = stream.get_final_message()
        return "\n\n".join(
            b.text for b in msg.content if hasattr(b, "text") and b.type == "text"
        )
    except Exception as exc:
        return f"AI brief unavailable: {exc}"


def _hive_prompt(sig: dict, df: pd.DataFrame) -> str:
    return (
        "You are a concise trading signal analyst for a private dashboard.\n"
        "Strategy: QQQ 50% core + HIVE 0-30% satellite (BTC mining / AI theme).\n"
        "Write a brief in exactly 5 short paragraphs:\n"
        "1) BTC/HIVE context  2) Current signal  3) QQQ macro  4) Risk watch  5) What would change the signal.\n"
        "No financial advice. Be direct.\n\n"
        f"Regime: {sig['regime']}\n"
        f"HIVE action: {sig['hive_action']}  ({sig['hive_target_alloc']:.0%})\n"
        f"QQQ action: {sig['qqq_action']}  ({sig['qqq_target_alloc']:.0%})\n"
        f"Options: {sig['options_action']}\n"
        f"Confidence: {sig['confidence']}  |  {sig['reason']}\n"
        f"BTC: ${sig['btc']:,.0f}  MA20: ${sig['btc_ma20']:,.0f}  Above: {sig['btc_above_ma20']}\n"
        f"HIVE: ${sig['hive']:.3f}  MA20: ${sig['hive_ma20']:.3f}  Above: {sig['hive_above_ma20']}\n"
        f"QQQ: ${sig['qqq']:.2f}  MA50: ${sig['qqq_ma50']:.2f}  Above: {sig['qqq_above_ma50']}\n"
        f"VIX: {sig['vix']:.2f}\n"
        f"5d HIVE: {_5d_ret(df['HIVE'])}  5d QQQ: {_5d_ret(df['QQQ'])}"
    )


def _soxs_prompt(sig: dict, df: pd.DataFrame) -> str:
    return (
        "You are a concise trading signal analyst for a private dashboard.\n"
        "Strategy: QQQ 40% core + short SOXS (3x inverse semis) 50% overlay.\n"
        "Write a brief in exactly 4 short paragraphs:\n"
        "1) QQQ/semis context  2) Current SOXS signal  3) VIX risk gauge  4) What would change the signal.\n"
        "No financial advice. Be direct.\n\n"
        f"Regime: {sig['regime']}\n"
        f"Action: {sig['action']}\n"
        f"Target SOXS short: {sig['target_short_alloc']:.0%}  Confidence: {sig['confidence']}\n"
        f"Reason: {sig['reason']}\n"
        f"QQQ: ${sig['qqq']:.2f}  MA20: ${sig['qqq_ma20']:.2f}\n"
        f"SOXS: ${sig['soxs']:.3f}  20d high: ${sig['soxs_high20']:.3f}  Pullback: {sig['soxs_pull']:+.1%}\n"
        f"VIX: {sig['vix']:.2f}\n"
        f"5d QQQ: {_5d_ret(df['QQQ'])}  5d SOXS: {_5d_ret(df['SOXS'])}"
    )


def _hive_only_prompt(sig: dict, df: pd.DataFrame) -> str:
    alloc = sig["target_alloc"]
    direction = "LONG" if alloc > 0 else ("SHORT" if alloc < 0 else "FLAT")
    return (
        "You are a concise trading signal analyst for a private dashboard.\n"
        "Strategy: HIVE-only account — can go long (up to 100%) or short (up to 55%) HIVE equity.\n"
        "BTC 20-day MA is the primary on/off switch. QQQ 50-day MA, VIX, and RSI-14 fine-tune size.\n"
        "Write a brief in exactly 4 short paragraphs:\n"
        "1) BTC/HIVE setup  2) Current signal and sizing rationale  3) Key risks  4) What would change the signal.\n"
        "No financial advice. Be direct.\n\n"
        f"Regime: {sig['regime']}\n"
        f"Action: {sig['action']}  ({direction} {abs(alloc):.0%})\n"
        f"Reason: {sig['reason']}\n"
        f"HIVE: ${sig['hive']:.3f}  MA5: ${sig['hive_ma5']:.3f}  MA20: ${sig['hive_ma20']:.3f}\n"
        f"RSI-14: {sig['hive_rsi14']:.1f}  HIVE above MA20: {sig['hive_above_ma20']}\n"
        f"BTC: ${sig['btc']:,.0f}  MA20: ${sig['btc_ma20']:,.0f}  Above: {sig['btc_above_ma20']}\n"
        f"QQQ: ${sig['qqq']:.2f}  MA50: ${sig['qqq_ma50']:.2f}  Above: {sig['qqq_above_ma50']}\n"
        f"VIX: {sig['vix']:.2f}\n"
        f"5d HIVE: {_5d_ret(df['HIVE'])}"
    )


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    st.sidebar.title("\U0001f4ca Signal Dashboard")
    st.sidebar.caption("HIVE + QQQ + SOXS + HIVE-Only")

    if not password_gate():
        return

    period = st.sidebar.selectbox("History period", ["3mo", "6mo", "1y", "2y"], index=2)
    st.sidebar.markdown("---")
    now_et = datetime.now(ZoneInfo("America/New_York"))
    st.sidebar.caption(f"Data: Yahoo Finance\n\n{now_et.strftime('%Y-%m-%d %H:%M ET')}")
    st.sidebar.caption("Signals are informational only — not financial advice.")

    tab_hive, tab_soxs, tab_ho = st.tabs([
        "\U0001f41d HIVE + QQQ Core",
        "\U0001f4c9 SOXS Short Overlay",
        "⚡ HIVE Only (Long/Short)",
    ])

    # ── HIVE + QQQ tab ────────────────────────────────────────────────────────
    with tab_hive:
        with st.spinner("Loading HIVE, BTC, QQQ, VIX data…"):
            df_h = build_hive_data(period)
        regimes_h = df_h.apply(classify_hive_qqq, axis=1).apply(lambda d: d["regime"])
        sig_h = classify_hive_qqq(df_h.iloc[-1])
        hcolor = HIVE_HERO_COLORS.get(sig_h["regime"], "#9ca3af")
        st.markdown(f'<div class="ts">Last bar: {df_h.index[-1].strftime("%Y-%m-%d %a")} &nbsp;·&nbsp; Cache refreshes every 5 min</div>',
                    unsafe_allow_html=True)
        alloc_h = f"QQQ {sig_h['qqq_target_alloc']:.0%}  ·  HIVE {sig_h['hive_target_alloc']:.0%}  ·  Cash {sig_h['target_cash_alloc']:.0%}"
        hero_card(sig_h["regime"], sig_h["hive_action"], alloc_h, sig_h["reason"], hcolor)
        with st.expander(f"QQQ action: {sig_h['qqq_action']}"):
            st.caption(f"QQQ target alloc: {sig_h['qqq_target_alloc']:.0%}")
        badges_h = [
            badge(f"BTC {'↑' if sig_h['btc_above_ma20'] else '↓'} MA20", "g" if sig_h["btc_above_ma20"] else "r"),
            badge(f"QQQ {'↑' if sig_h['qqq_above_ma50'] else '↓'} MA50", "g" if sig_h["qqq_above_ma50"] else "r"),
            badge(f"HIVE {'↑' if sig_h['hive_above_ma20'] else '↓'} MA20", "g" if sig_h["hive_above_ma20"] else "r"),
            badge(f"VIX {sig_h['vix']:.1f}", "g" if sig_h["vix"] < VIX_CALM else ("a" if sig_h["vix"] < VIX_CAUTION else ("r" if sig_h["vix"] < VIX_DANGER else "x"))),
            badge(f"Conf: {sig_h['confidence'].upper()}", "g" if sig_h["confidence"] == "high" else "a"),
        ]
        st.markdown("&nbsp;".join(badges_h), unsafe_allow_html=True)
        with st.expander("Options advisory"):
            st.info(f"**{sig_h['options_action']}**\n\n{sig_h['options_detail']}")
        st.plotly_chart(make_hive_chart(df_h, regimes_h), use_container_width=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("HIVE", f"${sig_h['hive']:.3f}", _5d_ret(df_h["HIVE"]) + " 5d")
        c2.metric("QQQ",  f"${sig_h['qqq']:.2f}",  _5d_ret(df_h["QQQ"]) + " 5d")
        c3.metric("BTC",  f"${sig_h['btc']:,.0f}",  _5d_ret(df_h["BTC"]) + " 5d")
        c4.metric("VIX",  f"{sig_h['vix']:.2f}")
        st.markdown("---")
        if st.button("\U0001f916 Generate AI Brief", key="ai_hive"):
            with st.spinner("Thinking…"):
                st.markdown(generate_ai_brief(_hive_prompt(sig_h, df_h)))
        col_dl, _ = st.columns([1, 3])
        col_dl.download_button("Download signal JSON",
            data=json.dumps(sig_h, indent=2, default=str),
            file_name=f"hive_qqq_{now_et.strftime('%Y%m%d')}.json", mime="application/json")

    # ── SOXS tab ──────────────────────────────────────────────────────────────
    with tab_soxs:
        with st.spinner("Loading QQQ, SOXS, VIX data…"):
            df_s = build_soxs_data(period)
        regimes_s = df_s.apply(classify_soxs, axis=1).apply(lambda d: d["regime"])
        sig_s = classify_soxs(df_s.iloc[-1])
        scolor = SOXS_HERO_COLORS.get(sig_s["regime"], "#9ca3af")
        st.markdown(f'<div class="ts">Last bar: {df_s.index[-1].strftime("%Y-%m-%d %a")} &nbsp;·&nbsp; Cache refreshes every 5 min</div>',
                    unsafe_allow_html=True)
        alloc_s = f"QQQ Core 40%  ·  SOXS Short {sig_s['target_short_alloc']:.0%}  ·  Cash {max(0.0, 1.0 - 0.40 - sig_s['target_short_alloc']):.0%}"
        hero_card(sig_s["regime"], sig_s["action"], alloc_s, sig_s["reason"], scolor)
        qqq_above = sig_s["qqq"] >= sig_s["qqq_ma20"]
        pull = sig_s["soxs_pull"]; vix_s = sig_s["vix"]
        badges_s = [
            badge(f"QQQ {'↑' if qqq_above else '↓'} MA20", "g" if qqq_above else "r"),
            badge(f"SOXS vs High20 {pull:+.1%}", "g" if pull <= -0.08 else ("a" if pull <= -0.03 else "r")),
            badge(f"VIX {vix_s:.1f}", "g" if vix_s < SOXS_VIX_CAUTION else ("a" if vix_s < SOXS_VIX_DANGER else ("r" if vix_s < SOXS_VIX_EMERGENCY else "x"))),
            badge(f"Conf: {sig_s['confidence'].upper()}", "g" if sig_s["confidence"] == "high" else "a"),
        ]
        st.markdown("&nbsp;".join(badges_s), unsafe_allow_html=True)
        st.plotly_chart(make_soxs_chart(df_s, regimes_s), use_container_width=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("QQQ",  f"${sig_s['qqq']:.2f}",  _5d_ret(df_s["QQQ"]) + " 5d")
        c2.metric("SOXS", f"${sig_s['soxs']:.3f}", _5d_ret(df_s["SOXS"]) + " 5d")
        c3.metric("VIX",  f"{sig_s['vix']:.2f}")
        c4.metric("SOXS vs High20", f"{sig_s['soxs_pull']:+.1%}")
        st.markdown("---")
        if st.button("\U0001f916 Generate AI Brief", key="ai_soxs"):
            with st.spinner("Thinking…"):
                st.markdown(generate_ai_brief(_soxs_prompt(sig_s, df_s)))
        col_dl, _ = st.columns([1, 3])
        col_dl.download_button("Download signal JSON",
            data=json.dumps(sig_s, indent=2, default=str),
            file_name=f"soxs_signal_{now_et.strftime('%Y%m%d')}.json", mime="application/json")

    # ── HIVE-Only tab ──────────────────────────────────────────────────────────
    with tab_ho:
        with st.spinner("Loading HIVE, BTC, QQQ, VIX data…"):
            df_ho = build_hive_only_data(period)
        regimes_ho = df_ho.apply(classify_hive_only, axis=1).apply(lambda d: d["regime"])
        sig_ho = classify_hive_only(df_ho.iloc[-1])
        hocolor = HO_HERO_COLORS.get(sig_ho["regime"], "#9ca3af")

        st.markdown(f'<div class="ts">Last bar: {df_ho.index[-1].strftime("%Y-%m-%d %a")} &nbsp;·&nbsp; Cache refreshes every 5 min</div>',
                    unsafe_allow_html=True)

        # Alloc display: +100% LONG / -40% SHORT / FLAT
        alloc_ho = sig_ho["target_alloc"]
        if alloc_ho > 0:
            alloc_line_ho = f"LONG {alloc_ho:.0%} of account"
        elif alloc_ho < 0:
            alloc_line_ho = f"SHORT {abs(alloc_ho):.0%} of account"
        else:
            alloc_line_ho = "FLAT — 100% CASH"

        hero_card(sig_ho["regime"], sig_ho["action"], alloc_line_ho, sig_ho["reason"], hocolor)

        # Condition badges
        rsi = sig_ho["hive_rsi14"]
        vix_ho = sig_ho["vix"]
        badges_ho = [
            badge(f"BTC {'↑' if sig_ho['btc_above_ma20'] else '↓'} MA20", "g" if sig_ho["btc_above_ma20"] else "r"),
            badge(f"QQQ {'↑' if sig_ho['qqq_above_ma50'] else '↓'} MA50", "g" if sig_ho["qqq_above_ma50"] else "r"),
            badge(f"HIVE {'↑' if sig_ho['hive_above_ma20'] else '↓'} MA20", "g" if sig_ho["hive_above_ma20"] else "r"),
            badge(f"RSI {rsi:.1f}", "r" if rsi >= HO_RSI_OB else ("g" if rsi <= HO_RSI_OS else "a")),
            badge(f"VIX {vix_ho:.1f}", "g" if vix_ho < HO_VIX_CALM else ("a" if vix_ho < HO_VIX_CAUTION else ("r" if vix_ho < HO_VIX_ELEVATED else "x"))),
        ]
        st.markdown("&nbsp;".join(badges_ho), unsafe_allow_html=True)

        st.plotly_chart(make_hive_only_chart(df_ho, regimes_ho), use_container_width=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("HIVE", f"${sig_ho['hive']:.3f}",  _5d_ret(df_ho["HIVE"]) + " 5d")
        c2.metric("BTC",  f"${sig_ho['btc']:,.0f}",   _5d_ret(df_ho["BTC"]) + " 5d")
        c3.metric("RSI 14", f"{sig_ho['hive_rsi14']:.1f}")
        c4.metric("VIX",  f"{sig_ho['vix']:.2f}")

        st.markdown("---")
        if st.button("\U0001f916 Generate AI Brief", key="ai_ho"):
            with st.spinner("Thinking…"):
                st.markdown(generate_ai_brief(_hive_only_prompt(sig_ho, df_ho)))

        col_dl, _ = st.columns([1, 3])
        col_dl.download_button("Download signal JSON",
            data=json.dumps(sig_ho, indent=2, default=str),
            file_name=f"hive_only_{now_et.strftime('%Y%m%d')}.json", mime="application/json")


if __name__ == "__main__":
    main()
