
from dataclasses import dataclass
@dataclass
class Trecho:
    id: int
    de_no: str
    para_no: str
    andar: str
    material: str
    dn_mm: float
    comp_real_m: float
    leq_m: float = 0.0
