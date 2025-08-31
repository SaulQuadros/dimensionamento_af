
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Optional
import pandas as pd

@dataclass
class Trecho:
    id: int
    de_no: str
    para_no: str
    andar: str   # 'Barrilete' ou nome do pavimento
    material: str  # 'PVC' or 'FoFo'
    dn_mm: float
    comp_real_m: float
    leq_m: float = 0.0

def tabela_trechos_default(andars: List[str]) -> pd.DataFrame:
    cols = ["id","de_no","para_no","andar","material","dn_mm","comp_real_m","leq_m"]
    return pd.DataFrame(columns=cols)

def to_json_rows(df: pd.DataFrame) -> List[dict]:
    return [row._asdict() if hasattr(row, "_asdict") else dict(row) for _, row in df.iterrows()]
