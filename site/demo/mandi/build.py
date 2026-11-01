"""Aggregate public Agmarknet daily price/arrival CSVs into a small JSON for the static dashboard.

Usage: python build.py <input_dir> [output_json]

Input files are the Agmarknet "Daily Price Arrival Report" exports (one commodity per file,
header on the second row). Only aggregates are written; raw rows are not kept.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

COMMODITIES = ["Onion", "Tomato", "Potato", "Banana"]


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, header=1, thousands=",")
    df["date"] = pd.to_datetime(df["Arrival Date"], format="%d-%m-%Y", errors="coerce")
    df = df.rename(columns={"State/UT": "state", "Market": "market", "Modal Price": "modal",
                            "Arrival Quantity": "arrival"})
    df = df[(df["Price Unit"] == "Rs./Quintal") & df["date"].notna() & (df["modal"] > 0)]
    df["arrival"] = df["arrival"].fillna(0).clip(lower=0)
    return df[["date", "state", "market", "modal", "arrival"]]


def wavg(g: pd.DataFrame) -> float:
    w = g["arrival"]
    return float(np.average(g["modal"], weights=w)) if w.sum() > 0 else float(g["modal"].mean())


def drop_thin_days(df: pd.DataFrame, floor: float = 0.6) -> pd.DataFrame:
    """Drop days where far fewer markets reported than usual (partial export days skew averages)."""
    n = df.groupby("date")["market"].nunique()
    keep = n[n >= floor * n.median()].index
    return df[df["date"].isin(keep)]


def summarise(df: pd.DataFrame) -> dict:
    df = drop_thin_days(df)
    daily =df.groupby("date").apply(
        lambda g: pd.Series({"price": wavg(g), "arrival": g["arrival"].sum(), "markets": g["market"].nunique()}),
        include_groups=False,
    ).reset_index()

    last = df["date"].max()
    recent = df[df["date"] > last - pd.Timedelta(days=7)]
    prior = df[(df["date"] <= last - pd.Timedelta(days=7)) & (df["date"] > last - pd.Timedelta(days=14))]

    states = []
    for st, g in recent.groupby("state"):
        p = prior[prior["state"] == st]
        now = wavg(g)
        before = wavg(p) if len(p) else None
        states.append({
            "state": st,
            "price": round(now, 0),
            "change_pct": round((now / before - 1) * 100, 1) if before else None,
            "arrival": round(float(g["arrival"].sum()), 1),
            "markets": int(g["market"].nunique()),
        })
    states.sort(key=lambda r: -r["arrival"])

    markets = (recent.groupby(["state", "market"])
               .apply(lambda g: pd.Series({"price": wavg(g), "arrival": g["arrival"].sum()}), include_groups=False)
               .reset_index().sort_values("arrival", ascending=False).head(10))

    return {
        "daily": [{"date": r.date.strftime("%Y-%m-%d"), "price": round(r.price, 0),
                   "arrival": round(r.arrival, 1), "markets": int(r.markets)} for r in daily.itertuples()],
        "states": states,
        "top_markets": [{"state": r.state, "market": r.market, "price": round(r.price, 0),
                         "arrival": round(r.arrival, 1)} for r in markets.itertuples()],
        "last_date": last.strftime("%Y-%m-%d"),
        "rows": int(len(df)),
    }


def main() -> None:
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "data.json"
    result = {}
    for name in COMMODITIES:
        f = src / f"{name}.csv"
        if f.exists():
            result[name] = summarise(load(f))
            print(name, result[name]["rows"], "rows ->", len(result[name]["daily"]), "days")
    out.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    print("wrote", out, out.stat().st_size, "bytes")
    # Same data as a script so index.html also works when opened from disk (file://)
    out.with_suffix(".js").write_text("window.MANDI=" + out.read_text(encoding="utf-8") + ";", encoding="utf-8")


if __name__ == "__main__":
    main()
