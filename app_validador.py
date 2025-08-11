import streamlit as st
import pandas as pd
from urllib.parse import quote

st.set_page_config(page_title="Validador de Empresas", page_icon="📇", layout="centered")

st.image("logo.png", width=120)
st.title("📇 Validador de Empresas")
st.markdown("Envie sua planilha e gere links personalizados de WhatsApp para cada empresa.")

# Upload da planilha
arquivo = st.file_uploader("📤 Envie sua planilha (.xlsx)", type=["xlsx"])

if arquivo:
    df = pd.read_excel(arquivo)

    # Verifica se colunas obrigatórias existem
    colunas_necessarias = {"Nome", "CNPJ", "Telefone", "Situação"}
    if not colunas_necessarias.issubset(df.columns):
        st.error("A planilha deve conter as colunas: Nome, CNPJ, Telefone, Situação")
    else:
        # Filtro por situação
        situacoes = df["Situação"].unique()
        filtro = st.selectbox("🔍 Filtrar por situação", options=["Todas"] + list(situacoes))

        if filtro != "Todas":
            df = df[df["Situação"] == filtro]

        # Mensagem personalizada
        mensagem_base = st.text_input("✉️ Mensagem para WhatsApp", 
            value="Olá, {nome}! Temos uma proposta especial para sua empresa.")

        # Geração dos links
        def gerar_link(telefone, nome):
            numero = ''.join(filter(str.isdigit, str(telefone)))
            texto = mensagem_base.replace("{nome}", nome)
            return f"https://wa.me/{numero}?text={quote(texto)}"

        df["Link WhatsApp"] = df.apply(lambda row: gerar_link(row["Telefone"], row["Nome"]), axis=1)

        st.success("✅ Links gerados com sucesso!")
        st.dataframe(df)

        # Botão de download
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar resultados", data=csv, file_name="empresas_com_links.csv", mime="text/csv")