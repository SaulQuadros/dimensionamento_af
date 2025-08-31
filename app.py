
import streamlit as st
import pandas as pd
import json
from io import BytesIO
from core.losses import hazen_williams_j, comprimento_equivalente_total
from core.tables import load_eqlen_tables, options_for_editor, key_from_label, row_for
from core.reports import export_to_excel, export_to_pdf

st.set_page_config(page_title='SPAF – Simplificado', layout='wide')
st.title('Dimensionamento de Tubulações de Água Fria — Barrilete e Colunas (Simplificado)')

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

BASE_COLS = ['id','ramo','ordem','de_no','para_no','material','dn_mm','comp_real_m','delta_z_m','peso_trecho','leq_m']

tab1, tab2, tab3 = st.tabs(['1) Trechos','2) Peças por Trecho','3) Resultados & Exportar'])

# ---------------- Tab 1: Trechos ----------------
with tab1:
    st.subheader('Cadastro de Trechos')
    st.caption('Informe: ramo, ordem, nós, material, DN interno (mm), comprimento real (m), Δz (m) e o **peso** do trecho.')

    # Estado inicial com esquema fixo
    if 'trechos' not in st.session_state:
        st.session_state['trechos'] = pd.DataFrame(columns=BASE_COLS)

    df = pd.DataFrame(st.session_state['trechos']).reindex(columns=BASE_COLS)

    colcfg = {
        'material': st.column_config.SelectboxColumn(options=['PVC','FoFo'], required=False),
        'ordem': st.column_config.NumberColumn(min_value=1, step=1, format='%d'),
        'dn_mm': st.column_config.NumberColumn(min_value=0, step=1, format='%.0f'),
        'comp_real_m': st.column_config.NumberColumn(min_value=0.0, step=0.1, format='%.2f'),
        'delta_z_m': st.column_config.NumberColumn(step=0.1, format='%.2f'),
        'peso_trecho': st.column_config.NumberColumn(min_value=0.0, step=1.0, format='%.2f'),
        'leq_m': st.column_config.NumberColumn(step=0.1, format='%.2f', disabled=True),
    }

    edited = st.data_editor(
        df,
        num_rows='dynamic',
        use_container_width=True,
        hide_index=True,
        column_config=colcfg,
        key='trechos_editor'
    )

    # Mantém apenas o esquema base e na mesma ordem (evita colunas transitórias como 'label')
    st.session_state['trechos'] = pd.DataFrame(edited).reindex(columns=BASE_COLS)

# ---------------- Tab 2: Peças por trecho ----------------
with tab2:
    st.subheader('Peças/Acessórios por Trecho (L_eq)')
    st.caption('Selecione um trecho e informe **somente as quantidades**. O app calcula L_eq pelo **material** e **DN** do trecho.')

    tre = pd.DataFrame(st.session_state.get('trechos', {})).reindex(columns=BASE_COLS)
    if tre.empty:
        st.warning('Cadastre trechos na aba 1.')
    else:
        # label para seleção (não é salvo em session_state)
        tre = tre.copy()
        tre['label'] = tre.apply(lambda r: f"{r.get('ramo','?')}-{int(r.get('ordem') or 0)} [{r.get('de_no','?')}→{r.get('para_no','?')}] id={r.get('id','')}", axis=1)
        sel = st.selectbox('Trecho', tre['label'].tolist())
        r = tre[tre['label']==sel].iloc[0]
        trecho_key = str(r.get('id') or f"{r.get('ramo')}-{r.get('ordem')}")

        if 'detalhes' not in st.session_state:
            st.session_state['detalhes'] = {}
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

        # Calcula L_eq
        material = (r.get('material') or 'PVC')
        try:
            dn = float(r.get('dn_mm') or 0)
        except Exception:
            dn = 0.0
        eqlen_row = row_for(material, dn, pvc_table, fofo_table)

        det_list = [{'tipo': key_from_label(rr['peca']), 'quantidade': rr['quantidade']} for _, rr in df_det.iterrows()]
        L_eq = comprimento_equivalente_total(eqlen_row, det_list)
        st.metric('Comprimento equivalente do trecho (m)', f'{L_eq:.2f}')

        # Grava L_eq no dataframe base, SEM adicionar colunas auxiliares
        base = pd.DataFrame(st.session_state['trechos']).reindex(columns=BASE_COLS).copy()
        # localizar a linha pelo trio (ramo, ordem, de_no->para_no) ou id
        mask = (
            (base['id'].astype(str) == str(r.get('id'))) &
            (base['ramo'].astype(str) == str(r.get('ramo'))) &
            (pd.to_numeric(base['ordem'], errors='coerce').fillna(-1) == float(r.get('ordem') or 0))
        )
        idx = base[mask].index
        if len(idx) == 0:
            # fallback pelo display label
            base['__label__'] = base.apply(lambda x: f"{x.get('ramo','?')}-{int(x.get('ordem') or 0)} [{x.get('de_no','?')}→{x.get('para_no','?')}] id={x.get('id','')}", axis=1)
            idx = base[base['__label__']==sel].index
        if len(idx) > 0:
            base.loc[idx[0], 'leq_m'] = float(L_eq)
            base = base.reindex(columns=BASE_COLS)
            st.session_state['trechos'] = base

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
