
from __future__ import annotations
from typing import Dict
import pandas as pd

class ParsedExcel:
    def __init__(self, raw: Dict[str, pd.DataFrame]):
        self.raw = raw
        self.exerc = raw.get("Exerc_4_(AF1)")
        self.peso_andar = raw.get("Peso_Andar")
        self.compr_eq = raw.get("Compr_Eq_(AF1)")
        self.quadro_33_pvc = raw.get("Quadro 3.3_PVC")
        self.quadro_33_ff = raw.get("Quadro 3.3_FF")

def load_three_sheets(file) -> ParsedExcel:
    xls = pd.ExcelFile(file, engine="openpyxl")
    need = ["Exerc_4_(AF1)", "Peso_Andar", "Compr_Eq_(AF1)", "Quadro 3.3_PVC", "Quadro 3.3_FF"]
    raw = {s: pd.read_excel(xls, sheet_name=s, header=None) for s in need if s in xls.sheet_names}
    return ParsedExcel(raw)

def normalize_peso_andar(df: pd.DataFrame) -> pd.DataFrame:
    tmp = df.copy(); tmp.columns = list(range(tmp.shape[1]))
    header_row = tmp.index[tmp.apply(lambda r: r.astype(str).str.contains("Apartamento Tipo", na=False).any(), axis=1)]
    start = int(header_row[0]) if len(header_row) else 0
    body = tmp.iloc[start+2:].reset_index(drop=True)
    body = body.rename(columns={1:"aparelho", 3:"peca", 6:"AF1", 7:"AF2", 8:"AF3", 9:"AF4", 10:"area_ad"})
    keep = ["aparelho","peca","AF1","AF2","AF3","AF4","area_ad"]; body = body[keep].copy()
    body = body[body["aparelho"].notna() | body["peca"].notna()]
    return body.reset_index(drop=True)

def normalize_compr_eq(df: pd.DataFrame) -> pd.DataFrame:
    tmp = df.copy(); tmp.columns = list(range(tmp.shape[1]))
    groups = []
    for c in range(tmp.shape[1]):
        txt = str(tmp.iat[1, c]) if 1 < len(tmp) else ""
        if "-" in txt and len(txt) <= 7:
            groups.append((c, txt.strip()))
    out_rows = []
    for (c0, trecho) in groups:
        total_col = c0; qt_col = c0 + 2; dn_row_guess = 3
        for r in range(5, tmp.shape[0]):
            total = tmp.iat[r, total_col] if total_col < tmp.shape[1] else None
            qt = tmp.iat[r, qt_col] if qt_col < tmp.shape[1] else None
            dn = tmp.iat[dn_row_guess, c0] if dn_row_guess < tmp.shape[0] else None
            if pd.isna(total) and pd.isna(qt): continue
            try: total_f = float(total)
            except: total_f = None
            try: qt_f = float(qt)
            except: qt_f = None
            try: dn_f = float(dn)
            except: dn_f = None
            if total_f is None and qt_f is None: continue
            out_rows.append({"trecho": trecho, "dn_mm": dn_f, "quantidade": qt_f, "total_m": total_f})
    return pd.DataFrame(out_rows)

def normalize_exerc(df: pd.DataFrame) -> pd.DataFrame:
    tmp = df.copy(); tmp.columns = list(range(tmp.shape[1]))
    body = tmp[[0, 16, 17, 18]].dropna(how="all")
    body.columns = ["andar","col16","press_disp_kpa","press_req_kpa"]
    mask = body["andar"].astype(str).str.contains("o|Barrilete|Térreo|Subsolo", case=False, na=False)
    body = body[mask].reset_index(drop=True)
    return body

def normalize_quadro33(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return pd.DataFrame()
    tmp = df.copy(); tmp.columns = list(range(tmp.shape[1]))
    rows = []
    for r in range(tmp.shape[0]):
        for c in range(tmp.shape[1]):
            val = tmp.iat[r, c]
            if isinstance(val, (int, float)) and not pd.isna(val):
                rows.append({"row": r, "col": c, "value": float(val)})
    return pd.DataFrame(rows)
