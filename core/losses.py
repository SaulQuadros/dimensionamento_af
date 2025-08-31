import numpy as np

def hazen_williams_j(q_l_s: float, d_mm: float, c: float = 150.0) -> float:
    if q_l_s is None or d_mm in (None, 0):
        return 0.0
    Q = q_l_s / 1000.0  # L/s -> m³/s
    D = d_mm / 1000.0   # mm -> m
    J = 10.67 * (Q**1.852) / ((c**1.852) * (D**4.871))
    return float(J)

def comprimento_equivalente_total(eqlen_row: dict, detalhes: list[dict]) -> float:
    total = 0.0
    if eqlen_row is None:
        return 0.0
    for item in detalhes or []:
        tipo = item.get("tipo")
        qtd  = float(item.get("quantidade") or 0)
        if not tipo or qtd <= 0: 
            continue
        L = float(eqlen_row.get(tipo, 0) or 0)
        total += qtd * L
    return float(total)
