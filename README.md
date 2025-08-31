# SPAF – Dimensionamento de Água Fria (Simplificado)

Fluxo:
1. Cadastre **trechos** (ramo, ordem, nós, material, DN, comprimento real, Δz, peso).
2. Para cada trecho, informe **quantidades** de peças/acessórios — o app busca L_eq por material+DN.
3. Veja **Q provável**, **J (Hazen–Williams)**, **hf contínua/local/total**, acúmulos por **ramo** e **pressão disponível**.
4. Exporte Excel/PDF ou JSON do projeto.

## Rodar
```bash
pip install -r requirements.txt
streamlit run app.py
```
