#!/usr/bin/env python
# coding: utf-8

import re, uuid, json, unicodedata
import pandas as pd
import streamlit as st

VERSION_STAMP = "build 2025-09-04 13:42:59 • app.py"

BASE_COLS = [
    'id','ramo','ordem','tipo_ini','de_no','para_no',
    'dn_mm','comp_real_m','dz_io_m','peso_trecho','p_min_ref_kPa'
]

def _ensure_session_df():
    if 'trechos' not in st.session_state:
        import pandas as pd
        st.session_state['trechos'] = pd.DataFrame(columns=BASE_COLS)

def normalize_label(value: str, mode: str) -> str:
    import re
    if mode.startswith('Letras'):
        v = (value or '').strip().upper()
        if not re.fullmatch(r'[A-Z]+', v):
            raise ValueError('Use apenas letras maiúsculas (A–Z, AA, AB, ...).')
        return v
    else:
        v = (value or '').strip()
        if not re.fullmatch(r'[0-9]+', v):
            raise ValueError('Use apenas dígitos (0–9).')
        return str(int(v))

def _norm_tipo(x:str)->str:
    import unicodedata
    s = (x or '').lower().strip()
    s = ''.join(ch for ch in unicodedata.normalize('NFD', s) if unicodedata.category(ch) != 'Mn')
    s = s.replace(' ', '')
    if 'entrada' in s: return 'entrada'
    if 'cruzeta' in s: return 'cruzeta'
    if 'te' in s: return 'te'
    return s

st.set_page_config(page_title='SPAF – Trechos', layout='wide')
st.title('SPAF – Cadastro de Trechos (Entrada, Tê, Cruzeta)')
st.caption(VERSION_STAMP)

_ensure_session_df()

with st.sidebar:
    st.header('Parâmetros Globais')
    projeto_nome = st.text_input('Nome do Projeto', 'Projeto Genérico')
    st.markdown('---')
    notacao_mode = st.radio('Modo de notação', ['Letras (A, B, ..., Z, AA, AB, ...)', 'Números (1, 2, 3, ...)'], index=0)
    st.markdown('---')
    st.subheader('Capacidade por tipo de conexão')
    cap_ent = st.number_input('Entrada de água – máx. saídas', min_value=1, max_value=10, value=1, step=1, key='cap_ent')
    cap_te  = st.number_input('Tê – máx. saídas', min_value=1, max_value=10, value=2, step=1, key='cap_te')
    cap_crz = st.number_input('Cruzeta – máx. saídas', min_value=1, max_value=10, value=3, step=1, key='cap_crz')

tab1, tab2 = st.tabs(['Trechos', 'Resultados (prévia)'])

with tab1:
    st.subheader('Cadastrar trechos')
    with st.form('frm_add'):
        c1,c2,c3 = st.columns([1.2,1,1])
        id_val = c1.text_input('id (opcional)')
        ramo = c2.text_input('ramo', value='A')
        ordem = c3.number_input('ordem', min_value=1, step=1, value=1)

        # Linha exclusiva e destacada
        st.markdown('### Tipo da conexão no INÍCIO')
        tipo_ini = st.selectbox('Selecione o tipo do ponto inicial:', ['Entrada de Água','Tê','Cruzeta'], key='tipo_ini_select')
        st.caption('Seletor obrigatório — se não estiver vendo este campo, o arquivo carregado não é esta versão.')

        c5, c6 = st.columns(2)
        de_no_raw = c5.text_input('de_no (início)', value='A' if notacao_mode.startswith('Let') else '1')
        para_no_raw = c6.text_input('para_no (fim)', value='B' if notacao_mode.startswith('Let') else '2')

        c7,c8,c9 = st.columns(3)
        dn_mm = c7.number_input('dn_mm (mm, interno)', min_value=0.0, step=1.0, value=32.0)
        comp_real_m = c8.number_input('comp_real_m (m)', min_value=0.0, step=0.1, value=6.0, format='%.2f')
        dz_io_m = c9.number_input("dz_io_m (m) (z_inicial - z_final; desce>0, sobe<0)", step=0.1, value=0.0, format="%.2f")

        c10,c11 = st.columns([1,1])
        peso_trecho = c10.number_input('peso_trecho (UC)', min_value=0.0, step=1.0, value=10.0, format='%.2f')
        tipo_ponto = c11.selectbox('Tipo do ponto no final do trecho', ['Sem utilização (5 kPa)','Ponto de utilização (10 kPa)'])
        p_min_ref_kPa = st.number_input('p_min_ref (kPa)', min_value=0.0, step=0.5,
                                        value=(5.0 if 'Sem' in tipo_ponto else 10.0), format='%.2f')

        ok = st.form_submit_button("➕ Adicionar trecho")

        if ok:
            try:
                de_no = normalize_label(de_no_raw, notacao_mode)
                para_no = normalize_label(para_no_raw, notacao_mode)
            except ValueError as e:
                st.error(f'Erro na notação dos nós: {e}')
                st.stop()
            if de_no == para_no:
                st.error('Início e fim do trecho não podem ser iguais.'); st.stop()

            df = st.session_state['trechos'].copy()

            # duplicidade global
            if not df.empty and set(['de_no','para_no']).issubset(df.columns):
                dup = df[(df['de_no'].astype(str)==de_no) & (df['para_no'].astype(str)==para_no)]
                if not dup.empty:
                    st.error(f'Já existe um trecho {de_no} → {para_no}.'); st.stop()

            # capacidade por tipo
            tipo_norm = _norm_tipo(tipo_ini)
            cap_map = {'entrada': int(st.session_state.get('cap_ent',1)),
                        'te': int(st.session_state.get('cap_te',2)),
                        'cruzeta': int(st.session_state.get('cap_crz',3))}
            cap_allowed = cap_map.get(tipo_norm, 2)
            subset = df[df['de_no'].astype(str)==de_no] if not df.empty else df
            if not subset.empty and len(subset) >= cap_allowed:
                st.error(f'O nó de início "{de_no}" ({tipo_ini}) já atingiu o limite de {cap_allowed} saída(s).'); st.stop()

            # inserir
            rid = (id_val or '').strip()
            if not rid:
                rid = f"row_{uuid.uuid4().hex[:6]}"
            new = pd.DataFrame([{
                'id': rid, 'ramo':ramo, 'ordem':int(ordem), 'tipo_ini':tipo_ini,
                'de_no':de_no, 'para_no':para_no, 'dn_mm':float(dn_mm),
                'comp_real_m':float(comp_real_m), 'dz_io_m':float(dz_io_m),
                'peso_trecho':float(peso_trecho), 'p_min_ref_kPa':float(p_min_ref_kPa)
            }])
            st.session_state['trechos'] = pd.concat([df, new], ignore_index=True)
            st.success(f'Trecho adicionado: {ramo}: {de_no} → {para_no} ({tipo_ini}).')

    st.dataframe(st.session_state['trechos'][BASE_COLS], use_container_width=True, height=360)

with tab2:
    st.subheader('Prévia de resultados / exportação')
    base = st.session_state['trechos']
    if base.empty:
        st.info('Cadastre trechos na aba 1.')
    else:
        proj = {'params': {}, 'trechos': base.to_dict(orient='list')}
        st.download_button('Baixar projeto (.json)',
                           data=json.dumps(proj, ensure_ascii=False, indent=2).encode('utf-8'),
                           file_name='spaf_projeto.json', mime='application/json')
