#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import streamlit as st

def _st_rerun():
    # Compat handler without recursion
    if hasattr(st, 'rerun'):
        st.rerun()
    elif hasattr(st, 'experimental_rerun'):
        st.experimental_rerun()
    else:
        return

import pandas as pd
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
        dz_io_m = c8.number_input(
        "dz_io_m (m) (z_inicial - z_final; desce>0, sobe<0)",
        step=0.1, value=0.0, format="%.2f"
        )

        peso_trecho = st.number_input('peso_trecho (UC)', min_value=0.0, step=1.0, value=10.0, format='%.2f')
        c9,c10 = st.columns([1,1])
        tipo_ponto = c9.selectbox('Tipo do ponto no final do trecho', ['Sem utilização (5 kPa)','Ponto de utilização (10 kPa)'])
        p_min_ref_kPa = c10.number_input('p_min_ref (kPa)', min_value=0.0, step=0.5, value=(5.0 if 'Sem' in tipo_ponto else 10.0), format='%.2f')
        ok = st.form_submit_button("➕ Adicionar trecho", disabled=(material_sistema == "(selecione)"))
    

    if ok:
        mat_key = 'FoFo' if isinstance(material_sistema,str) and material_sistema.strip().lower()=='fofo' else 'PVC'
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

# ============================
# Painel de gerenciamento de trechos (excluir / mover)
# ============================

st.subheader('Gerenciar trechos')
import pandas as pd

def _move_row_action(row_id, ramo_val, direction):
    df = pd.DataFrame(st.session_state.get('trechos', pd.DataFrame()))
    if df.empty or 'ramo' not in df.columns or 'ordem' not in df.columns:
        return
    if 'id' not in df.columns:
        # fallback: attach a synthetic id based on current order
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
    # reatribui 'ordem' sequencial dentro do ramo
    for k, rid in enumerate(ids, start=1):
        df.loc[df['id']==rid, 'ordem'] = k
    st.session_state['trechos'] = df
    if hasattr(st, 'rerun'):
        st.rerun()
    else:
        st.experimental_rerun()

def _delete_row_action(row_id, ramo_val):
    df = pd.DataFrame(st.session_state.get('trechos', pd.DataFrame()))
    if df.empty:
        return
    if 'id' not in df.columns:
        df = df.reset_index().rename(columns={'index':'id'})
    df = df[df['id'] != row_id].reset_index(drop=True)
    if 'ramo' in df.columns and 'ordem' in df.columns:
        for r in df['ramo'].dropna().unique().tolist():
            mask = df['ramo']==r
            order_ids = df.loc[mask].sort_values('ordem', kind='stable')['id'].tolist()
            for k, rid in enumerate(order_ids, start=1):
                df.loc[df['id']==rid, 'ordem'] = k
    st.session_state['trechos'] = df
    if hasattr(st, 'rerun'):
        st.rerun()
    else:
        st.experimental_rerun()

if 'trechos' in st.session_state and isinstance(st.session_state['trechos'], pd.DataFrame) and not st.session_state['trechos'].empty:
    tman = st.session_state['trechos'].copy()
    if 'ramo' in tman.columns and 'ordem' in tman.columns:
        tman = tman.sort_values(['ramo','ordem'], kind='stable').reset_index(drop=True)
    else:
        tman = tman.reset_index(drop=True)
    r_opt = ['Todos'] + (sorted([str(x) for x in tman['ramo'].dropna().unique().tolist()]) if 'ramo' in tman.columns else [])
    ramo_sel = st.selectbox('Filtrar por ramo', r_opt or ['Todos'], key='manage_ramo_sel')
    if ramo_sel != 'Todos' and 'ramo' in tman.columns:
        tview = tman[tman['ramo'].astype(str)==ramo_sel].reset_index(drop=True)
    else:
        tview = tman.copy()

    default_cols = [c for c in ['id','ramo','ordem','de_no','para_no','dn_mm','de_ref_mm','pol_ref','comp_real_m','dz_io_m','peso_trecho'] if c in tview.columns]
    show_cols = default_cols

    st.caption('Use os botões no final de cada linha para reordenar (↑, ↓) ou excluir (🗑).')
    head = st.columns([*([1]*len(show_cols)), 1.2], gap='small')
    for c, name in zip(head[:-1], show_cols):
        c.markdown(f"**{name}**")
    head[-1].markdown("**Ações**")

    for i, row in tview.reset_index(drop=True).iterrows():
        row_cols = st.columns([*([1]*len(show_cols)), 1.2], gap='small')
        for c, name in zip(row_cols[:-1], show_cols):
            c.markdown(f"{row.get(name, '')}")
        with row_cols[-1]:
            a1, a2, a3 = st.columns(3, gap='small')
            with a1:
                up = st.button("↑", key=f"mgr_up_{row.get('id', i)}", help="Mover para cima", disabled=(i==0))
            with a2:
                down = st.button("↓", key=f"mgr_down_{row.get('id', i)}", help="Mover para baixo", disabled=(i==len(tview)-1))
            with a3:
                delete = st.button("🗑", key=f"mgr_del_{row.get('id', i)}", help="Excluir esta linha")
        rid = row.get('id', i)
        ramo_val = row.get('ramo', None)
        if up:
            _move_row_action(rid, ramo_val, 'up')
        if down:
            _move_row_action(rid, ramo_val, 'down')
        if delete:
            _delete_row_action(rid, ramo_val)
else:
    st.info('Nenhum trecho cadastrado ainda.')
# TAB 2 — L_eq por trecho (baseado no DN referencial)
with tab2:
    st.subheader('Comprimento Equivalente — editar por trecho (baseado no DN **referencial**)')
    base = pd.DataFrame(st.session_state['trechos'])
    if base.empty:
        st.info('Cadastre trechos na aba 1.')
    elif material_sistema == '(selecione)':
        st.warning('Selecione o Material do Sistema na barra lateral.')
    else:
        mat_key = 'FoFo' if isinstance(material_sistema,str) and material_sistema.strip().lower()=='fofo' else 'PVC'
        table_mat = pvc_table if mat_key=='PVC' else fofo_table
        st.caption(f'Tabela L_eq em uso: **{mat_key}**')
        piece_cols, dn_name = piece_columns_for(table_mat)
        base = base.copy()
        base['label'] = base.apply(trecho_label, axis=1)
        sel = st.selectbox('Selecione o trecho para preencher quantidades', base['label'].tolist())
        r = base[base['label']==sel].iloc[0]
        dn_ref = r.get('dn_mm')
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
    st.subheader('Resultados (kPa) — Propagação **Nodal** (p_out em B vira p_in dos trechos que começam em B)')
    st.caption('Fórmula: **p_out = p_in + γ·(z_i − z_f) − (h_f^cont + h_f^loc)**; γ = 9,80665 kPa/m')
    t3 = pd.DataFrame(st.session_state.get('trechos', {}))
    if t3.empty:
        st.info('Cadastre trechos e atribua L_eq na aba 2.')
    else:
        t3 = t3.copy()

        # Q provável (L/s)
        t3['Q (L/s)'] = (k_uc * (t3['peso_trecho'] ** exp_uc)).astype(float)

        # Gradiente J (kPa/m) e J (m/m)
        def _J_kPa(rr):
            if modelo_perda == 'Hazen-Williams':
                C = c_pvc if material_sistema=='PVC' else c_fofo
                j_mm = j_hazen_williams(rr['Q (L/s)'], rr['dn_mm'], C)  # m/m
                return j_mm * KPA_PER_M
            else:
                return j_fair_whipple_hsiao_kPa_per_m(rr['Q (L/s)'], rr['dn_mm'], material_sistema)
        t3['J (kPa/m)'] = t3.apply(_J_kPa, axis=1)
        t3['J (m/m)']   = t3['J (kPa/m)'] / KPA_PER_M

        # Velocidade v (m/s)
        import math
        def _vel(rr):
            Q = max(0.0, _num(rr['Q (L/s)'],0.0)) / 1000.0
            D = max(0.0, _num(rr['dn_mm'],0.0)) / 1000.0
            if D <= 0 or Q <= 0: return 0.0
            A = math.pi * (D**2) / 4.0
            return Q / A
        t3['v (m/s)'] = t3.apply(_vel, axis=1)

        # === UI Condições de contorno nos nós-fonte ===
        # Identificar nós-fonte (sem alimentador chegando)
        de_series = t3['de_no'].astype(str)
        para_series = t3['para_no'].astype(str)
        nodes = set(de_series.tolist()) | set(para_series.tolist())
        in_edge = {}
        for i, v in para_series.reset_index(drop=True).items():
            if str(v) not in in_edge:
                in_edge[str(v)] = i
        fontes = sorted([n for n in nodes if n not in in_edge])

        src_press_kPa = {}
        if fontes:
            with st.expander("Condições de contorno (nós-fonte)", expanded=False):
                st.caption("Informe H (m.c.a.) nos nós que **não têm** trecho chegando.")
                head_ref = st.selectbox("Padrão para nós-fonte", ["H_op (operacional)","H_max (espelho máx.)","H_min (espelho mín.)","Manual"], index=0,
                                        help="Valor padrão para preencher os campos; você pode sobrescrever nó a nó.")
                for n in fontes:
                    if head_ref.startswith("H_op"): h_default = H_res
                    elif head_ref.startswith("H_max"): h_default = H_max
                    elif head_ref.startswith("H_min"): h_default = H_min
                    else: h_default = 0.0
                    h_mca = st.number_input(f"H (m.c.a.) em {n}", value=float(h_default), step=0.1, format="%.2f", key=f"h_src_{n}")
                    src_press_kPa[n] = h_mca * KPA_PER_M

        # === Propagação Nodal ===
        out_edges = {}
        in_edge_idx = {}
        t3 = t3.reset_index(drop=True)
        for idx, row in t3.iterrows():
            u = str(row['de_no'])
            v = str(row['para_no'])
            out_edges.setdefault(u, []).append(idx)
            if v in in_edge_idx:
                st.error(f"Conflito: mais de um trecho termina no nó '{v}'. Índices {in_edge_idx[v]} e {idx}. Ajuste a rede para um único alimentador por nó.")
                st.stop()
            in_edge_idx[v] = idx
            out_edges.setdefault(v, out_edges.get(v, []))

        pressao_nos = {}
        for n in fontes:
            pressao_nos[n] = float(src_press_kPa.get(n, H_res * KPA_PER_M))

        t3['hf_cont (kPa)'] = 0.0
        t3['hf_loc (kPa)']  = 0.0
        t3['p_in (kPa)']    = pd.NA
        t3['p_out (kPa)']   = pd.NA
        t3['p_out (m.c.a.)']= pd.NA
        if 'p_min_ref_kPa' in t3.columns:
            t3['p_margin (kPa)'] = pd.NA
        t3['dZ_term (kPa)'] = pd.NA
        t3['hf_total (kPa)']= pd.NA

        from collections import deque
        q = deque(fontes)
        processed = set()
        visited_nodes = set(fontes)

        while q:
            u = q.popleft()
            p_u = float(pressao_nos.get(u, 0.0))
            for eidx in out_edges.get(u, []):
                if eidx in processed:
                    continue
                rr = t3.loc[eidx]
                v = str(rr['para_no'])
                J_kPa_m = _num(rr['J (kPa/m)'])
                L_real  = _num(rr.get('comp_real_m'), 0.0)
                L_eq    = _num(rr.get('leq_m'), 0.0)
                dz      = _num(rr.get('dz_io_m'), 0.0)

                hf_cont = J_kPa_m * L_real
                hf_loc  = J_kPa_m * L_eq
                p_out = p_u + KPA_PER_M*dz - (hf_cont + hf_loc)

                dZ_term = KPA_PER_M*dz
                hf_total = (hf_cont + hf_loc)

                t3.at[eidx, 'hf_cont (kPa)'] = round(hf_cont, 3)
                t3.at[eidx, 'hf_loc (kPa)']  = round(hf_loc, 3)
                t3.at[eidx, 'p_in (kPa)']    = round(p_u, 3)
                t3.at[eidx, 'p_out (kPa)']   = round(p_out, 3)
                t3.at[eidx, 'p_out (m.c.a.)']= round(p_out / KPA_PER_M, 3)
                t3.at[eidx, 'dZ_term (kPa)'] = round(dZ_term, 3)
                t3.at[eidx, 'hf_total (kPa)']= round(hf_total, 3)
                if 'p_min_ref_kPa' in t3.columns:
                    t3.at[eidx, 'p_margin (kPa)'] = round(p_out - _num(rr.get('p_min_ref_kPa'),0.0), 3)

                if v in pressao_nos and abs(pressao_nos[v] - p_out) > 1e-6:
                    st.warning(f"Pressão no nó '{v}' já definida (={pressao_nos[v]:.3f} kPa) e difere do novo valor (={p_out:.3f} kPa). Verifique a rede.")
                pressao_nos[v] = p_out

                processed.add(eidx)
                if v not in visited_nodes:
                    visited_nodes.add(v)
                    q.append(v)

        if len(processed) != len(t3):
            pend = sorted(set(range(len(t3))) - processed)
            st.error(f"Não foi possível propagar para {len(pend)} trecho(s): {pend}. "
                     f"Causas comuns: ciclos na rede ou ausência de nós-fonte com pressão definida.")

        ordenar = st.checkbox('Ordenar por ramo/ordem (apenas visual)', value=False,
                              help='Não afeta o cálculo. O cálculo é topológico por nós.')
        if ordenar and 'ramo' in t3.columns and 'ordem' in t3.columns:
            t_out = t3.sort_values(by=['ramo','ordem'], kind='mergesort', na_position='last').reset_index(drop=True)
        else:
            t_out = t3

        show_cols = [c for c in [
            'id','ramo','ordem','de_no','para_no','dn_mm','de_ref_mm','pol_ref',
            'comp_real_m','leq_m','dz_io_m','peso_trecho',
            'Q (L/s)','v (m/s)','J (kPa/m)','J (m/m)',
            'p_in (kPa)','dZ_term (kPa)','hf_cont (kPa)','hf_loc (kPa)','hf_total (kPa)','p_out (kPa)','p_out (m.c.a.)',
            'p_min_ref_kPa','p_margin (kPa)'
        ] if c in t_out.columns]

        st.dataframe(t_out[show_cols], use_container_width=True, height=560)

        with st.expander('🔍 Diagnóstico do balanço por trecho', expanded=False):
            dbg_cols = [c for c in ['id','de_no','para_no','p_in (kPa)','dZ_term (kPa)','hf_cont (kPa)','hf_loc (kPa)','hf_total (kPa)','p_out (kPa)'] if c in t_out.columns]
            if dbg_cols:
                st.dataframe(t_out[dbg_cols], use_container_width=True, height=320)
            else:
                st.info('Sem colunas diagnósticas disponíveis.')

        params = {'projeto': projeto_nome, 'material': material_sistema, 'modelo_perda': modelo_perda,
                  'k_uc': k_uc, 'exp_uc': exp_uc, 'C_PVC': c_pvc, 'C_FoFo': c_fofo,
                  'H_max_m': H_max, 'H_min_m': H_min, 'H_op_m': H_res, 'KPA_PER_M': KPA_PER_M}
        proj = {'params': params, 'trechos': t_out[show_cols].to_dict(orient='list')}
        st.download_button('Baixar projeto (.json)',
                           data=json.dumps(proj, ensure_ascii=False, indent=2).encode('utf-8'),
                           file_name='spaf_projeto.json', mime='application/json')
