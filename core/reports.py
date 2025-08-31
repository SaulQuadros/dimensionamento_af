import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

def export_to_excel(path_or_buf, trechos_calc: pd.DataFrame, params: dict):
    with pd.ExcelWriter(path_or_buf, engine='xlsxwriter') as xl:
        trechos_calc.to_excel(xl, sheet_name='Trechos', index=False)
        pd.DataFrame({k:[v] for k,v in params.items()}).to_excel(xl, sheet_name='Parametros', index=False)

def export_to_pdf(path_or_buf, trechos_calc: pd.DataFrame, params: dict):
    if hasattr(path_or_buf, 'write'):
        from reportlab.pdfgen.canvas import Canvas
        c = Canvas(path_or_buf, pagesize=A4)
    else:
        c = canvas.Canvas(path_or_buf, pagesize=A4)
    w, h = A4
    y = h - 2*cm
    c.setFont('Helvetica-Bold', 12)
    c.drawString(2*cm, y, 'Relatório – Dimensionamento de Água Fria (Simplificado)')
    y -= 0.8*cm
    c.setFont('Helvetica', 9)
    for k, v in params.items():
        c.drawString(2*cm, y, f'{k}: {v}'); y -= 0.5*cm
        if y < 3*cm:
            c.showPage(); y = h - 2*cm
    y -= 0.3*cm
    c.setFont('Helvetica-Bold', 10)
    c.drawString(2*cm, y, 'Trechos (resumo)')
    y -= 0.6*cm; c.setFont('Helvetica', 8)
    cols = trechos_calc.columns.tolist()[:12]
    for _, row in trechos_calc.iterrows():
        line = ', '.join([f'{col}={row[col]}' for col in cols])
        c.drawString(2*cm, y, line[:120]); y -= 0.4*cm
        if y < 3*cm:
            c.showPage(); y = h - 2*cm
    c.save()
