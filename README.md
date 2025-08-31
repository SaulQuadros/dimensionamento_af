# Dimensionamento de Tubulações de Água Fria — Barrilete e Colunas (Streamlit)

Aplicativo em **Streamlit** para auxiliar o **pré-dimensionamento** do barrilete e das colunas de água fria
em edificações, com base em planilhas de entrada no padrão utilizado pelo autor (NBR 5626 como referência).
Inclui cálculo de **vazões prováveis** a partir de **UC** (unidades de consumo), perdas **contínuas** (Hazen–Williams)
e **localizadas** (comprimentos equivalentes), seleção de **DN** por **velocidade** ou por **perda específica alvo (J)**,
e verificação de **pressões por pavimento**. Gera **relatórios Excel** e **PDF**.

> **Aviso:** Este software é de apoio ao projeto e não substitui a responsabilidade técnica do projetista.
Revise parâmetros, limites normativos e hipóteses adotadas antes de usar em projetos executivos.

---

## ✨ Principais recursos
- Importa Excel com abas: `Exerc_4_(AF1)`, `Peso_Andar`, `Compr_Eq_(AF1)` (opcional: `Quadro 3.3_PVC` e `Quadro 3.3_FF`).
- Editor de **UC** por aparelho/peça (com **CSV default** em `data/uc_nbr5626.csv` + **Salvar/Carregar UC**).
- Grade **Andar × Tipos de apto (AF1..AF4)** com **Repetir dados do andar anterior**.
- Definição de **trechos** (ramos, ordem, material, DN, L_eq) e **link com rótulos** da planilha de comprimentos equivalentes.
- Seleção de **DN** por **velocidade** ou por **perda específica alvo (J)**.
- Cálculo de **hf contínua** + **hf localizada**, **acumulados por ramo** e **quadro de pressões por pavimento**.
- Exporta **projeto (.json)**, **relatório Excel (.xlsx)** e **PDF (.pdf)**.

---

## 🚀 Como rodar localmente
```bash
git clone https://github.com/<seu-usuario>/<seu-repo>.git
cd <seu-repo>
pip install -r requirements.txt
streamlit run app.py
```

### Requisitos
- Python 3.10+
- Bibliotecas listadas em `requirements.txt` (inclui: streamlit, pandas, numpy, networkx, openpyxl, xlsxwriter, plotly, pydantic, reportlab).

---

## 📁 Estrutura do projeto
```
app.py
core/
  excel_parser.py    # leitura/normalização das planilhas
  weights.py         # UC, vazões prováveis e agregações
  network.py         # modelo de trechos (ramos/ordem)
  losses.py          # Hazen–Williams e perdas localizadas
  reports.py         # exportação Excel e PDF
data/
  pvc_perda_local_equivalente.csv   # L_eq para PVC
  fofo_perda_local_equivalente.csv  # L_eq para Ferro Fundido
  uc_nbr5626.csv                    # UC default (edite conforme sua tabela)
assets/ (opcional para imagens/ícones)
README.md
LICENSE
NOTICE
```

---

## 📥 Entrada (Excel)
- **Obrigatórias**:
  - `Peso_Andar`: lista de **aparelhos/peças** e **quantidades por AF1..AF4** (o app normaliza automaticamente).
  - `Compr_Eq_(AF1)`: tabela de **rótulos de trechos** (ex.: `E - F`) com **DN**, **Qt.** e **Total (m)** para gerar **L_eq**.
- **Opcional**:
  - `Exerc_4_(AF1)`: quadro de **pressões** (usado como referência).
  - `Quadro 3.3_PVC`, `Quadro 3.3_FF`: ajudam na leitura de curvas/tabelas. Quando não for possível extrair,
    use o método por **J alvo**.

> Dica: se seus cabeçalhos tiverem células mescladas, o app usa heurísticas; verifique o preview após o upload.

---

## 🔧 Uso básico (workflow)
1. **Aba 1 — Excel & UC**: carregue seu `.xlsx`. Revise a tabela de UC vinda de `data/uc_nbr5626.csv` (ou carregue um CSV próprio).
2. **Aba 2 — Aptos por Andar**: preencha a grade AF1..AF4 por andar. Use **Repetir** se os andares forem iguais.
3. **Aba 3 — Trechos**: cadastre trechos (ramo/ordem/andar/material/DN/compr/L_eq). Clique **Aplicar L_eq por rótulos** para buscar
   os comprimentos equivalentes a partir de `Compr_Eq_(AF1)`.
4. **Aba 4 — Dimensionar & Pressões**: escolha método de **DN** (velocidade ou **J alvo**), informe **nível do reservatório**,
   **altura entre pavimentos** e **P_req**. Selecione o **trecho final por pavimento** para somatório de perdas.
5. **Aba 5 — Exportar**: baixe o **Excel** e/ou **PDF** com os resultados e o **JSON** do projeto.

---

## 🧪 Parâmetros importantes
- **UC → Q**: `Q = k · (UC)^exp` (ajustáveis na sidebar).  
- **Hazen–Williams**: `C` configurável por material (**PVC** e **Ferro Fundido**).  
- **DN**: por **velocidade** (faixa `v_min`–`v_max`) **ou** por **perda específica alvo (J)**.  
- **Unidades**: L/s, m, mm, m.c.a (1 m.c.a ≈ 9,81 kPa).

---

## 📝 Licenças
- **Código**: [Apache License 2.0](./LICENSE)  
- **Documentação (README e guias)**: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)  
- **Datasets de exemplo (`data/`)**: [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)  
- Veja o arquivo [NOTICE](./NOTICE) para créditos e bibliotecas utilizadas.

---

## 🤝 Contribuindo
Contribuições são bem-vindas! Abra uma **issue** com bugs/idéias ou envie um **pull request**.
Antes de contribuir, descreva claramente o cenário, inputs (planilhas) e o resultado esperado.

---

## 📚 Referência
- **ABNT NBR 5626** — Instalação predial de água fria – Projeto, execução e manutenção.

---

## ✍️ Citação sugerida
> Quadros, S. (2025). *Dimensionamento de Tubulações de Água Fria — Barrilete e Colunas (Streamlit)*. GitHub repository. Disponível em: https://github.com/<seu-usuario>/<seu-repo>

