import streamlit as st
import pandas as pd
import json
from io import BytesIO
from core.losses import hazen_williams_j, comprimento_equivalente_total
from core.tables import load_eqlen_tables, options_for_editor, key_from_label, row_for
from core.reports import export_to_excel, export_to_pdf

st.set_page_config(page_title='SPAF – Simplificado (Formulário)', layout='wide')
st.title('Dimensionamento de Tubulações de Água Fria — Barrilete e Colunas (Modo Formulário)')

# ---------------- Helpers ----------------
BASE_COLS = ['id','ramo','ordem','de_no','para_no','material','dn_mm','comp_real_m','delta_z_m','peso_trecho','leq_m']
DTYPES = {
    'id': 'string', 'ramo': 'string', 'ordem': 'Int64',
    'de_no': 'string', 'para_no': 'string', 'material': 'string',
    'dn_mm': 'float', 'comp_real_m': 'float', 'delta_z_m': 'float',
    'peso_trecho': 'float', 'leq_m': 'float'
}
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

# ---------------- Sidebar ----------------
with st.sidebar:
    st.header('Parâmetros Globais')
    projeto_nome = st.text_input('Nome do Projeto', 'Projeto Genérico')
    k_uc  = st.number_input('k (Q = k·Peso^exp)', value=0.30, step=0.05, format='%.2f')
    exp_uc = st.number_input('exp (Q = k·Peso^exp)', value=0.50, step=0.05, format='%.2f')
    c_pvc = st.number_input('C (PVC)', value=150.0, step=5.0)
    c_fofo = st.number_input('C (Ferro Fundido)', value=130.0, step=5.0)
    H_res  = st.number_input('Nível do reservatório (m) – referência z=0', value=25.0, step=0.5)

pvc_table, fofo_table = load_eqlen_tables()
pecas_labels = options_for_editor()

tab1, tab2, tab3 = st.tabs(['1) Trechos (Formulário)','2) Peças por Trecho','3) Resultados & Exportar'])

# ---------------- Session state init ----------------
if 'trechos' not in st.session_state:
    empty = {c: pd.Series(dtype=t) for c, t in DTYPES.items()}
    st.session_state['trechos'] = pd.DataFrame(empty)
if 'detalhes' not in st.session_state:
    st.session_state['detalhes'] = {}

# ---------------- Tab 1: Trechos (Form) ----------------
with tab1:
    st.subheader('Cadastro de Trechos — por Formulário')
    st.caption('Preencha todos os campos do trecho e clique **Adicionar trecho**. Sem edição inline para evitar perda de dados na primeira digitação.')

    with st.form('form_add_trecho', clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([1.2,1,1,1])
        with c1:
            id_val = st.text_input('id (opcional)')
        with c2:
            ramo = st.text_input('ramo', value='A')
        with c3:
            ordem = st.number_input('ordem', min_value=1, step=1, value=1)
        with c4:
            material = st.selectbox('material', ['PVC','FoFo'], index=0)

        c5, c6, c7 = st.columns(3)
        with c5:
            de_no = st.text_input('de_no', value='RS')
        with c6:
            para_no = st.text_input('para_no', value='T1')
        with c7:
            dn_mm = st.number_input('dn_mm (mm, interno)', min_value=0.0, step=1.0, value=32.0)

        c8, c9, c10 = st.columns(3)
        with c8:
            comp_real_m = st.number_input('comp_real_m (m)', min_value=0.0, step=0.1, value=6.0, format='%.2f')
        with c9:
            delta_z_m = st.number_input('delta_z_m (m)', step=0.1, value=0.0, format='%.2f', help='Positivo quando sobe; negativo quando desce.')
        with c10:
            peso_trecho = st.number_input('peso_trecho (UC)', min_value=0.0, step=1.0, value=10.0, format='%.2f')

        add_ok = st.form_submit_button('➕ Adicionar trecho')

    if add_ok:
        base = pd.DataFrame(st.session_state['trechos']).reindex(columns=BASE_COLS).copy()
        nova = {
            'id': id_val, 'ramo': ramo, 'ordem': int(ordem),
            'de_no': de_no, 'para_no': para_no, 'material': material,
            'dn_mm': float(dn_mm), 'comp_real_m': float(comp_real_m), 'delta_z_m': float(delta_z_m),
            'peso_trecho': float(peso_trecho), 'leq_m': 0.0
        }
        base = pd.concat([base, pd.DataFrame([nova])], ignore_index=True)
        # enforce dtypes
        for c, t in DTYPES.items():
            try: base[c] = base[c].astype(t)
            except Exception: pass
        st.session_state['trechos'] = base
        st.success('Trecho adicionado!')

    # Visualização (somente leitura)
    vis = pd.DataFrame(st.session_state['trechos']).reindex(columns=BASE_COLS).copy()
    if not vis.empty:
        vis_show = vis.copy()
        st.dataframe(vis_show, use_container_width=True, height=360)
        # Excluir linha
        vis['_label'] = vis.apply(lambda r: f"{_s(r.get('ramo'))}-{_i(r.get('ordem'))} [{_s(r.get('de_no'))}→{_s(r.get('para_no'))}] id={_s(r.get('id'))}", axis=1)
        col_del1, col_del2 = st.columns([3,1])
        with col_del1:
            to_del = st.selectbox('Excluir trecho (opcional): selecione', ['(nenhum)'] + vis['_label'].tolist())
        with col_del2:
            if st.button('🗑️ Excluir selecionado', use_container_width=True) and to_del != '(nenhum)':
                idx = vis[vis['_label']==to_del].index
                if len(idx)>0:
                    base = pd.DataFrame(st.session_state['trechos']).copy()
                    base = base.drop(index=idx[0]).reset_index(drop=True)
                    st.session_state['trechos'] = base
                    st.success('Trecho excluído.')

# ---------------- Tab 2: Peças por trecho ----------------
with tab2:
    st.subheader('Peças/Acessórios por Trecho (L_eq)')
    st.caption('Selecione um trecho e informe **somente as quantidades**. Clique **Aplicar L_eq** para gravar no trecho.')

    tre = pd.DataFrame(st.session_state.get('trechos', {})).reindex(columns=BASE_COLS)
    if tre.empty:
        st.warning('Cadastre trechos na aba 1.')
    else:
        tre = tre.copy()
        tre['label'] = tre.apply(lambda r: f"{_s(r.get('ramo'))}-{_i(r.get('ordem'))} [{_s(r.get('de_no'))}→{_s(r.get('para_no'))}] id={_s(r.get('id'))}", axis=1)
        sel = st.selectbox('Trecho', tre['label'].tolist())
        r = tre[tre['label']==sel].iloc[0]
        trecho_key = str(_s(r.get('id')) or f"{_s(r.get('ramo'))}-{_i(r.get('ordem'))}")

        if trecho_key not in st.session_state['detalhes']:
            st.session_state['detalhes'][trecho_key] = pd.DataFrame({'peca':[pecas_labels[0]], 'quantidade':[0]})

        df_det = st.data_editor(
            st.session_state['detalhes'][trecho_key],
            num_rows='dynamic',
            use_container_width=True,
            hide_index=True,
            column_config={
                'peca': st.column_config.SelectboxColumn(options=pecas_labels, required=True),
                'quantidade': st.column_config.NumberColumn(min_value=0, step=1),
            },
            key=f'det_{trecho_key}'
        )
        st.session_state['detalhes'][trecho_key] = df_det

        material = (_s(r.get('material')) or 'PVC')
        dn = _num(r.get('dn_mm'), 0.0)
        eqlen_row = row_for(material, dn, pvc_table, fofo_table)
        det_list = [{'tipo': key_from_label(rr['peca']), 'quantidade': rr['quantidade']} for _, rr in df_det.iterrows()]
        L_eq = comprimento_equivalente_total(eqlen_row, det_list)
        st.metric('Comprimento equivalente do trecho (m)', f'{L_eq:.2f}')

        if st.button('Aplicar L_eq ao trecho selecionado', key=f'apply_{trecho_key}'):
            base = pd.DataFrame(st.session_state['trechos']).reindex(columns=BASE_COLS).copy()
            base['label'] = base.apply(lambda x: f"{_s(x.get('ramo'))}-{_i(x.get('ordem'))} [{_s(x.get('de_no'))}→{_s(x.get('para_no'))}] id={_s(x.get('id'))}", axis=1)
            idx = base[base['label']==sel].index
            if len(idx)>0:
                base.loc[idx[0], 'leq_m'] = float(L_eq)
                base = base.drop(columns=['label']).reindex(columns=BASE_COLS)
                for c, t in DTYPES.items():
                    try: base[c] = base[c].astype(t)
                    except Exception: pass
                st.session_state['trechos'] = base
                st.success('L_eq aplicado ao trecho.')

# ---------------- Tab 3: Resultados & Exportar ----------------
with tab3:
    st.subheader('Resultados & Exportação')
    t3 = pd.DataFrame(st.session_state.get('trechos', {})).reindex(columns=BASE_COLS)
    if t3.empty:
        st.info('Cadastre trechos (aba 1) e, opcionalmente, defina L_eq (aba 2).')
    else:
        t3 = t3.copy()

        # Sanitização numérica (aceita vírgula)
        def to_num_col(s):
            return pd.to_numeric(s.astype(str).str.replace(',', '.', regex=False), errors='coerce')

        for col in ['peso_trecho', 'dn_mm', 'comp_real_m', 'delta_z_m', 'leq_m']:
            t3[col] = to_num_col(t3.get(col, 0)).fillna(0.0)

        # Q provável (vetorizado)
        t3['Q (L/s)'] = k_uc * (t3['peso_trecho'] ** exp_uc)

        # J de Hazen-Williams
        def C(m): return c_pvc if (m or '').lower()=='pvc' else c_fofo
        t3['J (m/m)'] = t3.apply(lambda rr: hazen_williams_j(rr['Q (L/s)'], rr['dn_mm'], C(rr.get('material'))), axis=1)

        # Perdas
        t3['hf_continua (mca)'] = (t3['J (m/m)'] * t3['comp_real_m']).astype(float)
        t3['hf_local (mca)']    = (t3['J (m/m)'] * t3['leq_m']).astype(float)
        t3['hf_total (mca)']    = t3['hf_continua (mca)'] + t3['hf_local (mca)']

        # Acúmulos por ramo/ordem
        t3 = t3.sort_values(by=['ramo','ordem'], na_position='last')
        t3['hf_acum_ramo (mca)'] = t3.groupby('ramo')['hf_total (mca)'].cumsum()
        t3['z_acum_ramo (m)']    = t3.groupby('ramo')['delta_z_m'].cumsum()

        # Pressão disponível
        t3['P_disp_final (mca)'] = (H_res - t3['z_acum_ramo (m)']) - t3['hf_acum_ramo (mca)']

        st.dataframe(t3, use_container_width=True, height=460)

        # Export
        params = {'projeto': projeto_nome, 'k_uc': k_uc, 'exp_uc': exp_uc, 'c_pvc': c_pvc, 'c_fofo': c_fofo, 'H_res': H_res}
        proj = {'params': params, 'trechos': t3.to_dict(orient='list')}
        st.download_button('Baixar projeto (.json)', data=json.dumps(proj, ensure_ascii=False, indent=2).encode('utf-8'),
                           file_name='spaf_projeto.json', mime='application/json')
        biox = BytesIO(); export_to_excel(biox, t3, params)
        st.download_button('Baixar Excel (.xlsx)', data=biox.getvalue(), file_name='spaf_relatorio.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        biop = BytesIO(); export_to_pdf(biop, t3, params)
        st.download_button('Baixar PDF (.pdf)', data=biop.getvalue(), file_name='spaf_relatorio.pdf', mime='application/pdf')
