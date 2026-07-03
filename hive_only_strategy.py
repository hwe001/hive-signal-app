#!/usr/bin/env python3
"""
HIVE-only long/short equity strategy.

The account holds only HIVE — goes long when BTC trend and macro are
supportive, short (up to 55%) when conditions deteriorate.
Pure functions: no Streamlit, no data fetching, no broker calls.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd


HIVE_SYMBOL   = "HIVE"
BTC_SYMBOL    = "BTC-USD"
QQQ_SYMBOL    = "QQQ"
VIX_SYMBOL    = "^VIX"

HIVE_MA_FAST  = 5
HIVE_MA_SLOW  = 20
BTC_MA_PERIOD = 20
QQQ_MA_PERIOD = 50
RSI_PERIOD    = 14

LONG_FULL      =  1.00
LONG_MODERATE  =  0.70
LONG_LIGHT     =  0.35
LONG_PILOT     =  0.20
FLAT           =  0.00
SHORT_LIGHT    = -0.25
SHORT_MODERATE = -0.40
SHORT_FULL     = -0.55

VIX_CALM     = 18.0
VIX_CAUTION  = 28.0
VIX_ELEVATED = 38.0
VIX_DANGER   = 50.0

RSI_OVERBOUGHT = 72.0
RSI_OVERSOLD   = 28.0

_ALLOC_ACTIONS = {
    LONG_FULL:      "LONG FULL — 100%",
    LONG_MODERATE:  "LONG MODERATE — 70%",
    LONG_LIGHT:     "LONG LIGHT — 35%",
    LONG_PILOT:     "LONG PILOT — 20%",
    FLAT:           "FLAT / CASH",
    SHORT_LIGHT:    "SHORT LIGHT — 25%",
    SHORT_MODERATE: "SHORT MODERATE — 40%",
    SHORT_FULL:     "SHORT FULL — 55%",
}


def _classify(btc_above: bool, qqq_above: bool, vix: float,
              rsi: float) -> tuple[float, str]:
    ob  = rsi >= RSI_OVERBOUGHT
    os_ = rsi <= RSI_OVERSOLD

    if vix >= VIX_DANGER:
        return FLAT, "danger"

    if btc_above and qqq_above:
        if ob or vix >= VIX_ELEVATED:
            return LONG_LIGHT, "bull_cautious"
        if vix < VIX_CALM:
            return LONG_FULL, "bull_strong"
        return LONG_MODERATE, "bull"

    if btc_above:
        return LONG_PILOT, "btc_bull_qqq_soft"
    if qqq_above:
        return FLAT, "btc_bear_qqq_firm"
    if vix >= VIX_ELEVATED:
        return FLAT, "bear_panic"
    if os_:
        return SHORT_LIGHT, "bear_oversold"

    return (SHORT_FULL if vix < VIX_CAUTION else SHORT_MODERATE), "bear"


def classify_signal(row: pd.Series) -> dict:
    """
    HIVE-only long/short signal.

    Required columns: HIVE, HIVE_MA5, HIVE_MA20, HIVE_RSI14,
                      BTC, BTC_MA20, QQQ, QQQ_MA50, VIX
    """
    vix        = float(row["VIX"])
    btc_above  = float(row["BTC"]) >= float(row["BTC_MA20"])
    qqq_above  = float(row["QQQ"]) >= float(row["QQQ_MA50"])
    rsi        = float(row["HIVE_RSI14"])
    hive_above = float(row["HIVE"]) >= float(row["HIVE_MA20"])

    alloc, regime = _classify(btc_above, qqq_above, vix, rsi)

    reasons = {
        "bull_strong":      f"BTC ↑ MA20, QQQ ↑ MA50, VIX {vix:.1f} calm — full long.",
        "bull":             f"BTC ↑ MA20, QQQ ↑ MA50, VIX {vix:.1f} moderate — long with sizing.",
        "bull_cautious":    (f"BTC ↑ MA20, QQQ ↑ MA50 but "
                             f"{'RSI overbought' if rsi >= RSI_OVERBOUGHT else f'VIX {vix:.1f} elevated'}"
                             " — reduced long."),
        "btc_bull_qqq_soft": f"BTC ↑ MA20 but QQQ ↓ MA50 — pilot position only.",
        "btc_bear_qqq_firm": "BTC ↓ MA20, QQQ ↑ MA50 — conflicting signals; stay flat.",
        "bear":             f"BTC ↓ MA20, QQQ ↓ MA50, VIX {vix:.1f} — {'full' if alloc == SHORT_FULL else 'moderate'} short.",
        "bear_oversold":    f"Bear regime but RSI {rsi:.1f} oversold — light short only, watch for bounce.",
        "bear_panic":       f"Bear regime with VIX {vix:.1f} elevated — stay flat, tail risk too high.",
        "danger":           f"VIX {vix:.1f} ≥ {VIX_DANGER} — danger mode, 100% cash.",
    }

    return {
        "timestamp_ny":   datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S"),
        "regime":         regime,
        "action":         _ALLOC_ACTIONS[alloc],
        "target_alloc":   alloc,
        "reason":         reasons.get(regime, ""),
        "hive":           float(row["HIVE"]),
        "hive_ma5":       float(row["HIVE_MA5"]),
        "hive_ma20":      float(row["HIVE_MA20"]),
        "hive_rsi14":     rsi,
        "hive_above_ma20": hive_above,
        "btc":            float(row["BTC"]),
        "btc_ma20":       float(row["BTC_MA20"]),
        "btc_above_ma20": btc_above,
        "qqq":            float(row["QQQ"]),
        "qqq_ma50":       float(row["QQQ_MA50"]),
        "qqq_above_ma50": qqq_above,
        "vix":            vix,
    }
