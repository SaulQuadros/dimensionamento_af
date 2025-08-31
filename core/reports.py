
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

def export_to_excel(path: str, trechos: pd.DataFrame, quadro: pd.DataFrame, uc_andar: pd.DataFrame, params: dict):
    with pd.ExcelWriter(path, engine="xlsxwriter") as xl:
        trechos.to_excel(xl, sheet_name="Trechos", index=False)
        quadro.to_excel(xl, sheet_name="Pressões", index=True)
        uc_andar.to_excel(xl, sheet_name="UC_por_andar", index=True)
        # params
        pd.DataFrame({k:[v] for k,v in params.items()}).to_excel(xl, sheet_name="Parametros", index=False)

def export_to_pdf(path: str, trechos: pd.DataFrame, quadro: pd.DataFrame, uc_andar: pd.DataFrame, params: dict):
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4
    y = h - 2*cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y, "Relatório – Dimensionamento de Água Fria")
    y -= 0.8*cm
    c.setFont("Helvetica", 9)
    # Params
    for k, v in params.items():
        c.drawString(2*cm, y, f"{k}: {v}")
        y -= 0.5*cm
        if y < 3*cm: c.showPage(); y = h - 2*cm
    # UC por andar
    y -= 0.3*cm
    c.setFont("Helvetica-Bold", 10); c.drawString(2*cm, y, "UC por andar")
    y -= 0.6*cm; c.setFont("Helvetica", 8)
    for idx, row in uc_andar.reset_index().iterrows():
        line = ", ".join([f"{col}={row[col]}" for col in uc_andar.reset_index().columns])
        c.drawString(2*cm, y, line[:110])
        y -= 0.4*cm
        if y < 3*cm: c.showPage(); y = h - 2*cm
    # Quadro de pressões
    y -= 0.3*cm
    c.setFont("Helvetica-Bold", 10); c.drawString(2*cm, y, "Pressões por pavimento")
    y -= 0.6*cm; c.setFont("Helvetica", 8)
    for idx, row in quadro.reset_index().iterrows():
        line = ", ".join([f"{col}={row[col]}" for col in quadro.reset_index().columns])
        c.drawString(2*cm, y, line[:110])
        y -= 0.4*cm
        if y < 3*cm: c.showPage(); y = h - 2*cm
    # Trechos (só primeiras N linhas para caber)
    y -= 0.3*cm
    c.setFont("Helvetica-Bold", 10); c.drawString(2*cm, y, "Trechos (resumo)")
    y -= 0.6*cm; c.setFont("Helvetica", 7.5)
    cols = trechos.columns.tolist()[:10]
    for idx, row in trechos[cols].head(40).iterrows():
        line = ", ".join([f"{col}={row[col]}" for col in cols])
        c.drawString(2*cm, y, line[:110])
        y -= 0.35*cm
        if y < 3*cm: c.showPage(); y = h - 2*cm
    c.save()
