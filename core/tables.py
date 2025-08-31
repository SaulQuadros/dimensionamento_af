import pandas as pd

def load_eqlen_tables(pvc_csv='data/pvc_pl_eqlen.csv', fofo_csv='data/fofo_pl_eqlen.csv'):
    pvc = pd.read_csv(pvc_csv)
    fofo = pd.read_csv(fofo_csv)
    return pvc, fofo

TIPOS_PECAS = [
    ('joelho_90_m', 'Joelho 90°'),
    ('joelho_45_m', 'Joelho 45°'),
    ('curva_90_m', 'Curva 90°'),
    ('curva_45_m', 'Curva 45°'),
    ('te_passagem_direita_m', 'Tê 90° Passagem Direita'),
    ('te_saida_de_lado_m', 'Tê 90° Saída de Lado'),
    ('te_saida_bilateral_m', 'Tê 90° Saída Bilateral'),
    ('entrada_normal_m', 'Entrada Normal'),
    ('entrada_de_borda_m', 'Entrada de Borda'),
    ('saida_de_canalizacao_m', 'Saída de Canalização'),
    ('valvula_pe_crivo_m', 'Válvula de Pé e Crivo'),
    ('valvula_retencao_leve_m', 'Válvula de Retenção (Leve)'),
    ('valvula_retencao_pesado_m', 'Válvula de Retenção (Pesado)'),
    ('registro_globo_aberto_m', 'Registro de Globo (aberto)'),
    ('registro_gaveta_aberto_m', 'Registro de Gaveta (aberto)'),
    ('registro_angulo_aberto_m', 'Registro de Ângulo (aberto)'),
]

def row_for(material: str, dn_mm: float, pvc, fofo) -> dict:
    table = pvc if (material or '').lower() == 'pvc' else fofo
    try:
        dn = float(dn_mm)
    except Exception:
        return None
    idx = int((table['de_mm'] - dn).abs().idxmin())
    row = table.loc[idx].to_dict()
    out = {}
    for key, _label in TIPOS_PECAS:
        out[key] = row.get(key, 0)
    return out

def options_for_editor():
    return [label for _key, label in TIPOS_PECAS]

def key_from_label(label: str):
    for key, lab in TIPOS_PECAS:
        if lab == label:
            return key
    return None
