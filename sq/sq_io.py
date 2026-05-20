import os
import pandas as pd
import numpy as np
import mysql.connector


CORTE_LEMI = pd.Timestamp("2026-01-01 00:00:00")


def cargar_min_folder(ruta: str) -> pd.DataFrame:
    """Carga TODOS los .min de una carpeta (no recursivo), igual a tu script."""
    archivos = [f for f in os.listdir(ruta) if f.lower().endswith(".min")]
    dfs = []

    for archivo in archivos:
        ruta_archivo = os.path.join(ruta, archivo)

        header_line = None
        with open(ruta_archivo, "r", errors="ignore") as f:
            for i, linea in enumerate(f):
                if linea.startswith("DATE"):
                    header_line = i
                    break
        if header_line is None:
            continue

        df = pd.read_csv(
            ruta_archivo,
            sep=r"\s+",
            header=header_line,
            na_values=["99999.00", "99999", "NaN"],
            dtype=str,
            engine="python"
        )

        df = df[df["DATE"].str.match(r"\d{4}-\d{2}-\d{2}", na=False)].copy()

        df["datetime"] = pd.to_datetime(
            df["DATE"] + " " + df["TIME"],
            format="%Y-%m-%d %H:%M:%S.%f",
            errors="coerce"
        )

        df = df.dropna(subset=["datetime"]).set_index("datetime")

        if "|" in df.columns:
            df.drop(columns=["|"], inplace=True)

        for col in ["FUQX", "FUQY", "FUQZ", "FUQG", "FUQH"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    return pd.concat(dfs, axis=0).sort_index()


def _leer_tabla_generica(db_config: dict, query: str, params: list) -> pd.DataFrame:
    conn = mysql.connector.connect(**db_config)
    try:
        df = pd.read_sql(query, conn, params=params)
    finally:
        conn.close()

    if df.empty:
        return pd.DataFrame()

    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"]).set_index("time").sort_index()
    return df


def cargar_xyh_minuto_desde_db(
    db_config: dict,
    table_name: str,
    start: pd.Timestamp,
    end: pd.Timestamp
) -> pd.DataFrame:
    """
    Lee time, x, y, H desde la tabla histórica al minuto.
    """
    query = f"""
        SELECT time, x, y, H
        FROM {table_name}
        WHERE time BETWEEN %s AND %s
        ORDER BY time ASC
    """
    df = _leer_tabla_generica(
        db_config=db_config,
        query=query,
        params=[start.to_pydatetime(), end.to_pydatetime()]
    )

    if df.empty:
        return pd.DataFrame(columns=["x", "y", "H"])

    for col in ["x", "y", "H"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df[["x", "y", "H"]]


def cargar_xyh_lemi_desde_db(
    db_config: dict,
    table_name: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    h0: float | None = None
) -> pd.DataFrame:
    """
    Lee LEMI en tiempo real.
    En LEMI: x = dH, y = dD, z = dZ.
    Para Sq necesitamos H absoluto, así que H = h0 + x.
    """
    query = f"""
        SELECT time, x, y
        FROM {table_name}
        WHERE time BETWEEN %s AND %s
        ORDER BY time ASC
    """
    df = _leer_tabla_generica(
        db_config=db_config,
        query=query,
        params=[start.to_pydatetime(), end.to_pydatetime()]
    )

    if df.empty:
        return pd.DataFrame(columns=["x", "y", "H"])

    for col in ["x", "y"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if h0 is None:
        raise RuntimeError("Para convertir LEMI a H absoluto debes pasar h0.")

    df["H"] = h0 + df["x"]
    return df[["x", "y", "H"]]


def resample_minuto_a_segundo(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte serie al minuto a 1 segundo repitiendo el valor del minuto
    durante 60 s. Esto preserva el promedio diario y permite mezclarla
    con la serie LEMI de mayor resolución.
    """
    if df.empty:
        return df.copy()

    df = df.sort_index()

    agg = {}
    for c in df.columns:
        agg[c] = "mean"

    # por si hubiera duplicados exactos dentro del mismo minuto
    df_1min = df.resample("1min").agg(agg)

    # expandir a 1 segundo
    df_1s = df_1min.resample("1s").ffill(limit=59)

    return df_1s


def combinar_ventana_mixta_xyh(
    db_config: dict,
    table_minuto: str,
    table_lemi: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    h0: float
) -> pd.DataFrame:
    """
    Combina datos viejos (tabla al minuto) + datos nuevos (LEMI).
    - Lo viejo se resamplea a 1 segundo.
    - Lo nuevo se toma tal cual.
    - Si existe traslape, se prioriza LEMI.
    """
    partes = []

    # ---- Parte histórica al minuto ----
    start_min = start
    end_min = min(end, CORTE_LEMI - pd.Timedelta(seconds=1))
    if start_min <= end_min:
        df_min = cargar_xyh_minuto_desde_db(
            db_config=db_config,
            table_name=table_minuto,
            start=start_min,
            end=end_min
        )
        if not df_min.empty:
            df_min_1s = resample_minuto_a_segundo(df_min)
            partes.append(df_min_1s)

    # ---- Parte nueva LEMI ----
    start_lemi = max(start, CORTE_LEMI)
    end_lemi = end
    if start_lemi <= end_lemi:
        df_lemi = cargar_xyh_lemi_desde_db(
            db_config=db_config,
            table_name=table_lemi,
            start=start_lemi,
            end=end_lemi,
            h0=h0
        )
        if not df_lemi.empty:
            # por si viniera con duplicados en el mismo segundo
            df_lemi = df_lemi.groupby(df_lemi.index).mean().sort_index()
            partes.append(df_lemi)

    if not partes:
        return pd.DataFrame(columns=["x", "y", "H"])

    df = pd.concat(partes).sort_index()

    # si llegara a haber traslape, nos quedamos con el último (LEMI)
    df = df[~df.index.duplicated(keep="last")]

    return df


def obtener_ultimo_dia_completo_mixto(
    db_config: dict,
    table_minuto: str,
    table_lemi: str,
    h0: float,
    min_points_day: int = 1200,
    dias_revision: int = 15
) -> pd.Timestamp | None:
    """
    Busca el último día completo usable revisando los últimos N días de la serie mixta.
    Como al final todo se lleva a 1 segundo, un día completo ideal tendría 86400 puntos,
    pero dejamos un umbral flexible.
    """
    hoy = pd.Timestamp.utcnow().tz_localize(None).floor("D")
    inicio = hoy - pd.Timedelta(days=dias_revision)
    fin = hoy - pd.Timedelta(seconds=1)

    df = combinar_ventana_mixta_xyh(
        db_config=db_config,
        table_minuto=table_minuto,
        table_lemi=table_lemi,
        start=inicio,
        end=fin,
        h0=h0
    )

    if df.empty:
        return None

    conteo = df["H"].resample("D").count()

    # recorremos desde el más reciente hacia atrás
    for fecha, n in conteo.sort_index(ascending=False).items():
        if n >= min_points_day:
            return pd.Timestamp(fecha)

    return None