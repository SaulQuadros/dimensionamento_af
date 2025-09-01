
import streamlit as st
import pandas as pd
import unicodedata

def _material_key(x: str) -> str:
    # normalize accents and case
    if not isinstance(x, str):
        return 'PVC'
    y = ''.join(c for c in unicodedata.normalize('NFKD', x) if not unicodedata.combining(c)).lower().strip()
    # common aliases
    if 'fofo' in y or 'ferro' in y or 'fundido' in y:
        return 'FoFo'
    return 'PVC'

import json
from pathlib import Path

# ----------------- Constants -----------------
KPA_PER_M = 9.80665  # 1 m.c.a. ≈ 9.80665 kPa

# ----------------- Small helpers -----------------
def _s(x):
    try:
        if pd.isna(x): return ''
    except Exception:
        pass
    return '' if x is None else str(x)

def _num(x, default=0.0):
    try:
        if pd.isna(x): return default
    except Exception:
        pass
    try:
        return float(str(x).replace(',', '.'))
    except Exception:
        return default

def _i(x, default=0):
    try: return int(_num(x, default))
    except Exception: return default

def trecho_label(r):
    return f"{_s(r.get('ramo'))}-{_i(r.get('ordem'))} [{_s(r.get('de_no'))}→{_s(r.get('para_no'))}] id={_s(r.get('id'))}"

# ----------------- Tables -----------------
def load_tables():
    base = Path(__file__).parent
    pvc = pd.read_csv(base / 'data/pvc_pl_eqlen.csv')
    fofo = pd.read_csv(base / 'data/fofo_pl_eqlen.csv')
    return pvc, fofo

def get_dn_series(table):
    for nm in table.columns:
        low = nm.lower()
        if ('de' in low or 'dn' in low or 'diam' in low) and 'mm' in low:
            return table[nm], nm
    return table.iloc[:, 0], table.columns[0]

def piece_columns_for(table):
    dn_series, dn_name = get_dn_series(table)
    cols = [c for c in table.columns if c not in (dn_name, 'dref_pol')]
    return cols, dn_name

def lookup_row_by_mm(table, ref_mm):
    dn_series, dn_name = get_dn_series(table)
    try: x = float(ref_mm)
    except Exception: x = 0.0
    idx = (dn_series - x).abs().idxmin()
    row = table.loc[idx]
    de_ref_mm = float(row.get(dn_name, 0) or 0)
    pol_ref = _s(row.get('dref_pol'))
    return row.to_dict(), de_ref_mm, pol_ref

def pretty(col):
    lbl = col
    if lbl.endswith('_m'): lbl = lbl[:-2]
    lbl = lbl.replace('_div_', '/').replace('_r_', ' R ')
    lbl = lbl.replace('_', ' ').strip().title()
    lbl = (lbl
           .replace('Te', 'Tê')
           .replace('Angulo', 'Ângulo')
           .replace('Pe', 'Pé')
           .replace('Canalizacao', 'Canalização')
           .replace('Retencao', 'Retenção')
    )
    return lbl

# ----------------- Headloss models -----------------

def j_fair_whipple_hsiao_kPa_per_m(Q_Ls, D_mm, material: str):
    Q = max(0.0, _num(Q_Ls, 0.0))
    D = max(0.0, _num(D_mm, 0.0))
    if D <= 0.0:
        return 0.0
    mat = (material or '').strip().lower()
    if mat == 'pvc':
        return 8.695e6 * (Q ** 1.75) / (D ** 4.75)
    else:
        return 20.2e6  * (Q ** 1.88) / (D ** 4.88)

def j_hazen_williams(Q_Ls, D_mm, C):
    # Q in L/s -> m3/s ; D in mm -> m ; J in m/m
    Q = max(0.0, _num(Q_Ls, 0.0)) / 1000.0
    D = max(0.0, _num(D_mm, 0.0)) / 1000.0
    if D <= 0.0 or C <= 0.0: return 0.0
    return 10.67 * (Q ** 1.852) / ( (C ** 1.852) * (D ** 4.87) )

def j_fair_whipple_hsiao(Q_Ls, D_mm):
    # Provided form, already for Q in L/s and D in mm ; J in m/m
    Q = max(0.0, _num(Q_Ls, 0.0))
    D = max(0.0, _num(D_mm, 0.0))
    if D <= 0.0: return 0.0
    return 20.2e6 * (Q ** 1.88) / (D ** 4.88)

# ----------------- App -----------------
st.set_page_config(page_title='SPAF – kPa + HW/FWH + L_eq por DN ref. + P(A)', layout='wide')
st.title('Dimensionamento – Barrilete e Colunas (kPa • Hazen-Williams / Fair-Whipple-Hsiao • Nível do Reservatório)')

pvc_table, fofo_table = load_tables()

BASE_COLS = ['id','ramo','ordem','de_no','para_no','dn_mm','de_ref_mm','pol_ref','comp_real_m','dz_io_m','peso_trecho','leq_m','p_min_ref_kPa']
DTYPES = {'id':'string','ramo':'string','ordem':'Int64','de_no':'string','para_no':'string',
          'dn_mm':'float','de_ref_mm':'float','pol_ref':'string',
          'comp_real_m':'float','dz_io_m':'float','peso_trecho':'float','leq_m':'float','p_min_ref_kPa':'float'}

with st.sidebar:
    st.header('Parâmetros Globais')
    projeto_nome = st.text_input('Nome do Projeto', 'Projeto Genérico')
    material_sistema = st.selectbox('Material do Sistema', ['(selecione)','PVC','FoFo'], index=0)
    modelo_perda = st.radio('Modelo de perda contínua', ['Hazen-Williams','Fair-Whipple-Hsiao'], index=0)
    # UC -> Q provável
    k_uc  = st.number_input('k (Q = k·Peso^exp)', value=0.30, step=0.05, format='%.2f')
    exp_uc = st.number_input('exp (Q = k·Peso^exp)', value=0.50, step=0.05, format='%.2f')
    # Coeficientes C por material (HW)
    c_pvc = st.number_input('C (PVC)', value=150.0, step=5.0)
    c_fofo = st.number_input('C (Ferro Fundido)', value=130.0, step=5.0)
    # Reservatório: Hmax / Hmin e nível de operação
    st.markdown('**Nível do Reservatório (m)**')
    H_max = st.number_input("H_max (espelho d'água no nível cheio)", value=25.0, step=0.5)
    H_min = st.number_input('H_min (mínimo com água no ponto)', value=0.0, step=0.5)
    frac = st.slider('Nível operacional (0 = H_min, 1 = H_max)', 0.0, 1.0, value=1.0)
    H_res = H_min + frac * (H_max - H_min)
    st.metric('p_in em A (kPa)', f'{H_res * KPA_PER_M:,.2f}')

if 'trechos' not in st.session_state:
    empty = {c: pd.Series(dtype=t) for c,t in DTYPES.items()}
    st.session_state['trechos'] = pd.DataFrame(empty)

tab1, tab2, tab3 = st.tabs(['1) Trechos','2) L_eq (por trecho)','3) Resultados & Exportar'])

# TAB 1 — cadastro
with tab1:
    st.subheader('Cadastro de Trechos (DN interno informado; DN **referencial** vem do material)')
    if material_sistema == '(selecione)':
        st.warning('Escolha o **Material do Sistema** na barra lateral para habilitar.')
    with st.form('form_add', clear_on_submit=True):
        c1,c2,c3 = st.columns([1.2,1,1])
        id_val = c1.text_input('id (opcional)')
        ramo = c2.text_input('ramo', value='A')
        ordem = c3.number_input('ordem', min_value=1, step=1, value=1)
        c4,c5 = st.columns(2)
        de_no = c4.text_input('de_no', value='A')
        para_no = c5.text_input('para_no', value='B')
        c6,c7,c8 = st.columns(3)
        dn_mm = c6.number_input('dn_mm (mm, interno)', min_value=0.0, step=1.0, value=32.0)
        comp_real_m = c7.number_input('comp_real_m (m)', min_value=0.0, step=0.1, value=6.0, format='%.2f')
        dz_io_m = c8.number_input('dz_io_m (m) [z_inicial - z_final]', step=0.1, value=0.0, format='%.2f')
        peso_trecho = st.number_input('peso_trecho (UC)', min_value=0.0, step=1.0, value=10.0, format='%.2f')
        c9,c10 = st.columns([1,1])
        tipo_ponto = c9.selectbox('Tipo do ponto no final do trecho', ['Sem utilização (5 kPa)','Ponto de utilização (10 kPa)'])
        pmin_default = 5.0 if 'Sem utilização' in tipo_ponto else 10.0
        p_min_ref_kPa = c10.number_input('p_min_ref (kPa)', min_value=0.0, step=0.5, value=pmin_default, format='%.2f')
        ok = st.form_submit_button('➕ Adicionar trecho', disabled=(material_sistema=='(selecione)'))
    if ok:
        mat_key = _material_key(material_sistema)
        table_mat = pvc_table if mat_key=='PVC' else fofo_table
        st.caption(f'Tabela L_eq em uso: **{mat_key}**')
        _row, de_ref_mm, pol_ref = lookup_row_by_mm(table_mat, dn_mm)
        base = pd.DataFrame(st.session_state['trechos']).reindex(columns=BASE_COLS).copy()
        nova = {'id':id_val,'ramo':ramo,'ordem':int(ordem),'de_no':de_no,'para_no':para_no,
                'dn_mm':float(dn_mm),'de_ref_mm':float(de_ref_mm),'pol_ref':pol_ref,
                'comp_real_m':float(comp_real_m),'dz_io_m':float(dz_io_m),
                'peso_trecho':float(peso_trecho),'leq_m':0.0,'p_min_ref_kPa':float(p_min_ref_kPa)}
        base = pd.concat([base, pd.DataFrame([nova])], ignore_index=True)
        for c,t in DTYPES.items():
            try: base[c] = base[c].astype(t)
            except Exception: pass
        st.session_state['trechos'] = base
        st.success('Trecho adicionado! DN referencial (nominal/externo) e "Dref Pol" preenchidos.')
    vis = pd.DataFrame(st.session_state['trechos']).reindex(columns=[c for c in BASE_COLS if c!='leq_m'])
    st.dataframe(vis, use_container_width=True, height=320)

# TAB 2 — L_eq por trecho (baseado no DN referencial)
with tab2:
    st.subheader('Comprimento Equivalente — editar por trecho (baseado no DN **referencial**)')
    base = pd.DataFrame(st.session_state['trechos'])
    if base.empty:
        st.info('Cadastre trechos na aba 1.')
    elif material_sistema == '(selecione)':
        st.warning('Selecione o Material do Sistema na barra lateral.')
    else:
        mat_key = _material_key(material_sistema)
        table_mat = pvc_table if mat_key=='PVC' else fofo_table
        st.caption(f'Tabela L_eq em uso: **{mat_key}**')
        piece_cols, dn_name = piece_columns_for(table_mat)
        base = base.copy()
        base['label'] = base.apply(trecho_label, axis=1)
        sel = st.selectbox('Selecione o trecho para preencher quantidades', base['label'].tolist())
        r = base[base['label']==sel].iloc[0]
        dn_ref = r.get('de_ref_mm') or r.get('dn_mm')
        eql_row, _, _ = lookup_row_by_mm(table_mat, dn_ref)
        display_labels = [pretty(c) for c in piece_cols]
        df = pd.DataFrame({
            'Conexão/Peça': display_labels,
            '(m)': [ _num(eql_row.get(c, 0.0), 0.0) for c in piece_cols ],
            '(Qt.)': [0]*len(piece_cols),
        }).set_index('Conexão/Peça')
        edited = st.data_editor(
            df,
            use_container_width=True,
            num_rows='fixed',
            column_config={
                '(m)': st.column_config.NumberColumn(disabled=True, format='%.2f'),
                '(Qt.)': st.column_config.NumberColumn(min_value=0, step=1)
            },
            key=f'eq_editor_{mat_key}_{sel}'
        )
        if st.button('Aplicar L_eq ao trecho selecionado'):
            dfe = pd.DataFrame(edited)
            L = float((dfe['(m)'] * dfe['(Qt.)']).fillna(0).sum())
            base2 = pd.DataFrame(st.session_state['trechos']).copy()
            idx = base2[base2.apply(trecho_label, axis=1)==sel].index
            if len(idx)>0:
                base2.loc[idx[0], 'leq_m'] = L
                st.session_state['trechos'] = base2
                st.success(f'L_eq aplicado ao trecho {sel}: {L:.2f} m')
            st.metric('L_eq do trecho (m)', f'{L:.2f}')

# TAB 3 — resultados (kPa) com J em kPa/m e propagação P_in -> P_out
with tab3:
    st.subheader('Resultados (kPa) — com J em kPa/m e pressão inicial no ponto A')
    st.caption('Fórmula: **p_out = p_in + γ·(z_i − z_f) − h_f^cont − h_f^loc**; γ = 9,80665 kPa/m')
    t3 = pd.DataFrame(st.session_state.get('trechos', {}))
    if t3.empty:
        st.info('Cadastre trechos e atribua L_eq na aba 2.')
    else:
        t3 = t3.copy()
        # Q provável (L/s)
        t3['Q (L/s)'] = _num(0, 0) + (k_uc * (t3['peso_trecho'] ** exp_uc))
        # Gradiente J (kPa/m)
        def _J_kPa(rr):
            if modelo_perda == 'Hazen-Williams':
                C = c_pvc if material_sistema=='PVC' else c_fofo
                j_mm = j_hazen_williams(rr['Q (L/s)'], rr['dn_mm'], C)
                return j_mm * KPA_PER_M
            else:
                return j_fair_whipple_hsiao_kPa_per_m(rr['Q (L/s)'], rr['dn_mm'], material_sistema)
        t3['J (kPa/m)'] = t3.apply(_J_kPa, axis=1)
        t3['J (m/m)']   = t3['J (kPa/m)'] / KPA_PER_M
        import math
        def _vel(rr):
            Q = max(0.0, _num(rr['Q (L/s)'],0.0)) / 1000.0
            D = max(0.0, _num(rr['dn_mm'],0.0)) / 1000.0
            if D <= 0 or Q <= 0: return 0.0
            A = math.pi * D*D / 4.0
            return Q / A
        t3['v (m/s)'] = t3.apply(_vel, axis=1)

        # Opção de ordenação (padrão = manter a ordem de cadastro dos trechos)
        ordenar = st.checkbox('Ordenar por ramo/ordem (ascendente)', value=False, help='Quando desligado, os resultados seguem a mesma ordem mostrada em "Trechos".')
        if ordenar:
            # sort estável para evitar embaralhar empates de ordem
            t3 = t3.sort_values(by=['ramo','ordem'], kind='mergesort', na_position='last').reset_index(drop=True)

        # Propagação por ramo: P_in -> perdas -> P_out, preservando a ordem atual da tabela
        results = []
        for ramo, grp in t3.groupby('ramo', sort=False):
            P_in = H_res * KPA_PER_M  # pressão inicial do ramo (ponto A)
            for _, r in grp.iterrows():
                J_kPa_m = _num(r['J (kPa/m)'])
                hf_cont = J_kPa_m * _num(r['comp_real_m'])
                hf_loc  = J_kPa_m * _num(r['leq_m'])
                p_disp  = KPA_PER_M * _num(r.get('dz_io_m', 0.0))
                p_out   = p_in + p_disp - hf_cont - hf_loc
                row = r.to_dict()
                row.update({
                    'p_in (kPa)': p_in,
                    'hf_cont (kPa)': hf_cont,
                    'hf_loc (kPa)': hf_loc,
                    'p_disp (kPa)': p_disp,
                    'p_out (kPa)': p_out,
                })
                results.append(row)
                P_in = P_out  # próximo trecho inicia com a pressão de saída deste
        t_out = pd.DataFrame(results)

        show_cols = ['id','ramo','ordem','de_no','para_no','dn_mm','de_ref_mm','pol_ref','comp_real_m','dz_io_m',
                     'peso_trecho','leq_m','Q (L/s)','v (m/s)','J (kPa/m)',
                     'P_in (kPa)','hf_cont (kPa)','hf_loc (kPa)','hf_alt (kPa)','P_out (kPa)']
        st.dataframe(t_out[show_cols], use_container_width=True, height=520)

        # Export JSON com parâmetros + tabela final
        params = {'projeto': projeto_nome, 'material': material_sistema, 'modelo_perda': modelo_perda,
                  'k_uc': k_uc, 'exp_uc': exp_uc, 'C_PVC': c_pvc, 'C_FoFo': c_fofo,
                  'H_max_m': H_max, 'H_min_m': H_min, 'H_op_m': H_res, 'KPA_PER_M': KPA_PER_M}
        proj = {'params': params, 'trechos': t_out[show_cols].to_dict(orient='list')}
        st.download_button('Baixar projeto (.json)',
                           data=json.dumps(proj, ensure_ascii=False, indent=2).encode('utf-8'),
                           file_name='spaf_projeto.json', mime='application/json')
