import os
import json
import numpy as np
import pandas as pd
from datetime import datetime

from .sq_state import SQ_STATE
from .sq_io import (
    combinar_ventana_mixta_xyh,
    obtener_ultimo_dia_completo_mixto
)

QUIET_DAYS_POR_MES = 5
VENTANA_MESES = 6
MIN_POINTS_DAY = 1200


def calcular_daily_deltaH(dfH: pd.DataFrame) -> pd.DataFrame:
    resultados = []
    for fecha, grupo in dfH["H"].resample("D"):
        g = grupo.dropna()
        if len(g) < MIN_POINTS_DAY:
            continue
        difs = g.diff().abs().dropna()
        deltaH = difs.mean() if len(difs) > 0 else np.nan
        resultados.append({
            "fecha": pd.Timestamp(fecha),
            "deltaH": deltaH,
            "n": len(g)
        })

    daily = pd.DataFrame(resultados)
    if daily.empty:
        return daily

    daily["mes"] = daily["fecha"].dt.to_period("M")
    return daily


def quiet_days_5_por_mes(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return daily

    return (
        daily.dropna(subset=["deltaH"])
             .sort_values(["mes", "deltaH"])
             .groupby("mes")
             .head(QUIET_DAYS_POR_MES)
             .reset_index(drop=True)
    )


def ajustar_poly1_mco(dfH: pd.DataFrame, quiet_fechas: pd.Series) -> tuple[float, float]:
    X_list, y_list = [], []

    for d in pd.to_datetime(quiet_fechas).dt.floor("D").unique():
        ini = pd.Timestamp(d).floor("D")
        fin = ini + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

        dia = dfH.loc[ini:fin].dropna(subset=["H"])
        if dia.empty:
            continue

        m = dia.index.hour * 60 + dia.index.minute
        X_list.append(m.to_numpy(dtype=float))
        y_list.append(dia["H"].to_numpy(dtype=float))

    if not X_list:
        raise RuntimeError("No hay datos suficientes para ajustar poly1 (quiet days vacíos).")

    X = np.concatenate(X_list)
    y = np.concatenate(y_list)

    A = np.column_stack([np.ones_like(X), X])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)

    return float(coef[0]), float(coef[1])


def recomputar_sq_desde_db(
    db_config: dict,
    table_minuto: str,
    table_lemi: str,
    out_dir: str,
    h0: float,
    dia_objetivo: pd.Timestamp | None = None
) -> dict:
    """
    Recalcula el modelo Sq usando una ventana mixta:
    - histórico en table_minuto
    - tiempo real en table_lemi

    Todo se lleva a 1 segundo para trabajar con una sola resolución.
    """
    if dia_objetivo is None:
        dia_objetivo = obtener_ultimo_dia_completo_mixto(
            db_config=db_config,
            table_minuto=table_minuto,
            table_lemi=table_lemi,
            h0=h0,
            min_points_day=MIN_POINTS_DAY
        )

    if dia_objetivo is None:
        raise RuntimeError("No se encontró un día completo usable en la serie mixta para recalcular Sq.")

    dia_objetivo = pd.Timestamp(dia_objetivo).floor("D")
    start = (dia_objetivo - pd.DateOffset(months=VENTANA_MESES)).floor("D")
    end = dia_objetivo + pd.Timedelta(hours=23, minutes=59, seconds=59)

    df = combinar_ventana_mixta_xyh(
        db_config=db_config,
        table_minuto=table_minuto,
        table_lemi=table_lemi,
        start=start,
        end=end,
        h0=h0
    )

    if df.empty:
        raise RuntimeError(
            f"No hay datos en la serie mixta para la ventana {start} - {end}"
        )

    # promedio diario de H sobre la serie unificada a 1 segundo
    daily_mean_H = (
        df["H"]
        .resample("D")
        .mean()
        .dropna()
        .reset_index(name="H_mean")
        .rename(columns={"time": "fecha"})
    )

    daily = calcular_daily_deltaH(df)
    if daily.empty:
        raise RuntimeError("No hubo suficientes días con datos válidos para calcular deltaH diario.")

    quiet = quiet_days_5_por_mes(daily)
    if quiet.empty:
        raise RuntimeError("No se pudieron seleccionar quiet days.")

    a0, a1 = ajustar_poly1_mco(df, quiet["fecha"])

    # ===== corrección para evitar salto abrupto al cambiar de modelo =====
    ahora_utc = pd.Timestamp.utcnow()
    m_ref = ahora_utc.hour * 60 + ahora_utc.minute

    a0_old = SQ_STATE.a0
    a1_old = SQ_STATE.a1

    if a0_old is not None and a1_old is not None:
        i_old_ref = a0_old + a1_old * m_ref
        i_new_ref = a0 + a1 * m_ref
        delta = i_old_ref - i_new_ref
        a0 = a0 + delta
        print(
            f"🔧 Continuidad Sq aplicada en m={m_ref}: "
            f"I_old={i_old_ref:.4f}, I_new={i_new_ref:.4f}, delta={delta:.4f}"
        )
        
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        "station": "FUQ",
        "source": "MariaDB_mixto",
        "table_minuto": table_minuto,
        "table_lemi": table_lemi,
        "fecha_modelo": dia_objetivo.strftime("%Y-%m-%d"),
        "ventana_start": start.strftime("%Y-%m-%d"),
        "ventana_end": dia_objetivo.strftime("%Y-%m-%d"),
        "quiet_days_por_mes": QUIET_DAYS_POR_MES,
        "quiet_days_total": int(len(quiet)),
        "quiet_days": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in quiet["fecha"]],
        "coef": {"a0": a0, "a1": a1},
        "daily_mean_H": [
            {
                "fecha": pd.Timestamp(r["fecha"]).strftime("%Y-%m-%d"),
                "H_mean": None if pd.isna(r["H_mean"]) else float(r["H_mean"])
            }
            for _, r in daily_mean_H.iterrows()
        ],
        "timestamp_utc": datetime.utcnow().isoformat() + "Z"
    }

    out_file = os.path.join(out_dir, f"coef_SQ_poly1_{dia_objetivo.strftime('%Y%m%d')}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    SQ_STATE.fecha_modelo = payload["fecha_modelo"]
    SQ_STATE.a0 = a0
    SQ_STATE.a1 = a1
    SQ_STATE.quiet_days = payload["quiet_days"]
    SQ_STATE.n_quiet = len(payload["quiet_days"])

    return payload