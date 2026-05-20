import pandas as pd
import numpy as np

def daily_deltaH(df, min_points_day=600):
    rows = []
    for fecha, g in df.dropna(subset=["H"]).resample("D"):
        if len(g) < min_points_day:
            continue
        deltaH = g["H"].diff().abs().mean()
        rows.append({"fecha": fecha, "deltaH": deltaH, "n": len(g)})

    if not rows:
        return pd.DataFrame(columns=["fecha", "deltaH", "n", "mes"]).set_index("fecha")

    daily = pd.DataFrame(rows).set_index("fecha")
    daily["mes"] = daily.index.to_period("M")
    return daily

def quiet_days(daily, quiet_per_month=5):
    if daily.empty:
        return daily

    q = (
        daily.sort_values(["mes", "deltaH"])
             .groupby("mes")
             .head(quiet_per_month)
             .reset_index()
    )
    return q