
import pandas as pd
import numpy as np

def hazen_williams_j(q_l_s: float, d_mm: float, c: float = 150.0) -> float:
    """
    Declive de energia J (m/m) pela fórmula de Hazen-Williams.
    q_l_s  : vazão em L/s
    d_mm   : diâmetro interno em mm
    c      : coeficiente HW do material
    """
    if q_l_s is None or d_mm is None or d_mm == 0:
        return 0.0
    Q = q_l_s / 1000.0   # m3/s
    D = d_mm / 1000.0    # m
    J = 10.67 * (Q**1.852) / ((c**1.852) * (D**4.871))
    return float(J)

def perda_localizada(L_eq_m: float, J: float) -> float:
    """Perda localizada (mca) = L_eq * J"""
    if L_eq_m is None or J is None:
        return 0.0
    return float(L_eq_m * J)
