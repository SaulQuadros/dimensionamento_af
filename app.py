import streamlit as st
import pandas as pd
import json
from io import BytesIO
from pathlib import Path

# ----------------- Utils -----------------
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
    try:
        return int(_num(x, default))
    except Exception:
        return default

def trecho_label(r):
    return f"{_s(r.get('ramo'))}-{_i(r.get('ordem'))} [{_s(r.get('de_no'))}→{_s(r.get('para_no'))}] id={_s(r.get('id'))}"

def load_tables():
    base = Path(__file__).parent
    pvc = pd.read_csv(base / 'pvc_perda_local_equivalente.csv')
    fofo = pd.read_csv(base / 'fofo_perda_local_equivalente.csv')
    return pvc, fofo

def get_dn_series(table):
    # pick the diameter column in mm
    for nm in table.columns:
        low = nm.lower()
        if ('de' in low or 'dn' in low or 'diam' in low) and 'mm' in low:
            return table[nm], nm
    return table.iloc[:, 0], table.columns[0]

def piece_columns_for(table):
    dn_series, dn_name = get_dn_series(table)
    cols = [c for c in table.columns if c not in (dn_name, 'dref_pol')]
    return cols, dn_name

def lookup_row(table, user_dn_mm):
    dn_series, dn_name = get_dn_series(table)
    try:
        dn_val = float(user_dn_mm)
    except Exception:
        dn_val = 0.0
    idx = (dn_series - dn_val).abs().idxmin()
    row = table.loc[idx]
    de_ref_mm = float(row.get(dn_name, 0) or 0)
    pol_ref = _s(row.get('dref_pol'))
    return row.to_dict(), de_ref_mm, pol_ref

def pretty(col):
    lbl = col
    if lbl.endswith('_m'):
        lbl = lbl[:-2]
    lbl = lbl.replace('_div_', '/').replace('_r_', ' R ')
    lbl = lbl.replace('_', ' ').strip().title()
    # ajustes de acentos e termos
    lbl = (lbl
           .replace('Te', 'Tê')
           .replace('Angulo', 'Ângulo')
           .replace('Pe', 'Pé')
           .replace('Canalizacao', 'Canalização')
           .replace('Borda', 'Borda')
           .replace('Gaveta', 'Gaveta')
           .replace('Globo', 'Globo')
           .replace('Retencao', 'Retenção')
    )
    return lbl

# ----------------- App -----------------
st.set_page_config(page_title='SPAF – L_eq por trecho (PVC/FoFo dinâmico)', layout='wide')
st.title('Dimensionamento – Barrilete e Colunas (L_eq por trecho, PVC/FoFo dinâmico)')

pvc_table, fofo_table = load_tables()

BASE_COLS = ['id','ramo','ordem','de_no','para_no','dn_mm','de_ref_mm','pol_ref','comp_real_m','delta_z_m','peso_trecho','leq_m']
DTYPES = {'id':'string','ramo':'string','ordem':'Int64','de_no':'string','para_no':'string',
          'dn_mm':'float','de_ref_mm':'float','pol_ref':'string',
          'comp_real_m':'float','delta_z_m':'float','peso_trecho':'float','leq_m':'float'}

with st.sidebar:
    st.header('Parâmetros Globais')
    projeto_nome = st.text_input('Nome do Projeto', 'Projeto Genérico')
    material_sistema = st.selectbox('Material do Sistema', ['(selecione)','PVC','FoFo'], index=0)
    k_uc  = st.number_input('k (Q = k·Peso^exp)', value=0.30, step=0.05, format='%.2f')
    exp_uc = st.number_input('exp (Q = k·Peso^exp)', value=0.50, step=0.05, format='%.2f')
    c_pvc = st.number_input('C (PVC)', value=150.0, step=5.0)
    c_fofo = st.number_input('C (Ferro Fundido)', value=130.0, step=5.0)
    H_res  = st.number_input('Nível do reservatório (m) – referência z=0', value=25.0, step=0.5)

if 'trechos' not in st.session_state:
    empty = {c: pd.Series(dtype=t) for c,t in DTYPES.items()}
    st.session_state['trechos'] = pd.DataFrame(empty)

tab1, tab2, tab3 = st.tabs(['1) Trechos','2) L_eq (por trecho)','3) Resultados & Exportar'])

with tab1:
    st.subheader('Cadastro de Trechos')
    if material_sistema == '(selecione)':
        st.warning('Escolha o **Material do Sistema** na barra lateral para habilitar.')
    with st.form('form_add', clear_on_submit=True):
        c1,c2,c3 = st.columns([1.2,1,1])
        id_val = c1.text_input('id (opcional)')
        ramo = c2.text_input('ramo', value='A')
        ordem = c3.number_input('ordem', min_value=1, step=1, value=1)
        c4,c5 = st.columns(2)
        de_no = c4.text_input('de_no', value='RS')
        para_no = c5.text_input('para_no', value='T1')
        c6,c7,c8 = st.columns(3)
        dn_mm = c6.number_input('dn_mm (mm, interno)', min_value=0.0, step=1.0, value=32.0)
        comp_real_m = c7.number_input('comp_real_m (m)', min_value=0.0, step=0.1, value=6.0, format='%.2f')
        delta_z_m = c8.number_input('delta_z_m (m)', step=0.1, value=0.0, format='%.2f')
        peso_trecho = st.number_input('peso_trecho (UC)', min_value=0.0, step=1.0, value=10.0, format='%.2f')
        ok = st.form_submit_button('➕ Adicionar trecho', disabled=(material_sistema=='(selecione)'))
    if ok:
        table_mat = pvc_table if material_sistema=='PVC' else fofo_table
        _row, de_ref_mm, pol_ref = lookup_row(table_mat, dn_mm)
        base = pd.DataFrame(st.session_state['trechos']).reindex(columns=BASE_COLS).copy()
        nova = {'id':id_val,'ramo':ramo,'ordem':int(ordem),'de_no':de_no,'para_no':para_no,
                'dn_mm':float(dn_mm),'de_ref_mm':float(de_ref_mm),'pol_ref':pol_ref,
                'comp_real_m':float(comp_real_m),'delta_z_m':float(delta_z_m),
                'peso_trecho':float(peso_trecho),'leq_m':0.0}
        base = pd.concat([base, pd.DataFrame([nova])], ignore_index=True)
        for c,t in DTYPES.items():
            try: base[c] = base[c].astype(t)
            except Exception: pass
        st.session_state['trechos'] = base
        st.success('Trecho adicionado! (DN ref. e polegadas preenchidos)')
    vis = pd.DataFrame(st.session_state['trechos']).reindex(columns=[c for c in BASE_COLS if c!='leq_m'])
    st.dataframe(vis, use_container_width=True, height=320)

with tab2:
    st.subheader('Comprimento Equivalente — editar por trecho')
    base = pd.DataFrame(st.session_state['trechos'])
    if base.empty:
        st.info('Cadastre trechos na aba 1.')
    elif material_sistema == '(selecione)':
        st.warning('Selecione o Material do Sistema na barra lateral.')
    else:
        table_mat = pvc_table if material_sistema=='PVC' else fofo_table
        piece_cols, dn_name = piece_columns_for(table_mat)
        # escolha do trecho
        base = base.copy()
        base['label'] = base.apply(trecho_label, axis=1)
        sel = st.selectbox('Selecione o trecho para preencher quantidades', base['label'].tolist())
        r = base[base['label']==sel].iloc[0]
        # linha do DN ref para este trecho
        eql_row, _, _ = lookup_row(table_mat, r.get('dn_mm'))
        # montar dataframe de edição (somente Qt., m fixo)
        display_labels = [pretty(c) for c in piece_cols]
        df = pd.DataFrame({
            'Conexão/Peça': display_labels,
            '(m)': [ _num(eql_row.get(c, 0.0), 0.0) for c in piece_cols ],
            '(Qt.)': [0]*len(piece_cols),
        })
        df = df.set_index('Conexão/Peça')
        edited = st.data_editor(
            df,
            use_container_width=True,
            num_rows='fixed',
            column_config={
                '(m)': st.column_config.NumberColumn(disabled=True, format='%.2f'),
                '(Qt.)': st.column_config.NumberColumn(min_value=0, step=1)
            },
            key=f'eq_editor_{sel}'
        )
        # calcular L_eq e aplicar
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

with tab3:
    st.subheader('Resultados & Exportar')
    t3 = pd.DataFrame(st.session_state.get('trechos', {}))
    if t3.empty:
        st.info('Cadastre trechos e atribua L_eq na aba 2.')
    else:
        t3 = t3.copy()
        # cálculos hidráulicos (esqueleto)
        def to_num_col(s): return pd.to_numeric(s.astype(str).str.replace(',', '.', regex=False), errors='coerce')
        for col in ['peso_trecho','dn_mm','de_ref_mm','comp_real_m','delta_z_m','leq_m']:
            t3[col] = to_num_col(t3.get(col,0)).fillna(0.0)
        # Vazão provável (parâmetros locais para simplicidade)
        k_local = 0.30; exp_local = 0.50
        t3['Q (L/s)'] = k_local * (t3['peso_trecho'] ** exp_local)
        # Placeholders para perdas (substitua por sua função oficial se preferir)
        t3['J (m/m)'] = 1e-3 * ( (t3['Q (L/s)'] / t3['dn_mm'].replace(0,1)) ** 1.0 )
        t3['hf_continua (mca)'] = (t3['J (m/m)'] * t3['comp_real_m']).astype(float)
        t3['hf_local (mca)'] = (t3['J (m/m)'] * t3['leq_m']).astype(float)
        t3['hf_total (mca)'] = t3['hf_continua (mca)'] + t3['hf_local (mca)']
        t3 = t3.sort_values(by=['ramo','ordem'], na_position='last')
        t3['hf_acum_ramo (mca)'] = t3.groupby('ramo')['hf_total (mca)'].cumsum()
        t3['z_acum_ramo (m)'] = t3.groupby('ramo')['delta_z_m'].cumsum()
        H_res = 25.0
        t3['P_disp_final (mca)'] = (H_res - t3['z_acum_ramo (m)']) - t3['hf_acum_ramo (mca)']
        st.dataframe(t3, use_container_width=True, height=460)

        params = {'projeto': projeto_nome, 'material': material_sistema}
        proj = {'params': params, 'trechos': t3.to_dict(orient='list')}
        st.download_button('Baixar projeto (.json)',
                           data=json.dumps(proj, ensure_ascii=False, indent=2).encode('utf-8'),
                           file_name='spaf_projeto.json', mime='application/json')
