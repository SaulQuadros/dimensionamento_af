import streamlit as st
import pandas as pd
import json
from io import BytesIO
from core.losses import hazen_williams_j
from core.tables import load_eqlen_tables
from core.reports import export_to_excel, export_to_pdf

st.set_page_config(page_title='SPAF – Form + Matriz L_eq (Dinâmico)', layout='wide')
st.title('Dimensionamento – Barrilete e Colunas (Form + Matriz L_eq Dinâmico)')

# ---------- Helpers ----------
BASE_COLS = ['id','ramo','ordem','de_no','para_no','dn_mm','comp_real_m','delta_z_m','peso_trecho','leq_m']
DTYPES = {'id':'string','ramo':'string','ordem':'Int64','de_no':'string','para_no':'string',
          'dn_mm':'float','comp_real_m':'float','delta_z_m':'float','peso_trecho':'float','leq_m':'float'}

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

# humanize dict covering both PVC and FoFo keys
HUMAN = {
    # PVC
    'joelho_90':'Joelho 90°','joelho_45':'Joelho 45°','curva_90':'Curva 90°','curva_45':'Curva 45°',
    'te_passagem_direita':'Tê 90° Passagem Direita','te_saida_de_lado':'Tê 90° Saída de Lado','te_saida_bilateral':'Tê 90° Saída Bilateral',
    'entrada_normal':'Entrada Normal','entrada_borda':'Entrada de Borda','saida_canalizacao':'Saída de Canalização',
    'registro_globo_aberto':'Registro de Globo Aberto (RE)','registro_gaveta_aberto':'Registro de Gaveta Aberto (RG)','registro_angulo_aberto':'Registro Ângulo Aberto',
    'valvula_pe_crivo':'Válvula de Pé e Crivo','valvula_retencao_leve':'Válvula de Retenção – Tipo Leve','valvula_retencao_pesado':'Válvula de Retenção – Tipo Pesado',
    # FoFo (exemplos comuns)
    'cot_90_raio_longo':'Cotovelo 90° Raio Longo','cot_90_raio_medio':'Cotovelo 90° Raio Médio','cot_90_raio_curto':'Cotovelo 90° Raio Curto/Joelho 90°',
    'cot_45':'Cotovelo/Joelho 45°','curva_90_rd_1_2':'Curva 90° R/d 1/2','curva_90_rd_1':'Curva 90° R/d 1','curva_45':'Curva 45°',
    'entrada_gaveta_aberta':'Entrada de gaveta aberta','entrada_globo_aberta':'Entrada de globo aberta','entrada_angulo_aberta':'Entrada de ângulo aberta',
    'saida_da_canalizacao':'Saída da Canalização',
}

# ---------- Sidebar ----------
with st.sidebar:
    st.header('Parâmetros Globais')
    projeto_nome = st.text_input('Nome do Projeto', 'Projeto Genérico')
    material_sistema = st.selectbox('Material do Sistema', ['(selecione)','PVC','FoFo'], index=0)
    k_uc  = st.number_input('k (Q = k·Peso^exp)', value=0.30, step=0.05, format='%.2f')
    exp_uc = st.number_input('exp (Q = k·Peso^exp)', value=0.50, step=0.05, format='%.2f')
    c_pvc = st.number_input('C (PVC)', value=150.0, step=5.0)
    c_fofo = st.number_input('C (Ferro Fundido)', value=130.0, step=5.0)
    H_res  = st.number_input('Nível do reservatório (m) – referência z=0', value=25.0, step=0.5)

pvc_table, fofo_table = load_eqlen_tables()

# ---------- Session init ----------
if 'trechos' not in st.session_state:
    empty = {c: pd.Series(dtype=t) for c,t in DTYPES.items()}
    st.session_state['trechos'] = pd.DataFrame(empty)

tab1, tab2, tab3 = st.tabs(['1) Trechos (Form)','2) Matriz de L_eq (dinâmico)','3) Resultados & Exportar'])

# TAB 1
with tab1:
    st.subheader('Cadastro de Trechos — por Formulário')
    if material_sistema == '(selecione)':
        st.warning('Escolha o **Material do Sistema** na sidebar para habilitar o cadastro.')
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
        base = pd.DataFrame(st.session_state['trechos']).reindex(columns=BASE_COLS).copy()
        nova = {'id':id_val,'ramo':ramo,'ordem':int(ordem),'de_no':de_no,'para_no':para_no,
                'dn_mm':float(dn_mm),'comp_real_m':float(comp_real_m),'delta_z_m':float(delta_z_m),
                'peso_trecho':float(peso_trecho),'leq_m':0.0}
        base = pd.concat([base, pd.DataFrame([nova])], ignore_index=True)
        for c,t in DTYPES.items():
            try: base[c]=base[c].astype(t)
            except Exception: pass
        st.session_state['trechos']=base
        st.success('Trecho adicionado!')
    vis = pd.DataFrame(st.session_state['trechos']).reindex(columns=[c for c in BASE_COLS if c!='leq_m'])
    st.dataframe(vis, use_container_width=True, height=300)

# Helpers to get diameter column and piece keys
def get_dn_series(table):
    # Try common names; else first column
    for nm in table.columns:
        low=nm.lower()
        if ('de' in low or 'dn' in low or 'diam' in low) and 'mm' in low:
            return table[nm], nm
    return table.iloc[:,0], table.columns[0]

def piece_keys_for(table):
    dn_series, dn_name = get_dn_series(table)
    keys = [c for c in table.columns if c != dn_name]
    return keys

# TAB 2
with tab2:
    st.subheader('Matriz de Comprimentos Equivalentes (dinâmico)')
    base = pd.DataFrame(st.session_state['trechos'])
    if base.empty:
        st.info('Cadastre trechos na aba 1.')
    elif material_sistema == '(selecione)':
        st.warning('Selecione o Material do Sistema na sidebar.')
    else:
        table_mat = pvc_table if material_sistema=='PVC' else fofo_table
        dn_series, dn_name = get_dn_series(table_mat)
        keys = piece_keys_for(table_mat)  # piece keys in table order
        labels = [HUMAN.get(k, k.replace('_',' ').title()) for k in keys]

        tre = base.copy()
        tre['label'] = tre.apply(trecho_label, axis=1)

        # Build the matrix
        mat = pd.DataFrame(index=labels)
        def eql_row_for_dn(dn):
            try: dn=float(dn)
            except Exception: return table_mat.iloc[0].to_dict()
            idx = (dn_series - dn).abs().idxmin()
            return table_mat.loc[idx].to_dict()

        for _, r in tre.iterrows():
            label = r['label']
            eql = eql_row_for_dn(r.get('dn_mm'))
            m_col = [ _num(eql.get(k,0.0),0.0) for k in keys ]
            mat[f'{label} (m)'] = m_col
            mat[f'{label} (Qt.)'] = [0]*len(m_col)
            mat[f'{label} (Total)'] = [0.0]*len(m_col)

        with st.form('matrix_form'):
            edited = st.data_editor(
                mat, use_container_width=True, num_rows='fixed', hide_index=False,
                column_config={c: (st.column_config.NumberColumn(step=1, min_value=0) if c.endswith('(Qt.)')
                                   else st.column_config.NumberColumn(disabled=True, format='%.2f'))
                               for c in mat.columns},
                key='matrix_editor_dyn'
            )
            ok2 = st.form_submit_button('Calcular L_eq e aplicar')
        if ok2:
            mat2 = pd.DataFrame(edited)
            # compute leq totals
            leq_by_label = { lab:0.0 for lab in tre['label'] }
            for lab in tre['label']:
                total = 0.0
                for k, disp in zip(keys, labels):
                    q = _num(mat2.loc[disp, f'{lab} (Qt.)'], 0.0)
                    m = _num(mat2.loc[disp, f'{lab} (m)'], 0.0)
                    mat2.loc[disp, f'{lab} (Total)'] = q*m
                    total += q*m
                leq_by_label[lab] = total
            base2 = base.copy(); base2['label'] = tre['label']
            for lab, leq in leq_by_label.items():
                idx = base2[base2['label']==lab].index
                if len(idx)>0: base2.loc[idx[0], 'leq_m'] = float(leq)
            base2 = base2.drop(columns=['label']).reindex(columns=BASE_COLS)
            for c,t in DTYPES.items():
                try: base2[c]=base2[c].astype(t)
                except Exception: pass
            st.session_state['trechos'] = base2
            st.success('L_eq aplicado a todos os trechos.')
            st.dataframe(mat2, use_container_width=True, height=420)

# TAB 3
with tab3:
    st.subheader('Resultados & Exportação')
    t3 = pd.DataFrame(st.session_state.get('trechos', {})).reindex(columns=BASE_COLS)
    if t3.empty:
        st.info('Cadastre trechos e preencha a matriz de L_eq.')
    else:
        t3 = t3.copy()
        def to_num_col(s): return pd.to_numeric(s.astype(str).str.replace(',', '.', regex=False), errors='coerce')
        for col in ['peso_trecho','dn_mm','comp_real_m','delta_z_m','leq_m']:
            t3[col] = to_num_col(t3.get(col,0)).fillna(0.0)
        t3['Q (L/s)'] = k_uc * (t3['peso_trecho'] ** exp_uc)
        C_value = (c_pvc if material_sistema=='PVC' else c_fofo)
        t3['J (m/m)'] = t3.apply(lambda rr: hazen_williams_j(rr['Q (L/s)'], rr['dn_mm'], C_value), axis=1)
        t3['hf_continua (mca)'] = (t3['J (m/m)'] * t3['comp_real_m']).astype(float)
        t3['hf_local (mca)'] = (t3['J (m/m)'] * t3['leq_m']).astype(float)
        t3['hf_total (mca)'] = t3['hf_continua (mca)'] + t3['hf_local (mca)']
        t3 = t3.sort_values(by=['ramo','ordem'], na_position='last')
        t3['hf_acum_ramo (mca)'] = t3.groupby('ramo')['hf_total (mca)'].cumsum()
        t3['z_acum_ramo (m)'] = t3.groupby('ramo')['delta_z_m'].cumsum()
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
