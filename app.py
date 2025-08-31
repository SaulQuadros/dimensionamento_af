import streamlit as st
import pandas as pd
import json
from io import BytesIO
from core.losses import hazen_williams_j, comprimento_equivalente_total
from core.tables import load_eqlen_tables, options_for_editor, key_from_label, row_for
from core.reports import export_to_excel, export_to_pdf

st.set_page_config(page_title='SPAF – Simplificado', layout='wide')
st.title('Dimensionamento de Tubulações de Água Fria — Barrilete e Colunas (Simplificado)')

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

tab1, tab2, tab3 = st.tabs(['1) Trechos','2) Peças por Trecho','3) Resultados & Exportar'])

with tab1:
    st.subheader('Cadastro de Trechos')
    st.caption('Informe: ramo, ordem, nós, material, DN interno (mm), comprimento real (m), Δz (m) e o **peso** do trecho.')
    if 'trechos' not in st.session_state:
        st.session_state['trechos'] = pd.DataFrame(columns=['id','ramo','ordem','de_no','para_no','material','dn_mm','comp_real_m','delta_z_m','peso_trecho','leq_m'])
    trechos_df = pd.DataFrame(st.session_state['trechos'])
    edited = st.data_editor(trechos_df, num_rows='dynamic', use_container_width=True,
                            column_config={'material': st.column_config.SelectboxColumn(options=['PVC','FoFo'], required=False)},
                            key='trechos_editor')
    st.session_state['trechos'] = edited

with tab2:
    st.subheader('Peças/Acessórios por Trecho (L_eq)')
    st.caption('Selecione um trecho e informe **somente as quantidades**. O app calcula L_eq pelo **material** e **DN** do trecho.')
    tre = pd.DataFrame(st.session_state.get('trechos', {}))
    if tre.empty:
        st.warning('Cadastre trechos na aba 1.')
    else:
        tre=tre.copy(); tre['label']=tre.apply(lambda r: f"{r.get('ramo','?')}-{int(r.get('ordem') or 0)} [{r.get('de_no','?')}→{r.get('para_no','?')}] id={r.get('id','')}", axis=1)
        sel = st.selectbox('Trecho', tre['label'].tolist())
        r = tre[tre['label']==sel].iloc[0]
        key = str(r.get('id') or f"{r.get('ramo')}-{r.get('ordem')}")
        if 'detalhes' not in st.session_state: st.session_state['detalhes'] = {}
        if key not in st.session_state['detalhes']:
            st.session_state['detalhes'][key] = pd.DataFrame({'peca':[pecas_labels[0]], 'quantidade':[0]})
        df_det = st.data_editor(st.session_state['detalhes'][key], num_rows='dynamic', use_container_width=True,
                                column_config={'peca': st.column_config.SelectboxColumn(options=pecas_labels, required=True),
                                               'quantidade': st.column_config.NumberColumn(min_value=0, step=1)},
                                key=f'det_{key}')
        st.session_state['detalhes'][key] = df_det
        eqlen_row = row_for((r.get('material') or 'PVC'), float(r.get('dn_mm') or 0), pvc_table, fofo_table)
        det_list=[{'tipo': key_from_label(rr['peca']), 'quantidade': rr['quantidade']} for _,rr in df_det.iterrows()]
        Leq = comprimento_equivalente_total(eqlen_row, det_list)
        st.metric('Comprimento equivalente do trecho (m)', f'{Leq:.2f}')
        tdf = pd.DataFrame(st.session_state['trechos']).copy()
        if 'label' not in tdf.columns:
            tdf['label']=tdf.apply(lambda x: f"{x.get('ramo','?')}-{int(x.get('ordem') or 0)} [{x.get('de_no','?')}→{x.get('para_no','?')}] id={x.get('id','')}", axis=1)
        idx=tdf[tdf['label']==sel].index
        if len(idx)>0: tdf.loc[idx[0],'leq_m']=float(Leq); st.session_state['trechos']=tdf

with tab3:
    st.subheader('Resultados & Exportação')
    t3 = pd.DataFrame(st.session_state.get('trechos', {}))
    if t3.empty:
        st.info('Cadastre trechos (aba 1) e, opcionalmente, defina L_eq (aba 2).')
    else:
        t3=t3.copy()
        t3['Q (L/s)']=t3['peso_trecho'].apply(lambda p: float(k_uc*((p or 0.0)**exp_uc)))
        def C(m): return c_pvc if (m or '').lower()=='pvc' else c_fofo
        t3['J (m/m)']=t3.apply(lambda rr: hazen_williams_j(rr.get('Q (L/s)'), rr.get('dn_mm'), C(rr.get('material'))), axis=1)
        t3['leq_m']=pd.to_numeric(t3.get('leq_m',0), errors='coerce').fillna(0.0)
        t3['comp_real_m']=pd.to_numeric(t3.get('comp_real_m',0), errors='coerce').fillna(0.0)
        t3['hf_continua (mca)']=(t3['J (m/m)']*t3['comp_real_m']).astype(float)
        t3['hf_local (mca)']=(t3['J (m/m)']*t3['leq_m']).astype(float)
        t3['hf_total (mca)']=t3['hf_continua (mca)']+t3['hf_local (mca)']
        t3=t3.sort_values(by=['ramo','ordem'], na_position='last')
        t3['delta_z_m']=pd.to_numeric(t3.get('delta_z_m',0), errors='coerce').fillna(0.0)
        t3['hf_acum_ramo (mca)']=t3.groupby('ramo')['hf_total (mca)'].cumsum()
        t3['z_acum_ramo (m)']=t3.groupby('ramo')['delta_z_m'].cumsum()
        t3['P_disp_final (mca)']=(H_res - t3['z_acum_ramo (m)']) - t3['hf_acum_ramo (mca)']
        st.dataframe(t3, use_container_width=True, height=460)
        params={'projeto':projeto_nome,'k_uc':k_uc,'exp_uc':exp_uc,'c_pvc':c_pvc,'c_fofo':c_fofo,'H_res':H_res}
        proj={'params':params,'trechos':t3.to_dict(orient='list')}
        st.download_button('Baixar projeto (.json)', data=json.dumps(proj, ensure_ascii=False, indent=2).encode('utf-8'),
                           file_name='spaf_projeto.json', mime='application/json')
        biox=BytesIO(); export_to_excel(biox,t3,params)
        st.download_button('Baixar Excel (.xlsx)', data=biox.getvalue(), file_name='spaf_relatorio.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        biop=BytesIO(); export_to_pdf(biop,t3,params)
        st.download_button('Baixar PDF (.pdf)', data=biop.getvalue(), file_name='spaf_relatorio.pdf', mime='application/pdf')
