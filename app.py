#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import streamlit as st
st.sidebar.caption(f"Streamlit {st.__version__}")
import pandas as pd
import numpy as np
import json

from core.excel_parser import load_three_sheets, normalize_peso_andar, normalize_compr_eq, normalize_exerc, normalize_quadro33
from core.weights import load_uc_default, build_pesos_uc_from_aparelhos, compute_uc_by_floor, vazao_probavel_from_uc
from core.losses import hazen_williams_j, perda_localizada
from core.reports import export_to_excel, export_to_pdf


st.set_page_config(page_title="Dimensionamento Água Fria – Barrilete e Colunas", layout="wide")

st.title("Dimensionamento de Tubulações de Água Fria – Barrilete e Colunas")

with st.sidebar:
    st.header("Parâmetros Globais")
    projeto_nome = st.text_input("Nome do Projeto", "Edifício Exemplo")
    andares_txt = st.text_area("Andares (do topo para o térreo)", "Cobertura\n6º\n5º\n4º\n3º\n2º\n1º\nTérreo")
    andares = [a.strip() for a in andares_txt.splitlines() if a.strip()]
    if "Barrilete" not in andares:
        andares = andares + ["Barrilete"]
    andares_sem_barr = [a for a in andares if a != "Barrilete"]

    st.markdown("---")
    st.subheader("UC → Vazão provável")
    k_uc = st.number_input("k (Q = k·UC^exp)", value=0.30, step=0.05, format="%.2f")
    exp_uc = st.number_input("exp (Q = k·UC^exp)", value=0.50, step=0.05, format="%.2f")

    st.markdown("---")
    st.subheader("Hazen–Williams")
    c_pvc = st.number_input("C (PVC)", value=150.0, step=5.0)
    c_fofo = st.number_input("C (Ferro Fundido)", value=130.0, step=5.0)

    st.markdown("---")
    st.subheader("Seleção de DN")
    metodo_dn = st.selectbox("Método", ["Velocidade", "Perda específica (J alvo)"])
    J_alvo = st.number_input("J alvo (m/m) – para método por perda específica", value=0.02, step=0.005)

    st.subheader("Velocidade admissível")
    v_min = st.number_input("v_min (m/s)", value=0.5, step=0.1)
    v_max = st.number_input("v_max (m/s)", value=3.0, step=0.1)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["1) Excel & UC", "2) Aptos por Andar", "3) Trechos", "4) Dimensionar & Pressões", "5) Exportar"])

with tab1:
    st.subheader("Carregar Excel (Exerc_4_(AF1) / Peso_Andar / Compr_Eq_(AF1))")
    up = st.file_uploader("Selecione o arquivo .xlsx", type=["xlsx"])

    st.markdown("**UC default (NBR 5626)**")
    uc_default = load_uc_default("data/uc_nbr5626.csv")
    st.dataframe(uc_default, use_container_width=True, height=220)
    st.caption("Você pode editar este CSV em `data/uc_nbr5626.csv` ou ajustar na aba 2 para cada projeto.")

    if up:
        parsed = load_three_sheets(up)
        st.success("Excel carregado.")

        if parsed.peso_andar is not None:
            tidy = normalize_peso_andar(parsed.peso_andar)
            st.markdown("**Aparelhos/Peças** (normalizado)")
            st.dataframe(tidy, use_container_width=True, height=260)

            # construir UC por aparelho com base no default
            tidy_cat = tidy.copy()
            tidy_cat["aparelho_full"] = tidy_cat[["aparelho","peca"]].fillna("").agg(lambda x: " - ".join([p for p in x if p]), axis=1).str.strip(" -")
            pesos_uc = build_pesos_uc_from_aparelhos(tidy_cat["aparelho_full"], uc_default)
            st.session_state["pesos_uc"] = pesos_uc.to_dict(orient="list")
            st.session_state["peso_andar_tidy"] = tidy.to_dict(orient="list")

            st.info("UC por aparelho inicializado a partir do CSV default. Ajuste os valores na aba 2 se necessário.")
        else:
            st.warning("Aba 'Peso_Andar' não encontrada.")

        if parsed.compr_eq is not None:
            ce = normalize_compr_eq(parsed.compr_eq)
            st.markdown("**Comprimentos equivalentes (rótulo de trecho, DN, Qt., Total m)**")
            st.dataframe(ce.head(200), use_container_width=True, height=260)
            st.session_state["compr_eq_norm"] = ce.to_dict(orient="list")
        else:
            st.warning("Aba 'Compr_Eq_(AF1)' não encontrada.")
        # Quadro 3.3 (PVC/FF) – tentativa de leitura
        if parsed.quadro_33_pvc is not None:
            q33p = normalize_quadro33(parsed.quadro_33_pvc)
            st.markdown("**Quadro 3.3 – PVC (leitura bruta)**")
            st.dataframe(q33p.head(100), use_container_width=True, height=200)
            st.session_state["q33_pvc"] = q33p.to_dict(orient="list")
        if parsed.quadro_33_ff is not None:
            q33f = normalize_quadro33(parsed.quadro_33_ff)
            st.markdown("**Quadro 3.3 – Ferro Fundido (leitura bruta)**")
            st.dataframe(q33f.head(100), use_container_width=True, height=200)
            st.session_state["q33_ff"] = q33f.to_dict(orient="list")
    

with tab2:
    st.subheader("UC por aparelho & Apartamentos por Andar")
    st.markdown("---")
    st.markdown("**Salvar/Carregar UC (CSV)**")
    uc_df = pd.DataFrame(st.session_state.get("pesos_uc", {}))
    if not uc_df.empty:
        csv_bytes = uc_df.to_csv(index=False).encode("utf-8")
        st.download_button("Baixar UC atual (.csv)", data=csv_bytes, file_name="uc_atual.csv", mime="text/csv")
    up_uc = st.file_uploader("Carregar UC (.csv)", type=["csv"], key="up_uc_csv")
    if up_uc is not None:
        try:
            new_uc = pd.read_csv(up_uc)
            if set(["aparelho_full","peso_uc"]).issubset(new_uc.columns):
                st.session_state["pesos_uc"] = new_uc.to_dict(orient="list")
                st.success("UC carregado e aplicado.")
            else:
                st.error("CSV inválido: precisa conter colunas 'aparelho_full' e 'peso_uc'.")
        except Exception as e:
            st.error(f"Erro ao ler CSV: {e}")
    
    pesos_uc = pd.DataFrame(st.session_state.get("pesos_uc", {}))
    if pesos_uc.empty:
        st.info("Carregue primeiro o Excel na aba 1.")
    else:
        st.markdown("**Editar UC por Aparelho/Peça**")
        pesos_uc = st.data_editor(pesos_uc, num_rows="dynamic", use_container_width=True)
        st.session_state["pesos_uc"] = pesos_uc.to_dict(orient="list")

        # Tabela de apartamentos por andar
        if "aptos_por_andar" not in st.session_state:
            base = pd.DataFrame(0, index=andares_sem_barr, columns=["AF1","AF2","AF3","AF4"], dtype=int)
            st.session_state["aptos_por_andar"] = base
        apt_tbl = pd.DataFrame(st.session_state["aptos_por_andar"])
        st.markdown("**Quantidade de apartamentos por tipo (AF1..AF4) em cada andar**")
        apt_tbl_edit = st.data_editor(apt_tbl, use_container_width=True, num_rows="fixed", key="apt_tbl_editor")
        st.session_state["aptos_por_andar"] = apt_tbl_edit

        # Repetir do andar anterior
        colA, colB = st.columns(2)
        if colA.button("Repetir dados do andar anterior (de cima para baixo)"):
            df = pd.DataFrame(st.session_state["aptos_por_andar"]).copy()
            for i in range(1, df.shape[0]):
                df.iloc[i] = df.iloc[i-1]
            st.session_state["aptos_por_andar"] = df
            st.success("Aplicado.")
        # Calcular UC e Q por andar
        tidy = pd.DataFrame(st.session_state.get("peso_andar_tidy", {}))
        if tidy.empty:
            st.warning("Sem tabela de aparelhos/peças normalizada.")
        else:
            uc_by_floor = compute_uc_by_floor(tidy, pd.DataFrame(st.session_state["pesos_uc"]), pd.DataFrame(st.session_state["aptos_por_andar"]))
            uc_by_floor["Q_l_s"] = uc_by_floor["UC_total"].apply(lambda u: vazao_probavel_from_uc(u, k_uc, exp_uc))
            st.markdown("**UC total e vazão provável por andar**")
            st.dataframe(uc_by_floor, use_container_width=True)
            st.session_state["uc_by_floor"] = uc_by_floor.to_dict(orient="index")

with tab3:
    st.subheader("Definição de Trechos (ramos, ordem e L_eq)")
    st.caption("Use 'rotulo' para casar com os rótulos da aba 'Compr_Eq_(AF1)' (ex.: 'E - F'). Informe 'ramo' e 'ordem' para permitir soma de perdas até cada pavimento.")

    if "trechos_df" not in st.session_state:
        cols = ["id","ramo","ordem","rotulo","de_no","para_no","andar","andares_atendidos","material","dn_mm","comp_real_m","leq_m"]
        st.session_state["trechos_df"] = pd.DataFrame(columns=cols)
    trechos_df = pd.DataFrame(st.session_state["trechos_df"])

    edited = st.data_editor(
        trechos_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "andar": st.column_config.SelectboxColumn(options=andares, required=False),
            "andares_atendidos": st.column_config.MultiselectColumn(options=andares_sem_barr, required=False),
            "material": st.column_config.SelectboxColumn(options=["PVC","FoFo"], required=False),
        },
        key="trechos_editor"
    )
    st.session_state["trechos_df"] = edited

    if st.button("Aplicar L_eq a partir dos rótulos (Compr_Eq_(AF1))"):
        ce = pd.DataFrame(st.session_state.get("compr_eq_norm", {}))
        if not ce.empty and "trecho" in ce.columns:
            leq_by_label = ce.groupby("trecho")["total_m"].sum().to_dict()
            tmp = pd.DataFrame(st.session_state["trechos_df"])
            tmp["leq_m"] = tmp["rotulo"].map(leq_by_label).fillna(tmp.get("leq_m",0))
            st.session_state["trechos_df"] = tmp
            st.success("L_eq aplicado.")
        else:
            st.warning("Não há dados normalizados de 'Compr_Eq_(AF1)'.")

with tab4:
    st.subheader("Dimensionar & Verificar Pressões")
    trechos = pd.DataFrame(st.session_state.get("trechos_df", {}))
    uc_idx = st.session_state.get("uc_by_floor", {})
    if trechos.empty or not uc_idx:
        st.info("Cadastre trechos na aba 3 e calcule UC por andar na aba 2.")
    else:
        uc_by_floor = pd.DataFrame.from_dict(uc_idx, orient="index")
        # vazões por trecho = UC das andares_atendidos convertidos por Q = k·UC^exp
        def uc_sum(lst):
            if not isinstance(lst, list): return 0.0
            return float(sum(uc_by_floor.loc[a]["UC_total"] for a in lst if a in uc_by_floor.index))

        trechos = trechos.copy()
        trechos["UC_total_trecho"] = trechos["andares_atendidos"].apply(uc_sum)
        trechos["Q (L/s)"] = trechos["UC_total_trecho"].apply(lambda u: vazao_probavel_from_uc(u, k_uc, exp_uc))

        # DN sugerido por método selecionado
        dn_padrao = [20,25,32,40,50,60,75,85,110,125,150,200]
        def select_dn(q_l_s):
            # retorna (DN, velocidade)
            if metodo_dn == "Perda específica (J alvo)":
                # Escolhe primeiro DN cujo J <= J_alvo (com C do material)
                best_dn = None; best_v = 0.0
                for dn in dn_padrao:
                    area = np.pi * (dn/1000.0)**2 / 4.0
                    v = (q_l_s/1000.0)/area if (q_l_s or 0)>0 else 0.0
                    Jpvc = hazen_williams_j(q_l_s, dn, c_pvc)
                    Jff  = hazen_williams_j(q_l_s, dn, c_fofo)
                    Jref = Jpvc  # usaremos material do trecho abaixo, mas aqui apenas pra ordenar
                    if Jref <= J_alvo:
                        best_dn, best_v = dn, v
                        break
                if best_dn is None:
                    best_dn = dn_padrao[-1]
                    area = np.pi * (best_dn/1000.0)**2 / 4.0
                    best_v = (q_l_s/1000.0)/area if (q_l_s or 0)>0 else 0.0
                return best_dn, best_v
            # Método velocidade (original)
            if (q_l_s or 0) <= 0: return None, 0.0
            best = None; best_v = None
            for dn in dn_padrao:
                area = np.pi * (dn/1000.0)**2 / 4.0
                v = (q_l_s/1000.0)/area
                if v_min <= v <= v_max:
                    best = dn; best_v = v; break
            if best is None:
                # pega o menor DN com v <= v_max, senão o maior
                candidates = []
                for dn in dn_padrao:
                    area = np.pi*(dn/1000.0)**2/4.0
                    v = (q_l_s/1000.0)/area
                    if v <= v_max: candidates.append((dn,v))
                if candidates:
                    best, best_v = candidates[0]
                else:
                    best, best_v = dn_padrao[-1], (q_l_s/1000.0)/(np.pi*(dn_padrao[-1]/1000.0)**2/4.0)
            return best, best_v

        dn_sug, vel = [], []
        for _, r in trechos.iterrows():
            dn, v = select_dn(r.get("Q (L/s)"))
            dn_sug.append(dn if pd.isna(r.get("dn_mm")) else r.get("dn_mm"))
            vel.append(v)

        trechos["DN_sugerido_mm"] = dn_sug
        trechos["velocidade (m/s)"] = vel

        # Hazen-Williams C por material
        def c_hw(material): return c_pvc if material=="PVC" else c_fofo
        trechos["J (m/m)"] = trechos.apply(lambda r: hazen_williams_j(r.get("Q (L/s)"), r.get("DN_sugerido_mm") or r.get("dn_mm"), c_hw(r.get("material"))), axis=1)
        trechos["hf_contínua (mca)"] = (trechos["J (m/m)"] * trechos.get("comp_real_m",0).fillna(0)).astype(float)
        trechos["hf_local (mca)"] = trechos.apply(lambda r: perda_localizada(r.get("leq_m",0) or 0, r.get("J (m/m)") or 0), axis=1)
        trechos["hf_total (mca)"] = trechos["hf_contínua (mca)"] + trechos["hf_local (mca)"]

        st.markdown("**Tabela de Trechos Calculada**")
        st.dataframe(trechos, use_container_width=True, height=420)

        # === Pressões por pavimento ===
        st.markdown("---")
        st.subheader("Pressões por Pavimento")
        col1, col2, col3 = st.columns(3)
        H_res = col1.number_input("Nível d'água do reservatório sup. (m) [referência: térreo = 0]", value=25.0, step=0.5)
        delta_h = col2.number_input("Altura entre pavimentos (m)", value=3.0, step=0.1)
        P_req = col3.number_input("Pressão requerida no ponto útil (m.c.a.)", value=5.0, step=0.5)

        # Gera cotas dos andares assumindo térreo = 0, andares acima com +n*delta_h, e ordem fornecida (topo→térreo)
        cotas = {}
        # construir mapeamento do topo ao térreo: o último da lista (excluindo Barrilete) é o térreo
        floors = [a for a in andares if a!="Barrilete"]
        for i, a in enumerate(reversed(floors)):
            # i = 0 para térreo
            cotas[a] = i * delta_h

        st.markdown("**Seleção do trecho final por pavimento (somatório de perdas no ramo até o pavimento)**")
        # Opção de ramo/ordem: computar acumulado por ramo
        trechos_sorted = trechos.sort_values(by=["ramo","ordem"], na_position="last").copy()
        trechos_sorted["hf_acum_ramo (mca)"] = trechos_sorted.groupby("ramo")["hf_total (mca)"].cumsum()
        # criar chave de identificação amigável
        trechos_sorted["id_label"] = trechos_sorted.apply(lambda r: f"{r.get('ramo','?')}-{int(r.get('ordem') or 0)} [{r.get('rotulo','')}] id={r.get('id','')}", axis=1)

        # construir seletores por pavimento filtrando trechos que atendem o andar
        escolha = {}
        for a in floors:
            options = trechos_sorted[trechos_sorted["andares_atendidos"].apply(lambda lst: isinstance(lst,list) and a in lst)]
            if options.empty:
                st.warning(f"Não há trechos marcados como atendendo '{a}'. Marque em 'andares_atendidos'.")
                continue
            sel = st.selectbox(f"Trecho final para {a}", options["id_label"].tolist(), key=f"sel_{a}")
            escolha[a] = sel

        # montar quadro de pressões
        rows = []
        for a in floors:
            if a not in escolha or a not in cotas: continue
            sel_label = escolha[a]
            row = trechos_sorted[trechos_sorted["id_label"]==sel_label].iloc[0]
            hf_path = float(row["hf_acum_ramo (mca)"])
            H_static = max(H_res - cotas[a], 0.0)
            P_disp = H_static - hf_path
            atende = P_disp >= P_req
            q_piso = float(uc_by_floor.loc[a]["Q_l_s"]) if a in uc_by_floor.index else 0.0
            rows.append({"andar": a, "cota (m)": cotas[a], "Q_piso (L/s)": q_piso, "hf_caminho (mca)": hf_path, "H_estática (mca)": H_static, "P_disp_residual (mca)": P_disp, "P_req (mca)": P_req, "Atende?": "SIM" if atende else "NÃO"})

        if rows:
            quadro = pd.DataFrame(rows).set_index("andar")
            st.markdown("**Quadro de verificação**")
            st.dataframe(quadro, use_container_width=True)
            st.session_state["quadro_pressoes"] = quadro.to_dict(orient="index")
        else:
            st.info("Defina os trechos finais por pavimento para ver o quadro.")

with tab5:
    st.markdown("---")
    st.subheader("Relatórios")
    trechos_df = pd.DataFrame(st.session_state.get("trechos_calc", {}))
    quadro_df = pd.DataFrame(st.session_state.get("quadro_pressoes", {})).T
    uc_by_floor = pd.DataFrame.from_dict(st.session_state.get("uc_by_floor", {}), orient="index") if st.session_state.get("uc_by_floor") else pd.DataFrame()

    if trechos_df.empty or quadro_df.empty or uc_by_floor.empty:
        st.info("Gere os cálculos nas abas anteriores para exportar relatórios.")
    else:
        params = {
            "k_uc": k_uc, "exp_uc": exp_uc, "c_pvc": c_pvc, "c_fofo": c_fofo,
            "v_min": v_min, "v_max": v_max
        }
        # Excel
        from io import BytesIO
        bio_xlsx = BytesIO()
        export_to_excel(bio_xlsx, trechos_df, quadro_df, uc_by_floor, params)
        st.download_button("Baixar relatório Excel (.xlsx)", data=bio_xlsx.getvalue(), file_name="relatorio_dim_agua_fria.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        # PDF
        bio_pdf = BytesIO()
        export_to_pdf(bio_pdf, trechos_df, quadro_df, uc_by_floor, params)
        st.download_button("Baixar relatório PDF (.pdf)", data=bio_pdf.getvalue(), file_name="relatorio_dim_agua_fria.pdf", mime="application/pdf")
    
    st.subheader("Exportar/Importar Projeto")
    proj = {
        "projeto_nome": projeto_nome,
        "andares": andares,
        "parms": {"k_uc": k_uc, "exp_uc": exp_uc, "c_pvc": c_pvc, "c_fofo": c_fofo, "v_min": v_min, "v_max": v_max},
        "peso_andar_tidy": st.session_state.get("peso_andar_tidy"),
        "pesos_uc": st.session_state.get("pesos_uc"),
        "aptos_por_andar": st.session_state.get("aptos_por_andar"),
        "compr_eq_norm": st.session_state.get("compr_eq_norm"),
        "trechos": st.session_state.get("trechos_df"),
        "quadro_pressoes": st.session_state.get("quadro_pressoes"),
    }
    j = json.dumps(proj, ensure_ascii=False, indent=2)
    st.download_button("Baixar projeto (.json)", data=j.encode("utf-8"), file_name="projeto_dim_agua_fria.json", mime="application/json")
    st.write("Para retomar, carregue este JSON e reconstrua as tabelas nas abas correspondentes.")

