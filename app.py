import streamlit as st
import pandas as pd
import json
from io import BytesIO
from core.losses import hazen_williams_j, comprimento_equivalente_total
from core.tables import load_eqlen_tables, TIPOS_PECAS, key_from_label, row_for
from core.reports import export_to_excel, export_to_pdf

st.set_page_config(page_title='SPAF – Modo Formulário + Matriz L_eq', layout='wide')
st.title('Dimensionamento de Tubulações de Água Fria — Barrilete e Colunas (Form + Matriz L_eq)')

# ---------- Helpers ----------
BASE_COLS = ['id','ramo','ordem','de_no','para_no','dn_mm','comp_real_m','delta_z_m','peso_trecho','leq_m']
DTYPES = {
    'id':'string','ramo':'string','ordem':'Int64','de_no':'string','para_no':'string',
    'dn_mm':'float','comp_real_m':'float','delta_z_m':'float','peso_trecho':'float','leq_m':'float'
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

def trecho_label(r):
    return f"{_s(r.get('ramo'))}-{_i(r.get('ordem'))} [{_s(r.get('de_no'))}→{_s(r.get('para_no'))}] id={_s(r.get('id'))}"

# ---------- Sidebar (global params) ----------
with st.sidebar:
    st.header('Parâmetros Globais')
    projeto_nome = st.text_input('Nome do Projeto', 'Projeto Genérico')
    material_sistema = st.selectbox('Material do Sistema', ['(selecione)', 'PVC', 'FoFo'], index=0,
                                    help='Define o material para TODOS os trechos (barrilete/colunas).')
    k_uc  = st.number_input('k (Q = k·Peso^exp)', value=0.30, step=0.05, format='%.2f')
    exp_uc = st.number_input('exp (Q = k·Peso^exp)', value=0.50, step=0.05, format='%.2f')
    c_pvc = st.number_input('C (PVC)', value=150.0, step=5.0)
    c_fofo = st.number_input('C (Ferro Fundido)', value=130.0, step=5.0)
    H_res  = st.number_input('Nível do reservatório (m) – referência z=0', value=25.0, step=0.5)

pvc_table, fofo_table = load_eqlen_tables()
pecas_labels = [lab for _k, lab in TIPOS_PECAS]

# ---------- Session init ----------
if 'trechos' not in st.session_state:
    empty = {c: pd.Series(dtype=t) for c,t in DTYPES.items()}
    st.session_state['trechos'] = pd.DataFrame(empty)
if 'eq_qty' not in st.session_state:
    st.session_state['eq_qty'] = {}  # {trecho_label: {peca_key: quantidade}}

tab1, tab2, tab3 = st.tabs(['1) Trechos (Form)','2) Matriz de L_eq (por trecho)','3) Resultados & Exportar'])

# ---------- Tab 1: Trechos (Form) ----------
with tab1:
    st.subheader('Cadastro de Trechos — por Formulário')
    st.caption('O material é **global** (sidebar). Preencha o trecho e clique **Adicionar**.')

    disabled_add = (material_sistema == '(selecione)')
    if disabled_add:
        st.warning('Escolha o **Material do Sistema** na sidebar para habilitar o cadastro.')

    with st.form('form_add_trecho', clear_on_submit=True):
        c1, c2, c3 = st.columns([1.2,1,1])
        with c1: id_val = st.text_input('id (opcional)')
        with c2: ramo = st.text_input('ramo', value='A')
        with c3: ordem = st.number_input('ordem', min_value=1, step=1, value=1)

        c4, c5 = st.columns(2)
        with c4: de_no = st.text_input('de_no', value='RS')
        with c5: para_no = st.text_input('para_no', value='T1')

        c6, c7, c8 = st.columns(3)
        with c6: dn_mm = st.number_input('dn_mm (mm, interno)', min_value=0.0, step=1.0, value=32.0)
        with c7: comp_real_m = st.number_input('comp_real_m (m)', min_value=0.0, step=0.1, value=6.0, format='%.2f')
        with c8: delta_z_m = st.number_input('delta_z_m (m)', step=0.1, value=0.0, format='%.2f')

        peso_trecho = st.number_input('peso_trecho (UC)', min_value=0.0, step=1.0, value=10.0, format='%.2f')

        add_ok = st.form_submit_button('➕ Adicionar trecho', disabled=disabled_add)

    if add_ok:
        base = pd.DataFrame(st.session_state['trechos']).reindex(columns=BASE_COLS).copy()
        nova = {
            'id': id_val, 'ramo': ramo, 'ordem': int(ordem), 'de_no': de_no, 'para_no': para_no,
            'dn_mm': float(dn_mm), 'comp_real_m': float(comp_real_m), 'delta_z_m': float(delta_z_m),
            'peso_trecho': float(peso_trecho), 'leq_m': 0.0
        }
        base = pd.concat([base, pd.DataFrame([nova])], ignore_index=True)
        for c,t in DTYPES.items():
            try: base[c] = base[c].astype(t)
            except Exception: pass
        st.session_state['trechos'] = base
        st.success('Trecho adicionado! Agora preencha a matriz de L_eq na aba 2.')

    # Vis (sem leq_m)
    vis = pd.DataFrame(st.session_state['trechos']).reindex(columns=[c for c in BASE_COLS if c!='leq_m'])
    if not vis.empty:
        st.dataframe(vis, use_container_width=True, height=320)
        # exclusão simples
        labels = vis.apply(trecho_label, axis=1)
        del_sel = st.selectbox('Excluir trecho (opcional)', ['(nenhum)'] + labels.tolist())
        if st.button('🗑️ Excluir selecionado') and del_sel != '(nenhum)':
            idx = labels[labels==del_sel].index
            if len(idx)>0:
                base = pd.DataFrame(st.session_state['trechos']).drop(index=idx[0]).reset_index(drop=True)
                st.session_state['trechos'] = base
                st.session_state['eq_qty'].pop(str(del_sel), None)
                st.success('Trecho excluído.')

# ---------- Tab 2: Matriz de L_eq por trecho ----------
with tab2:
    st.subheader('Matriz de Comprimentos Equivalentes (por trecho)')
    st.caption('Para cada tipo de conexão (linhas), informe a **quantidade** por trecho (colunas). Os comprimentos equivalentes (m) vêm da norma conforme **material global** e **DN do trecho**.')

    base = pd.DataFrame(st.session_state['trechos'])
    if base.empty:
        st.info('Cadastre trechos na aba 1.')
    elif material_sistema == '(selecione)':
        st.warning('Selecione o Material do Sistema na sidebar.')
    else:
        # montar matriz
        idx_labels = [lab for _k, lab in TIPOS_PECAS]
        mat = pd.DataFrame(index=idx_labels)

        trechos = base.copy()
        trechos['label'] = trechos.apply(trecho_label, axis=1)

        table_mat = pvc_table if material_sistema=='PVC' else fofo_table

        def eqlen_for_dn(dn):
            try:
                dn = float(dn)
            except Exception:
                return None
            idx = int((table_mat['de_mm'] - dn).abs().idxmin())
            return table_mat.loc[idx].to_dict()

        trechos_info = []
        for _, r in trechos.iterrows():
            dn = r.get('dn_mm')
            eql = eqlen_for_dn(dn) or {}
            label = r['label']
            m_col, q_col = [], []
            for key, lab in TIPOS_PECAS:
                m = float(eql.get(key, 0) or 0)
                m_col.append(m)
                q_saved = st.session_state['eq_qty'].get(label, {}).get(key, 0)
                q_col.append(q_saved)
            mat[f'{label} (m)'] = m_col
            mat[f'{label} (Qt.)'] = q_col
            mat[f'{label} (Total)'] = [0.0]*len(m_col)
            trechos_info.append((label, eql))

        with st.form('form_eq_matrix'):
            edited = st.data_editor(
                mat,
                use_container_width=True,
                num_rows='fixed',
                column_config={c: (st.column_config.NumberColumn(step=1, min_value=0) if c.endswith('(Qt.)')
                                   else st.column_config.NumberColumn(disabled=True, format='%.2f'))
                               for c in mat.columns},
                hide_index=False,
                key='eq_matrix_editor'
            )
            ok = st.form_submit_button('Atualizar quantidades e calcular L_eq')

        if ok:
            mat2 = pd.DataFrame(edited)
            leq_by_label = {label: 0.0 for label, _ in trechos_info}
            for label, _eql in trechos_info:
                qdict = {}
                for key, lab in TIPOS_PECAS:
                    q = _num(mat2.loc[lab, f'{label} (Qt.)'], 0.0)
                    m = _num(mat2.loc[lab, f'{label} (m)'], 0.0)
                    leq_by_label[label] += q * m
                    qdict[key] = q
                    mat2.loc[lab, f'{label} (Total)'] = q * m
                st.session_state['eq_qty'][label] = qdict
            base2 = base.copy()
            base2['label'] = base2.apply(trecho_label, axis=1)
            for label, leq in leq_by_label.items():
                idx = base2[base2['label']==label].index
                if len(idx)>0:
                    base2.loc[idx[0], 'leq_m'] = float(leq)
            base2 = base2.drop(columns=['label']).reindex(columns=BASE_COLS)
            for c,t in DTYPES.items():
                try: base2[c] = base2[c].astype(t)
                except Exception: pass
            st.session_state['trechos'] = base2
            st.success('Quantidades atualizadas e L_eq calculado.')
            st.dataframe(mat2, use_container_width=True, height=420)
        else:
            st.info('Edite as **Qt.** e clique em **Atualizar quantidades e calcular L_eq**.')

# ---------- Tab 3: Resultados & Exportar ----------
with tab3:
    st.subheader('Resultados & Exportação')
    t3 = pd.DataFrame(st.session_state.get('trechos', {})).reindex(columns=BASE_COLS)
    if t3.empty:
        st.info('Cadastre trechos e preencha a matriz de L_eq.')
    else:
        t3 = t3.copy()

        def to_num_col(s):
            return pd.to_numeric(s.astype(str).str.replace(',', '.', regex=False), errors='coerce')

        for col in ['peso_trecho', 'dn_mm', 'comp_real_m', 'delta_z_m', 'leq_m']:
            t3[col] = to_num_col(t3.get(col, 0)).fillna(0.0)

        t3['Q (L/s)'] = k_uc * (t3['peso_trecho'] ** exp_uc)
        C_value = (c_pvc if material_sistema=='PVC' else c_fofo)
        t3['J (m/m)'] = t3.apply(lambda rr: hazen_williams_j(rr['Q (L/s)'], rr['dn_mm'], C_value), axis=1)

        t3['hf_continua (mca)'] = (t3['J (m/m)'] * t3['comp_real_m']).astype(float)
        t3['hf_local (mca)']    = (t3['J (m/m)'] * t3['leq_m']).astype(float)
        t3['hf_total (mca)']    = t3['hf_continua (mca)'] + t3['hf_local (mca)']

        t3 = t3.sort_values(by=['ramo','ordem'], na_position='last')
        t3['hf_acum_ramo (mca)'] = t3.groupby('ramo')['hf_total (mca)'].cumsum()
        t3['z_acum_ramo (m)']    = t3.groupby('ramo')['delta_z_m'].cumsum()

        t3['P_disp_final (mca)'] = (H_res - t3['z_acum_ramo (m)']) - t3['hf_acum_ramo (mca)']

        st.dataframe(t3, use_container_width=True, height=460)

        params = {'projeto': projeto_nome, 'material': material_sistema, 'k_uc': k_uc, 'exp_uc': exp_uc,
                  'c_pvc': c_pvc, 'c_fofo': c_fofo, 'H_res': H_res}
        proj = {'params': params, 'trechos': t3.to_dict(orient='list')}
        st.download_button('Baixar projeto (.json)', data=json.dumps(proj, ensure_ascii=False, indent=2).encode('utf-8'),
                           file_name='spaf_projeto.json', mime='application/json')
        biox = BytesIO(); export_to_excel(biox, t3, params)
        st.download_button('Baixar Excel (.xlsx)', data=biox.getvalue(), file_name='spaf_relatorio.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        biop = BytesIO(); export_to_pdf(biop, t3, params)
        st.download_button('Baixar PDF (.pdf)', data=biop.getvalue(), file_name='spaf_relatorio.pdf', mime='application/pdf')
