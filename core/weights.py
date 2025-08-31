
import pandas as pd

def load_uc_default(csv_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(csv_path)
        df["aparelho_full"] = df["aparelho_full"].astype(str)
        df["peso_uc"] = pd.to_numeric(df["peso_uc"], errors="coerce").fillna(1.0)
        return df[["aparelho_full","peso_uc"]]
    except Exception:
        return pd.DataFrame(columns=["aparelho_full","peso_uc"])

def build_pesos_uc_from_aparelhos(aparelhos: pd.Series, uc_default: pd.DataFrame) -> pd.DataFrame:
    base = pd.DataFrame({"aparelho_full": aparelhos.dropna().unique()})
    base["aparelho_full"] = base["aparelho_full"].astype(str)
    df = base.merge(uc_default, on="aparelho_full", how="left")
    df["peso_uc"] = pd.to_numeric(df["peso_uc"], errors="coerce").fillna(1.0)
    return df.sort_values("aparelho_full").reset_index(drop=True)

def normalize_peso_andar_table(peso_andar_tidy: pd.DataFrame) -> pd.DataFrame:
    df = peso_andar_tidy.copy()
    for c in ["AF1","AF2","AF3","AF4"]:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["aparelho_full"] = df[["aparelho","peca"]].fillna("").agg(lambda x: " - ".join([p for p in x if p]), axis=1).str.strip(" -")
    df = df[["aparelho_full","AF1","AF2","AF3","AF4"]]
    return df

def compute_uc_by_floor(peso_andar_tidy: pd.DataFrame, pesos_uc: pd.DataFrame, aptos_por_andar: pd.DataFrame) -> pd.DataFrame:
    cat = normalize_peso_andar_table(peso_andar_tidy)
    pes = pesos_uc.set_index("aparelho_full")["peso_uc"]
    res_rows = []
    for andar, row in aptos_por_andar.iterrows():
        total_uc = 0.0
        for _, r in cat.iterrows():
            qtd = 0.0
            for af in ["AF1","AF2","AF3","AF4"]:
                qtd += (r.get(af,0.0) or 0.0) * (row.get(af,0.0) or 0.0)
            total_uc += qtd * float(pes.get(r["aparelho_full"], 1.0))
        res_rows.append({"andar": andar, "UC_total": total_uc})
    return pd.DataFrame(res_rows).set_index("andar")

def vazao_probavel_from_uc(uc: float, k: float, exp: float) -> float:
    if (uc or 0) <= 0: return 0.0
    return float(k * (uc**exp))
