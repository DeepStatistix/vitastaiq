"""Build the Price Forecast Lab data from public Agmarknet price histories.

Usage (needs pandas, numpy, statsmodels):
    python build_forecast.py <history_dir> [--out forecast.js] [--only Onion__Maharashtra]

<history_dir> holds files named <State>__<Commodity>.csv with the Agmarknet columns
Arrival_Date (dd/mm/yyyy), Modal_Price, State, Commodity.

Method (everything a forecaster at time t could actually know):
  * weekly series = median of daily state-level median modal prices, Rs/quintal, log scale
  * model = equal blend of damped-trend exponential smoothing and a seasonal-drift forecast
    (last value + shrunken average of the same-season price moves in the previous 3 years)
  * baselines = naive (last value) and seasonal naive (same week last year)
  * rolling-origin backtest over the last 3 years: refit at each origin on data up to that
    origin only, forecast 12 weeks ahead, score against what actually happened
  * prediction intervals = empirical quantiles of backtest errors per horizon; their coverage
    is checked on origins that were NOT used to calibrate them
"""
import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")

H = 12            # forecast horizon, weeks
BACK_WEEKS = 156  # backtest window, weeks
STEP = 4          # an origin every 4 weeks
HIST_SHOW = 156   # weeks of history shown on the page
TRAIN_FROM = "2018-01-01"


def load_weekly(path: Path) -> pd.Series | None:
    d = pd.read_csv(path)
    d["dt"] = pd.to_datetime(d["Arrival_Date"], format="%d/%m/%Y", errors="coerce")
    d = d[(d["Modal_Price"] > 0) & d["dt"].notna() & (d["dt"] >= TRAIN_FROM)]
    if d.empty:
        return None
    daily = d.groupby("dt")["Modal_Price"].median()
    days_in_week = daily.resample("W-SUN").count()
    wk = daily.resample("W-SUN").median()
    if days_in_week.iloc[-1] < 4:  # drop a thin, still-running last week
        wk = wk.iloc[:-1]
    wk = wk.asfreq("W-SUN")
    if wk.isna().mean() > 0.10:
        return None
    return wk.interpolate(limit=6).ffill().bfill()


def seasonal_drift(tr: np.ndarray, h: int, years: int = 3, shrink: float = 0.5) -> np.ndarray:
    """Last value plus a shrunken average of how prices moved over the same weeks in earlier years."""
    n, out = len(tr), []
    for j in range(1, h + 1):
        d = [tr[n - 1 - 52 * i + j] - tr[n - 1 - 52 * i] for i in range(1, years + 1)
             if n - 1 - 52 * i >= 0 and n - 1 - 52 * i + j < n]
        out.append(tr[-1] + shrink * np.mean(d) if d else tr[-1])
    return np.array(out)


def fit_forecast(y_log, h: int) -> np.ndarray:
    """Equal blend of damped-trend exponential smoothing and the seasonal-drift forecast (log scale)."""
    tr = np.asarray(y_log, dtype=float)
    ets = np.asarray(ExponentialSmoothing(tr, trend="add", damped_trend=True).fit().forecast(h))
    return 0.5 * ets + 0.5 * seasonal_drift(tr, h)


def backtest(y: pd.Series):
    yl = np.log(y)
    n = len(y)
    origins = list(range(n - BACK_WEEKS - H, n - H, STEP))
    rows = []  # (origin_idx, h, actual, model, naive, snaive)
    for t in origins:
        train = yl.iloc[: t + 1]
        try:
            f = fit_forecast(train, H)
        except Exception:
            continue
        for h in range(1, H + 1):
            tgt = t + h
            snaive = yl.iloc[tgt - 52] if tgt - 52 >= 0 else np.nan
            rows.append((t, h, yl.iloc[tgt], f[h - 1], yl.iloc[t], snaive))
    return pd.DataFrame(rows, columns=["t", "h", "act", "mod", "nai", "snai"])


def summarise(bt: pd.DataFrame, y: pd.Series):
    ape = lambda col: (np.exp(bt[col] - bt["act"]) - 1).abs()  # APE of the price, from log forecasts
    bt = bt.assign(m=ape("mod"), n=ape("nai"), s=ape("snai"))
    by_h = bt.groupby("h")[["m", "n", "s"]].mean() * 100
    # intervals: calibrate on the earlier 60% of origins, test coverage on the later 40%
    origins = sorted(bt["t"].unique())
    cut = origins[int(len(origins) * 0.6)]
    err = bt.assign(e=bt["act"] - bt["mod"])
    cal, test = err[err["t"] < cut], err[err["t"] >= cut]
    cov = []
    for h in range(1, H + 1):
        lo, hi = cal[cal["h"] == h]["e"].quantile([0.10, 0.90])
        te = test[test["h"] == h]["e"]
        cov.append(float(((te >= lo) & (te <= hi)).mean()))
    q = {h: err[err["h"] == h]["e"].quantile([0.025, 0.10, 0.90, 0.975]).values for h in range(1, H + 1)}
    return by_h, float(np.mean(cov)), q, bt


def build_one(path: Path):
    y = load_weekly(path)
    if y is None or len(y) < BACK_WEEKS + H + 120:
        return None
    bt = backtest(y)
    if bt.empty:
        return None
    by_h, cov80, q, bt = summarise(bt, y)
    f = fit_forecast(np.log(y), H)
    last = y.index[-1]
    fc = []
    for h in range(1, H + 1):
        lo95, lo80, hi80, hi95 = q[h]
        fc.append({"d": (last + pd.Timedelta(weeks=h)).strftime("%Y-%m-%d"), "p": round(float(np.exp(f[h - 1]))),
                   "l80": round(float(np.exp(f[h - 1] + lo80))), "h80": round(float(np.exp(f[h - 1] + hi80))),
                   "l95": round(float(np.exp(f[h - 1] + lo95))), "h95": round(float(np.exp(f[h - 1] + hi95)))})
    # actual vs 4-week-ahead forecast for each backtest origin
    b4 = bt[bt["h"] == 4]
    idx = y.index
    chart = [{"d": idx[int(r.t) + 4].strftime("%Y-%m-%d"), "a": round(float(np.exp(r.act))), "f": round(float(np.exp(r["mod"])))}
             for _, r in b4.iterrows()]
    hist = y.iloc[-HIST_SHOW:]
    return {
        "hist": [[d.strftime("%Y-%m-%d"), round(float(v))] for d, v in hist.items()],
        "fc": fc, "bt4": chart,
        "score": {"origins": int(bt["t"].nunique()),
                  "model": [round(float(by_h.loc[h, "m"]), 1) for h in range(1, H + 1)],
                  "naive": [round(float(by_h.loc[h, "n"]), 1) for h in range(1, H + 1)],
                  "snaive": [round(float(by_h.loc[h, "s"]), 1) for h in range(1, H + 1)],
                  "cov80": round(cov80 * 100)},
        "last": last.strftime("%Y-%m-%d"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hist_dir")
    ap.add_argument("--out", default=str(Path(__file__).parent / "forecast.js"))
    ap.add_argument("--only")
    a = ap.parse_args()
    out = {}
    for p in sorted(Path(a.hist_dir).glob("*__*.csv")):
        state, com = p.stem.split("__")
        if com not in ("Onion", "Tomato", "Potato"):
            continue
        key = f"{com}|{state.replace('_', ' ')}"
        if a.only and a.only != f"{com}__{state}":
            continue
        r = build_one(p)
        if r is None:
            print(f"skip {key} (too sparse)")
            continue
        out[key] = r
        s = r["score"]
        print(f"{key}: MAPE h4 model {s['model'][3]}% naive {s['naive'][3]}% snaive {s['snaive'][3]}% | h12 {s['model'][11]}/{s['naive'][11]} | cov80 {s['cov80']}% | origins {s['origins']}", flush=True)
    Path(a.out).write_text("window.FC=" + json.dumps(out, separators=(",", ":")) + ";", encoding="utf-8")
    print("wrote", a.out, Path(a.out).stat().st_size, "bytes,", len(out), "series")


if __name__ == "__main__":
    main()
