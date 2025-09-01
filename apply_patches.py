#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_patches.py
Aplica correções no app Streamlit do SPAF:
- p_in/p_disp/p_out (minúsculas) e fórmula p_out = p_in + γΔz − hf_cont − hf_loc
- FWH em kPa/m (PVC/FoFo), HW com conversão m/m→kPa/m
- Velocidade v (m/s)
- p_min_ref (kPa) na aba Trechos
- Tabelas L_eq robustas + seleção correta PVC/FoFo
- Editor L_eq reinicia ao trocar material
- Painel "Gerenciar trechos" (excluir/mover)
Uso:
    python apply_patches.py /caminho/para/spaf/app.py
"""
import sys, re, io, os, json, unicodedata
from pathlib import Path

def patch_text(src: str) -> str:
    out = src

    # ---- 1) Caminhos dos CSV em data/ ----
    out = out.replace("pvc_perda_local_equivalente.csv", "data/pvc_pl_eqlen.csv")
    out = out.replace("fofo_perda_local_equivalente.csv", "data/fofo_pl_eqlen.csv")

    # ---- 2) Função FWH em kPa/m por material ----
    if "j_fair_whipple_hsiao_kPa_per_m" not in out:
        out = out.replace(
            "def j_hazen_williams(",
            "def j_fair_whipple_hsiao_kPa_per_m(Q_Ls, D_mm, material: str):\n"
            "    Q = max(0.0, _num(Q_Ls, 0.0))\n"
            "    D = max(0.0, _num(D_mm, 0.0))\n"
            "    if D <= 0.0:\n"
            "        return 0.0\n"
            "    mat = (material or '').strip().lower()\n"
            "    if mat == 'pvc':\n"
            "        return 8.695e6 * (Q ** 1.75) / (D ** 4.75)\n"
            "    else:\n"
            "        return 20.2e6  * (Q ** 1.88) / (D ** 4.88)\n\n"
            "def j_hazen_williams("
        )

    # ---- 3) J(kPa/m) + J(m/m) ----
    out = re.sub(
        r"t3\['J \(m/m\)'\]\s*=\s*.*?t3\['J \(kPa/m\)'\]\s*=\s*.*?\n",
        "        def _J_kPa(rr):\n"
        "            if modelo_perda == 'Hazen-Williams':\n"
        "                C = c_pvc if material_sistema=='PVC' else c_fofo\n"
        "                j_mm = j_hazen_williams(rr['Q (L/s)'], rr['dn_mm'], C)\n"
        "                return j_mm * KPA_PER_M\n"
        "            else:\n"
        "                return j_fair_whipple_hsiao_kPa_per_m(rr['Q (L/s)'], rr['dn_mm'], material_sistema)\n"
        "        t3['J (kPa/m)'] = t3.apply(_J_kPa, axis=1)\n"
        "        t3['J (m/m)']   = t3['J (kPa/m)'] / KPA_PER_M\n",
        out, flags=re.DOTALL
    )

    # ---- 4) Velocidade v (m/s) ----
    if "v (m/s)" not in out:
        out = out.replace(
            "t3['J (m/m)']   = t3['J (kPa/m)'] / KPA_PER_M",
            "t3['J (m/m)']   = t3['J (kPa/m)'] / KPA_PER_M\n"
            "        import math\n"
            "        def _vel(rr):\n"
            "            Q = max(0.0, _num(rr['Q (L/s)'],0.0)) / 1000.0\n"
            "            D = max(0.0, _num(rr['dn_mm'],0.0)) / 1000.0\n"
            "            if D <= 0 or Q <= 0: return 0.0\n"
            "            A = math.pi * (D**2) / 4.0\n"
            "            return Q / A\n"
            "        t3['v (m/s)'] = t3.apply(_vel, axis=1)"
        )
        out = out.replace(
            "'peso_trecho','leq_m','Q (L/s)','J (kPa/m)',",
            "'peso_trecho','leq_m','Q (L/s)','v (m/s)','J (kPa/m)',"
        )

    # ---- 5) p_min_ref_kPa no cadastro de trechos ----
    out = re.sub(
        r"peso_trecho\s*=\s*st\.number_input\([^\n]+\)\n\s*ok\s*=\s*st\.form_submit_button\([^\)]*\)",
        "peso_trecho = st.number_input('peso_trecho (UC)', min_value=0.0, step=1.0, value=10.0, format='%.2f')\n"
        "        c9,c10 = st.columns([1,1])\n"
        "        tipo_ponto = c9.selectbox('Tipo do ponto no final do trecho', ['Sem utilização (5 kPa)','Ponto de utilização (10 kPa)'])\n"
        "        p_min_ref_kPa = c10.number_input('p_min_ref (kPa)', min_value=0.0, step=0.5, value=(5.0 if 'Sem' in tipo_ponto else 10.0), format='%.2f')\n"
        "        ok = st.form_submit_button('➕ Adicionar trecho', disabled=(material_sistema=='(selecione)'))",
        out
    )
    out = out.replace(
        "'peso_trecho','leq_m']",
        "'peso_trecho','leq_m','p_min_ref_kPa']"
    ).replace(
        "'peso_trecho':'float','leq_m':'float'}",
        "'peso_trecho':'float','leq_m':'float','p_min_ref_kPa':'float'}"
    ).replace(
        "'peso_trecho':float(peso_trecho),'leq_m':0.0}",
        "'peso_trecho':float(peso_trecho),'leq_m':0.0,'p_min_ref_kPa':float(p_min_ref_kPa)}"
    )

    # ---- 6) Fórmula e nomenclatura p_in/p_disp/p_out ----
    out = out.replace("P_in (kPa)", "p_in (kPa)").replace("P_out (kPa)", "p_out (kPa)").replace("hf_alt (kPa)", "p_disp (kPa)")
    out = out.replace("Pressão inicial em A (kPa)", "p_in em A (kPa)")

    # loop de propagação (p_in inicial, p_out e avanço)
    out = re.sub(
        r"for ramo, grp in t3\.groupby\('ramo', sort=False\):[\s\S]*?results = \[\]",
        "for ramo, grp in t3.groupby('ramo', sort=False):\n"
        "            p_in = H_res * KPA_PER_M\n"
        "            results = []",
        out
    )
    out = re.sub(
        r"for _, r in grp\.iterrows\(\):[\s\S]*?row = r\.to_dict\(\)",
        "for _, r in grp.iterrows():\n"
        "                J_kPa_m = _num(r['J (kPa/m)'])\n"
        "                hf_cont = J_kPa_m * _num(r['comp_real_m'])\n"
        "                hf_loc  = J_kPa_m * _num(r['leq_m'])\n"
        "                p_disp  = KPA_PER_M * _num(r.get('dz_io_m', 0.0))\n"
        "                p_out   = p_in + p_disp - hf_cont - hf_loc\n"
        "                row = r.to_dict()",
        out, flags=re.DOTALL
    )
    out = out.replace(
        "{'P_in (kPa)': P_in,",
        "{'p_in (kPa)': p_in,"
    ).replace(
        "'P_out (kPa)': P_out",
        "'p_out (kPa)': p_out"
    ).replace(
        "'hf_alt (kPa)': hf_alt",
        "'p_disp (kPa)': p_disp"
    )
    out = re.sub(r"results\.append\(row\)\s*\n", "results.append(row)\n                p_in = p_out\n", out)

    # ---- 7) Legenda da fórmula ----
    out = out.replace(
        "st.subheader('Resultados (kPa) — com J em kPa/m e pressão inicial no ponto A')",
        "st.subheader('Resultados (kPa) — com J em kPa/m e pressão inicial no ponto A')\n"
        "    st.caption('Fórmula: **p_out = p_in + γ·(z_i − z_f) − h_f^cont − h_f^loc**; γ = 9,80665 kPa/m')"
    )

    # ---- 8) L_eq: seleção robusta e reset do editor ----
    out = out.replace(
        "table_mat = pvc_table if material_sistema=='PVC' else fofo_table",
        "mat_key = 'FoFo' if isinstance(material_sistema,str) and material_sistema.strip().lower()=='fofo' else 'PVC'\n"
        "        table_mat = pvc_table if mat_key=='PVC' else fofo_table\n"
        "        st.caption(f'Tabela L_eq em uso: **{mat_key}**')"
    )
    out = out.replace(
        "dn_ref = r.get('de_ref_mm') or r.get('dn_mm')",
        "dn_ref = r.get('dn_mm')"
    )
    out = out.replace("key=f'eq_editor_{sel}'", "key=f'eq_editor_{mat_key}_{sel}'")

    # ---- 9) Painel de gerenciamento (excluir/mover) ----
    if "Gerenciar trechos" not in out:
        out = re.sub(
            r"(st\.form_submit_button\([^\)]*\))",
            r"\1\n"
            r"    # ============================\n"
            r"    # Painel de gerenciamento de trechos (excluir / mover)\n"
            r"    # ============================\n"
            r"    st.subheader(\"Gerenciar trechos\")\n"
            r"    if 'trechos' in st.session_state and isinstance(st.session_state['trechos'], pd.DataFrame) and not st.session_state['trechos'].empty:\n"
            r"        tman = st.session_state['trechos'].copy()\n"
            r"        if 'ramo' in tman.columns and 'ordem' in tman.columns:\n"
            r"            tman = tman.sort_values(['ramo','ordem']).reset_index(drop=True)\n"
            r"        else:\n"
            r"            tman = tman.reset_index(drop=True)\n"
            r"        r_opt = ['Todos'] + (sorted([str(x) for x in tman['ramo'].dropna().unique().tolist()]) if 'ramo' in tman.columns else [])\n"
            r"        ramo_sel = st.selectbox('Filtrar por ramo', r_opt or ['Todos'], key='manage_ramo_sel')\n"
            r"        if ramo_sel != 'Todos' and 'ramo' in tman.columns:\n"
            r"            tview = tman[tman['ramo'].astype(str)==ramo_sel].reset_index(drop=True)\n"
            r"        else:\n"
            r"            tview = tman.copy()\n"
            r"        st.write('Clique para **excluir** ou **mover** o trecho na ordem. As alterações são imediatas e afetam as demais abas.')\n"
            r"        for idx in tview.index:\n"
            r"            r = tview.loc[idx]\n"
            r"            cols = st.columns([2,2,2,2,8])\n"
            r"            with cols[4]:\n"
            r"                st.write(f\"**{r.get('ramo','?')}-{r.get('ordem','?')}**  [{r.get('de_no','?')} → {r.get('para_no','?')}]  DN={r.get('dn_mm','?')} mm  L={r.get('comp_real_m','?')} m\")\n"
            r"            with cols[0]:\n"
            r"                if st.button('🗑️ Excluir', key=f\"del_{r.name}_{r.get('ramo','')}_{r.get('ordem','')}\"):\n"
            r"                    mask = (tman['ramo'].astype(str)==str(r.get('ramo'))) & (tman['ordem']==r.get('ordem')) & (tman['de_no']==r.get('de_no')) & (tman['para_no']==r.get('para_no'))\n"
            r"                    t_new = tman.loc[~mask].copy().reset_index(drop=True)\n"
            r"                    if all(c in t_new.columns for c in ['ramo','ordem']):\n"
            r"                        t_new['ordem'] = t_new.groupby('ramo').cumcount()+1\n"
            r"                    st.session_state['trechos'] = t_new\n"
            r"                    st.experimental_rerun()\n"
            r"            with cols[1]:\n"
            r"                if st.button('⬆️ Subir', key=f\"up_{r.name}_{r.get('ramo','')}_{r.get('ordem','')}\"):\n"
            r"                    if all(c in tman.columns for c in ['ramo','ordem']):\n"
            r"                        ramo_v = r.get('ramo'); ordem_v = int(r.get('ordem') or 1)\n"
            r"                        if ordem_v > 1:\n"
            r"                            i1 = (tman['ramo']==ramo_v) & (tman['ordem']==ordem_v)\n"
            r"                            i2 = (tman['ramo']==ramo_v) & (tman['ordem']==ordem_v-1)\n"
            r"                            tman.loc[i1,'ordem'] = ordem_v-1\n"
            r"                            tman.loc[i2,'ordem'] = ordem_v\n"
            r"                            t_new = tman.sort_values(['ramo','ordem']).reset_index(drop=True)\n"
            r"                            st.session_state['trechos'] = t_new\n"
            r"                            st.experimental_rerun()\n"
            r"            with cols[2]:\n"
            r"                if st.button('⬇️ Descer', key=f\"down_{r.name}_{r.get('ramo','')}_{r.get('ordem','')}\"):\n"
            r"                    if all(c in tman.columns for c in ['ramo','ordem']):\n"
            r"                        ramo_v = r.get('ramo'); ordem_v = int(r.get('ordem') or 1)\n"
            r"                        max_ord = int(tman.loc[tman['ramo']==ramo_v, 'ordem'].max())\n"
            r"                        if ordem_v < max_ord:\n"
            r"                            i1 = (tman['ramo']==ramo_v) & (tman['ordem']==ordem_v)\n"
            r"                            i2 = (tman['ramo']==ramo_v) & (tman['ordem']==ordem_v+1)\n"
            r"                            tman.loc[i1,'ordem'] = ordem_v+1\n"
            r"                            tman.loc[i2,'ordem'] = ordem_v\n"
            r"                            t_new = tman.sort_values(['ramo','ordem']).reset_index(drop=True)\n"
            r"                            st.session_state['trechos'] = t_new\n"
            r"                            st.experimental_rerun()\n"
            r"            with cols[3]:\n"
            r"                pass\n"
            r"    else:\n"
            r"        st.info('Nenhum trecho cadastrado ainda.')",
            out, count=1
        )

    return out

def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    app_path = Path(sys.argv[1]).resolve()
    src = app_path.read_text(encoding='utf-8')
    patched = patch_text(src)
    app_path.write_text(patched, encoding='utf-8')
    print(f'OK: patches aplicados em {app_path}')

if __name__ == "__main__":
    main()
