#!/usr/bin/env python
# coding: utf-8

# In[ ]:


#!/usr/bin/env python
# coding: utf-8

import re
import uuid
from pathlib import Path
import json
import unicodedata
import pandas as pd
import streamlit as st

# =========================
# Helpers & constants
# =========================

KPA_PER_M = 9.80665  # 1 m.c.a. ≈ 9.80665 kPa

# Colunas-base (inclui tipo da conexão no início do trecho)
BASE_COLS = [
    'id','ramo','ordem','tipo_ini','de_no','para_no',
    'dn_mm','de_ref_mm','pol_ref',
    'comp_real_m','dz_io_m','peso_trecho','leq_m','p_min_ref_kPa'
]
DTYPES = {
    'id':'string','ramo':'string','ordem':'Int64','tipo_ini':'string',
    'de_no':'string','para_no':'string',
    'dn_mm':'float','de_ref_mm':'float','pol_ref':'string',
    'comp_real_m':'float','dz_io_m':'float','peso_trecho':'float','leq_m':'float','p_min_ref_kPa':'float'
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
    try: return int(_num(x, default))
    except Exception: return default

def trecho_label(r):
    return f"{_s(r.get('ramo'))}-{_i(r.get('ordem'))} [{_s(r.get('de_no'))}→{_s(r.get('para_no'))}] ({_s(r.get('tipo_ini'))}) id={_s(r.get('id'))}"

def _st_rerun():
    if hasattr(st, 'rerun'):
        st.rerun()
    elif hasattr(st, 'experimental_rerun'):
        st.experimental_rerun()

def _ensure_session_df():
    if 'trechos' not in st.session_state or not isinstance(st.session_state['trechos'], pd.DataFrame):
        st.session_state['trechos'] = pd.DataFrame(columns=BASE_COLS)
    else:
        df = st.session_state['trechos']
        for c in BASE_COLS:
            if c not in df.columns:
                df[c] = pd.Series([None]*len(df))
        st.session_state['trechos'] = df[BASE_COLS]

def _norm_tipo(x:str)->str:
    """Normaliza 'tipo_ini' para comparação robusta (te/tê, entrada de água, cruzeta)."""
    s = _s(x).lower().strip()
    # remove acentos
    s = ''.join(ch for ch in unicodedata.normalize('NFD', s) if unicodedata.category(ch) != 'Mn')
    s = s.replace(' ', '')
    if 'entrada' in s:
        return 'entrada'
    if 'cruzeta' in s:
        return 'cruzeta'
    if 'te' in s:  # cobre 'tê' e 'te'
        return 'te'
    return s

# =========================
# Notação dos nós (A..Z, AA.. / 1..N)
# =========================

def excel_next_label(lbl: str) -> str:
    """Próximo rótulo estilo Excel (A..Z, AA..AZ, BA..)."""
    s = (lbl or '').strip().upper()
    if s == '': return 'A'
    if not re.fullmatch(r'[A-Z]+', s): s = 'A'
    chars = list(s)
    i = len(chars) - 1
    carry = True
    while i >= 0 and carry:
        if chars[i] == 'Z':
            chars[i] = 'A'
            i -= 1
        else:
            chars[i] = chr(ord(chars[i]) + 1)
            carry = False
    if carry: chars = ['A'] + chars
    return ''.join(chars)

def normalize_label(value: str, mode: str) -> str:
    """Limpa/valida rótulos conforme o modo escolhido."""
    if mode == 'Letras (A, B, ..., Z, AA, AB, ...)':
        v = (value or '').strip().upper()
        if not re.fullmatch(r'[A-Z]+', v):
            raise ValueError('Use apenas letras maiúsculas (A–Z, AA, AB, ...).')
        return v
    else:  # 'Números (1, 2, 3, ...)'
        v = (value or '').strip()
        if not re.fullmatch(r'[0-9]+', v):
            raise ValueError('Use apenas dígitos (0–9).')
        return str(int(v))  # remove zeros à esquerda (mantém "0" se for zero)

# =========================
# Tabelas de L_eq (seguras)
# =========================

def safe_load_tables():
    pvc = pd.DataFrame()
    fofo = pd.DataFrame()
    try:
        base = Path(__file__).parent
        pvc = pd.read_csv(base / 'data/pvc_pl_eqlen.csv')
    except Exception:
        pass
    try:
        base = Path(__file__).parent
        fofo = pd.read_csv(base / 'data/fofo_pl_eqlen.csv')
    except Exception:
        pass
    return pvc, fofo

def get_dn_series(table):
    if table.empty:
        return None, None
    for nm in table.columns:
        low = nm.lower()
        if ('de' in low or 'dn' in low or 'diam' in low) and 'mm' in low:
            return table[nm], nm
    return table.iloc[:, 0], table.columns[0]

def piece_columns_for(table):
    if table.empty:
        return [], None
    dn_series, dn_name = get_dn_series(table)
    cols = [c for c in table.columns if c not in (dn_name, 'dref_pol')]
    return cols, dn_name

def lookup_row_by_mm(table, ref_mm):
    if table.empty:
        return pd.Series(dtype=float), float(ref_mm or 0), ''
    dn_series, dn_name = get_dn_series(table)
    try: x = float(ref_mm)
    except Exception: x = 0.0
    idx = (dn_series - x).abs().idxmin()
    row = table.loc[idx]
    de_ref_mm = float(row.get(dn_name, 0) or 0)
    pol_ref = _s(row.get('dref_pol')) if 'dref_pol' in table.columns else ''
    return row, de_ref_mm, pol_ref

def pretty(name: str):
    name = (name or '').strip().replace('_', ' ')
    name = name.replace(' de ', ' DE ').replace(' mm', ' (mm)')
    return name

# =========================
# App
# =========================

st.set_page_config(page_title='SPAF – Regras de Trechos (ramais, Tês, cruzetas)', layout='wide')
st.title('SPAF – Barriletes e Colunas • Regras de Trechos (ramais, Tê, Cruzeta, Entrada)')

pvc_table, fofo_table = safe_load_tables()
_ensure_session_df()

# Sidebar
with st.sidebar:
    st.header('Parâmetros Globais')
    projeto_nome = st.text_input('Nome do Projeto', 'Projeto Genérico')
    material_sistema = st.selectbox('Material do Sistema', ['(selecione)','PVC','FoFo'], index=0)
    modelo_perda = st.selectbox('Modelo de perda de carga', ['Hazen-Williams','Fair-Whipple-Hsiao'], index=0)
    st.markdown('---')
    st.subheader('Notação dos nós (início/fim)')
    notacao_mode = st.radio('Modo de notação', ['Letras (A, B, ..., Z, AA, AB, ...)', 'Números (1, 2, 3, ...)'], index=0)
    st.caption('A validação do app garante que os nós respeitem o modo escolhido.')
    st.markdown('---')
    st.subheader('Capacidade por tipo de conexão (saídas permitidas)')
    cap_ent = st.number_input('Entrada de água – máx. saídas', min_value=1, max_value=10, value=1, step=1)
    cap_te  = st.number_input('Tê – máx. saídas', min_value=1, max_value=10, value=2, step=1)
    cap_crz = st.number_input('Cruzeta – máx. saídas', min_value=1, max_value=10, value=3, step=1)
    st.caption('A lógica do app impede exceder essas capacidades por nó de início.')

tab1, tab2, tab3 = st.tabs(['Trechos', 'L_eq por DN (referencial)', 'Resultados'])

# ---------------- TAB 1: Cadastro ----------------
with tab1:
    st.subheader('Cadastrar trechos')
    with st.form('frm_add'):
        # Linha 1 – identificação
        c1,c2,c3 = st.columns([1.2,1,1])
        id_val = c1.text_input('id (opcional)')
        ramo = c2.text_input('ramo', value='A')
        ordem = c3.number_input('ordem', min_value=1, step=1, value=1)

        # Linha 2 – tipo do ponto inicial, início e fim
        st.markdown('**Ponto inicial e final**')
        c4, c5, c6 = st.columns([1.2, 1, 1])
        tipo_ini = c4.selectbox('Tipo do ponto inicial (INÍCIO)',
                                ['Entrada de Água','Tê','Cruzeta'])
        de_no_raw = c5.text_input('de_no (início)', value='A' if notacao_mode.startswith('Let') else '1')
        para_no_raw = c6.text_input('para_no (fim)', value='B' if notacao_mode.startswith('Let') else '2')

        # Linha 3 – DN, comprimento, desnível
        c7,c8,c9 = st.columns(3)
        dn_mm = c7.number_input('dn_mm (mm, interno)', min_value=0.0, step=1.0, value=32.0)
        comp_real_m = c8.number_input('comp_real_m (m)', min_value=0.0, step=0.1, value=6.0, format='%.2f')
        dz_io_m = c9.number_input("dz_io_m (m) (z_inicial - z_final; desce>0, sobe<0)", step=0.1, value=0.0, format="%.2f")

        # Linha 4 – peso e ponto final (mín. de pressão)
        c10,c11 = st.columns([1,1])
        peso_trecho = c10.number_input('peso_trecho (UC)', min_value=0.0, step=1.0, value=10.0, format='%.2f')
        tipo_ponto = c11.selectbox('Tipo no final do trecho', ['Sem utilização (5 kPa)','Ponto de utilização (10 kPa)'])
        p_min_ref_kPa = st.number_input('p_min_ref (kPa)', min_value=0.0, step=0.5,
                                        value=(5.0 if 'Sem' in tipo_ponto else 10.0), format='%.2f')

        ok = st.form_submit_button("➕ Adicionar trecho", disabled=(material_sistema == "(selecione)"))

        if ok:
            # 1) Notação
            try:
                de_no = normalize_label(de_no_raw, notacao_mode)
                para_no = normalize_label(para_no_raw, notacao_mode)
            except ValueError as e:
                st.error(f'Erro na notação dos nós: {e}')
                st.stop()
            if de_no == para_no:
                st.error('Início e fim do trecho não podem ser iguais.')
                st.stop()

            # 2) Duplicidade global (de_no + para_no) — independente do ramo
            df = pd.DataFrame(st.session_state['trechos']).copy()
            if not df.empty and {'de_no','para_no'} <= set(df.columns):
                dup = df[(df['de_no'].astype(str)==de_no) & (df['para_no'].astype(str)==para_no)]
                if not dup.empty:
                    st.error(f'Já existe um trecho {de_no} → {para_no}.')
                    st.stop()

            # 3) Limite de saídas por nó de início + consistência do tipo
            count_out = 0
            if not df.empty and {'de_no','tipo_ini'} <= set(df.columns):
                subset = df[df['de_no'].astype(str)==de_no]
                if not subset.empty:
                    # Consistência do tipo: compara em forma normalizada
                    tipos_exist_norm = set(_norm_tipo(x) for x in subset['tipo_ini'].tolist())
                    tipo_sel_norm = _norm_tipo(tipo_ini)
                    if len(tipos_exist_norm) > 1 and tipo_sel_norm not in tipos_exist_norm:
                        st.error('O nó de início já foi cadastrado com tipos diferentes. Padronize o tipo.')
                        st.stop()
                    if len(tipos_exist_norm) == 1 and tipo_sel_norm not in tipos_exist_norm:
                        st.error(f'O nó "{de_no}" já está definido como "{list(subset["tipo_ini"].unique())[0]}".')
                        st.stop()
                    count_out = len(subset)
            # Capacidades (valores da sidebar)
            cap_map = {'entrada': int(locals().get('cap_ent', 1)),
                       'te': int(locals().get('cap_te', 2)),
                       'cruzeta': int(locals().get('cap_crz', 3))}
            cap_allowed = cap_map.get(_norm_tipo(tipo_ini), 2)
            if count_out >= cap_allowed:
                st.error(f'O nó de início "{de_no}" ({tipo_ini}) já atingiu o limite de {cap_allowed} saída(s).')
                st.stop()

            # 4) Monta nova linha (ID único)
            base_exist = pd.DataFrame(st.session_state['trechos'])
            existing_ids = set(
                base_exist.get('id', pd.Series([], dtype=str)).astype(str).fillna('').str.strip().tolist()
            )
            raw_id = (id_val or '').strip()
            if (not raw_id) or (raw_id in existing_ids):
                base_tag = raw_id if raw_id else 'row'
                raw_id = f"{base_tag}_{uuid.uuid4().hex[:6]}"

            # L_eq de referência (se tabelas existirem)
            mat_key = 'FoFo' if isinstance(material_sistema,str) and material_sistema.strip().lower()=='fofo' else 'PVC'
            table_mat = pvc_table if mat_key=='PVC' else fofo_table
            _, de_ref_mm, pol_ref = lookup_row_by_mm(table_mat, dn_mm)

            nova = {
                'id': raw_id,'ramo':ramo,'ordem':int(ordem),'tipo_ini':tipo_ini,
                'de_no':de_no,'para_no':para_no,
                'dn_mm':float(dn_mm),'de_ref_mm':float(de_ref_mm),'pol_ref':pol_ref,
                'comp_real_m':float(comp_real_m),'dz_io_m':float(dz_io_m),
                'peso_trecho':float(peso_trecho),'leq_m':0.0,'p_min_ref_kPa':float(p_min_ref_kPa)
            }

            base = pd.concat([df, pd.DataFrame([nova])], ignore_index=True)
            for c,t in DTYPES.items():
                try: base[c] = base[c].astype(t)
                except Exception: pass
            st.session_state['trechos'] = base[BASE_COLS]
            st.success(f'Trecho adicionado: {ramo}: {de_no} → {para_no} ({tipo_ini}).')

    vis_cols = [c for c in BASE_COLS if c!='leq_m']
    st.dataframe(pd.DataFrame(st.session_state['trechos'])[vis_cols], use_container_width=True, height=360)

# ---------------- Gerenciar trechos ----------------
st.subheader('Gerenciar trechos')

def _move_row_action(row_id, ramo_val, direction):
    df = pd.DataFrame(st.session_state.get('trechos', pd.DataFrame()))
    if df.empty or 'ramo' not in df.columns or 'ordem' not in df.columns:
        return
    if 'id' not in df.columns:
        df = df.reset_index().rename(columns={'index':'id'})
    sub = df[df['ramo']==ramo_val].sort_values('ordem', kind='stable')
    ids = sub['id'].tolist()
    if row_id not in ids:
        return
    i = ids.index(row_id)
    if direction == 'up' and i > 0:
        ids[i-1], ids[i] = ids[i], ids[i-1]
    elif direction == 'down' and i < len(ids)-1:
        ids[i], ids[i+1] = ids[i+1], ids[i]
    sub = sub.set_index('id').loc[ids].reset_index()
    sub['ordem'] = range(1, len(sub)+1)
    df.loc[df['ramo']==ramo_val, 'ordem'] = None
    for _, r in sub.iterrows():
        df.loc[(df['ramo']==ramo_val) & (df['id']==r['id']), 'ordem'] = r['ordem']
    for k, rid in enumerate(ids, start=1):
        df.loc[df['id']==rid, 'ordem'] = k
    st.session_state['trechos'] = df[BASE_COLS]
    _st_rerun()

def _delete_row_action(row_id, ramo_val):
    df = pd.DataFrame(st.session_state.get('trechos', pd.DataFrame()))
    if df.empty: return
    if 'id' not in df.columns:
        df = df.reset_index().rename(columns={'index':'id'})
    df = df[df['id'] != row_id].reset_index(drop=True)
    if 'ramo' in df.columns and 'ordem' in df.columns:
        for rv in df['ramo'].dropna().unique().tolist():
            sub = df[df['ramo']==rv].sort_values('ordem', kind='stable').copy()
            sub['ordem'] = range(1, len(sub)+1)
            df.loc[df['ramo']==rv, 'ordem'] = None
            for _, r in sub.iterrows():
                df.loc[(df['ramo']==rv) & (df['id']==r['id']), 'ordem'] = r['ordem']
    st.session_state['trechos'] = df[BASE_COLS]
    _st_rerun()

df_view = pd.DataFrame(st.session_state.get('trechos', pd.DataFrame()))
if not df_view.empty:
    if 'ramo' in df_view.columns and 'ordem' in df_view.columns:
        tman = df_view.sort_values(['ramo','ordem'], kind='stable').reset_index(drop=True)
    else:
        tman = df_view.reset_index(drop=True)

    r_opt = ['Todos'] + (sorted([str(x) for x in tman['ramo'].dropna().unique().tolist()]) if 'ramo' in tman.columns else [])
    ramo_sel = st.selectbox('Filtrar por ramo', r_opt or ['Todos'], key='manage_ramo_sel')

    if ramo_sel != 'Todos' and 'ramo' in tman.columns:
        tview = tman[tman['ramo'].astype(str)==ramo_sel].reset_index(drop=True)
    else:
        tview = tman.copy()

    show_cols = [c for c in ['id','ramo','ordem','tipo_ini','de_no','para_no',
                             'dn_mm','de_ref_mm','pol_ref','comp_real_m','dz_io_m','peso_trecho'] if c in tview.columns]

    st.caption('Use os botões no final de cada linha para reordenar (↑, ↓) ou excluir (🗑).')
    head = st.columns([*([1]*len(show_cols)), 1.2], gap='small')
    for c, name in zip(head[:-1], show_cols):
        c.markdown(f"**{name}**")
    head[-1].markdown("**Ações**")

    tv = tview.reset_index(drop=True)
    for i, row in tv.iterrows():
        row_cols = st.columns([*([1]*len(show_cols)), 1.2], gap='small')
        for c, name in zip(row_cols[:-1], show_cols):
            c.markdown(f"{row.get(name, '')}")
        with row_cols[-1]:
            a1, a2, a3 = st.columns(3, gap='small')
            rid = str(row.get('id', '')).strip() or f"row_{i}"
            ramo_val = row.get('ramo', 'R')
            rid_key = f"{rid}_{ramo_val}_{i}"
            with a1:
                up = st.button("↑", key=f"mgr_up_{rid_key}", help="Mover para cima", disabled=(i==0))
            with a2:
                down = st.button("↓", key=f"mgr_down_{rid_key}", help="Mover para baixo", disabled=(i==len(tv)-1))
            with a3:
                delete = st.button("🗑", key=f"mgr_del_{rid_key}", help="Excluir esta linha")
        if up:
            _move_row_action(rid, ramo_val, 'up')
        if down:
            _move_row_action(rid, ramo_val, 'down')
        if delete:
            _delete_row_action(rid, ramo_val)
else:
    st.info('Nenhum trecho cadastrado ainda.')

# ---------------- TAB 2: L_eq (referencial) ----------------
with tab2:
    st.subheader('Comprimento Equivalente — editar por trecho (baseado no DN **referencial**)')
    base = pd.DataFrame(st.session_state['trechos'])
    if base.empty:
        st.info('Cadastre trechos na aba 1.')
    elif material_sistema == '(selecione)':
        st.warning('Selecione o Material do Sistema na barra lateral.')
    else:
        table_mat = pvc_table if (isinstance(material_sistema,str) and material_sistema.strip().lower()=='pvc') else fofo_table
        piece_cols, dn_name = piece_columns_for(table_mat)
        sel = st.selectbox('Selecione o trecho', [trecho_label(r) for _, r in base.iterrows()])
        if sel:
            idx_sel = None
            for idx, r in base.iterrows():
                if trecho_label(r) == sel:
                    idx_sel = idx
                    break
            if idx_sel is not None:
                eql_row, de_ref_mm, pol_ref = lookup_row_by_mm(table_mat, base.loc[idx_sel, 'dn_mm'])
                if piece_cols:
                    display_labels = [pretty(c) for c in piece_cols]
                    df = pd.DataFrame({
                        'Conexão/Peça': display_labels,
                        '(m)': [ _num(eql_row.get(c, 0.0), 0.0) for c in piece_cols ],
                        '(Qt.)': [0]*len(piece_cols),
                    }).set_index('Conexão/Peça')
                else:
                    df = pd.DataFrame({'Conexão/Peça': [], '(m)': [], '(Qt.)': []}).set_index('Conexão/Peça')
                edited = st.data_editor(
                    df,
                    use_container_width=True,
                    num_rows='fixed',
                    column_config={
                        '(m)': st.column_config.NumberColumn(disabled=True, format='%.2f'),
                        '(Qt.)': st.column_config.NumberColumn(min_value=0, step=1)
                    },
                    key=f'eq_editor_{idx_sel}'
                )
                leq_total = float((edited['(m)'] * edited['(Qt.)']).sum()) if not edited.empty else 0.0
                st.session_state['trechos'].loc[idx_sel, 'leq_m'] = leq_total
                st.success(f'L_eq total para o trecho selecionado: {leq_total:.2f} m')

# ---------------- TAB 3: Resultados ----------------
with tab3:
    st.subheader('Resultados')
    base = pd.DataFrame(st.session_state['trechos']).copy()
    if base.empty:
        st.info('Cadastre trechos na aba 1.')
    else:
        st.write('Em construção: aqui você pode calcular perdas, somatórios por ramo, etc.')
        params = {
            'projeto': projeto_nome,
            'material': material_sistema,
            'modelo_perda': modelo_perda,
            'notacao': notacao_mode,
            'capacidade': {'entrada': int(cap_ent), 'te': int(cap_te), 'cruzeta': int(cap_crz)}
        }
        show_cols = [c for c in BASE_COLS if c in base.columns]
        proj = {'params': params, 'trechos': base[show_cols].to_dict(orient='list')}
        st.download_button('Baixar projeto (.json)',
                           data=json.dumps(proj, ensure_ascii=False, indent=2).encode('utf-8'),
                           file_name='spaf_projeto.json', mime='application/json')

