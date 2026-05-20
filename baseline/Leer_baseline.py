def leer_baseline_hdzf(path, doy_ini=310, doy_fin=342):
    baseline = []

    with open(path, "r") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("*"):
                continue
            if line.startswith("Comments"):
                break

            parts = line.split()
            if len(parts) < 5:
                continue

            try:
                doy = int(parts[0])
                H = float(parts[1])
                D = float(parts[2])
                Z = float(parts[3])
                F = float(parts[4])
            except ValueError:
                continue

            if doy_ini <= doy <= doy_fin:
                baseline.append({
                    "H": H,
                    "D": D,
                    "Z": Z,
                    "F": F
                })

    if not baseline:
        raise ValueError("No se encontraron datos válidos de línea base")

    mean = lambda k: sum(r[k] for r in baseline) / len(baseline)

    return baseline, {
        "H": mean("H"),
        "D": mean("D"),
        "Z": mean("Z"),
        "F": mean("F")
    }