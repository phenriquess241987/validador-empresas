import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Importador de Planilhas", layout="centered")
st.title("📊 Importador de Dados Empresariais")

# 🔹 Instruções iniciais
st.markdown("### 📎 Baixe a planilha modelo para garantir o formato correto")
st.markdown("A planilha deve conter as colunas: **CNPJ**, **Nome**, **Telefone**")

# 🔹 Gerar planilha modelo
modelo_df = pd.DataFrame({
    "CNPJ": ["00000000000000"],
    "Nome": ["Empresa Exemplo"],
    "Telefone": ["(00) 00000-0000"]
})

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
    modelo_df.to_excel(writer, index=False, sheet_name="Modelo")

st.download_button(
    label="📥 Baixar planilha modelo",
    data=excel_buffer.getvalue(),
    file_name="modelo_planilha.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# 🔹 Upload da planilha do usuário
st.markdown("### 📤 Envie sua planilha preenchida")
uploaded_file = st.file_uploader("Selecione o arquivo Excel (.xlsx)", type=["xlsx"])

# 🔹 Validação da estrutura
colunas_esperadas = ["CNPJ", "Nome", "Telefone"]

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)

        # Verifica se todas as colunas esperadas estão presentes
        if all(col in df.columns for col in colunas_esperadas):
            st.success("✅ Planilha válida! Pronta para ser processada.")
            st.dataframe(df)
            # Aqui você pode incluir o código para salvar no banco de dados
        else:
            st.error("❌ Estrutura inválida. Certifique-se de que sua planilha contém as colunas: CNPJ, Nome, Telefone.")
            st.write("Colunas encontradas:", list(df.columns))

    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
