import streamlit as st
import pandas as pd
import requests
import time
import psycopg2
import matplotlib.pyplot as plt
import io
from openpyxl import Workbook
from datetime import date

# 🔌 Conectar ao banco Neon via secrets
conn = psycopg2.connect(st.secrets["database"]["url"])
cursor = conn.cursor()

# 🧱 Criar tabela se não existir
cursor.execute("""
    CREATE TABLE IF NOT EXISTS empresas (
        id SERIAL PRIMARY KEY,
        cnpj TEXT,
        nome TEXT,
        telefone TEXT,
        situacao_rf TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
""")
conn.commit()

# 🔍 Função para consultar CNPJ na ReceitaWS
def consultar_cnpj(cnpj):
    cnpj = ''.join(filter(str.isdigit, str(cnpj)))
    url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj}"
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            dados = response.json()
            return dados.get("situacao", "Não encontrado")
        else:
            return f"Erro {response.status_code}"
    except Exception as e:
        return f"Erro: {str(e)}"

# ⏱️ Contagem regressiva visual
def contagem_regressiva(segundos):
    for i in range(segundos, 0, -1):
        st.write(f"⏳ Próximo lote em {i} segundos...")
        time.sleep(1)

# 🖥️ Interface com abas
st.set_page_config(page_title="Validador de CNPJs", layout="wide")
st.title("🔍 Validador de CNPJs com ReceitaWS + Banco Neon")
aba1, aba2, aba3 = st.tabs(["📤 Validação", "📊 Dashboard", "📦 Histórico"])

with aba1:
    st.subheader("📤 Validação de CNPJs")

    st.markdown("### 📎 Baixe a planilha modelo para garantir o formato correto")
    st.markdown("A planilha deve conter as colunas: **CNPJ**, **Nome**, **Telefone**")

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

    arquivo = st.file_uploader("📄 Envie sua planilha preenchida", type=["xlsx", "csv"])
    colunas_esperadas = ["CNPJ", "Nome", "Telefone"]

    if "df_validacao" not in st.session_state:
        st.session_state.df_validacao = None
    if "indice_lote" not in st.session_state:
        st.session_state.indice_lote = 0
    if "pausado" not in st.session_state:
        st.session_state.pausado = False

    tempo_entre_lotes = st.slider("⏱️ Tempo entre lotes (segundos)", min_value=1, max_value=30, value=5)

    if arquivo and st.session_state.df_validacao is None:
        df = pd.read_excel(arquivo) if arquivo.name.endswith(".xlsx") else pd.read_csv(arquivo)

        if all(col in df.columns for col in colunas_esperadas):
            erros = []

            df["CNPJ"] = df["CNPJ"].astype(str).str.replace(r"\D", "", regex=True)
            df["Telefone"] = df["Telefone"].astype(str)

            for i, row in df.iterrows():
                cnpj = row["CNPJ"]
                telefone = row["Telefone"]

                if not cnpj.isdigit() or len(cnpj) != 14:
                    erros.append(f"Linha {i+2}: CNPJ inválido ({cnpj})")
                if len(''.join(filter(str.isdigit, telefone))) < 11:
                    erros.append(f"Linha {i+2}: Telefone inválido ({telefone})")

            duplicados = df[df.duplicated(subset=["CNPJ"], keep=False)]
            if not duplicados.empty:
                erros.append("⚠️ CNPJs duplicados encontrados:")
                for cnpj in duplicados["CNPJ"].unique():
                    erros.append(f"- {cnpj}")

            if erros:
                st.error("❌ Erros encontrados na planilha:")
                for erro in erros:
                    st.write(erro)
            else:
                st.session_state.df_validacao = df
                st.session_state.indice_lote = 0
                st.success("📋 Planilha válida e carregada com sucesso!")
        else:
            st.error("❌ Estrutura inválida. Certifique-se de que sua planilha contém as colunas: CNPJ, Nome, Telefone.")
            st.write("Colunas encontradas:", list(df.columns))

    df_validacao = st.session_state.df_validacao

    if df_validacao is not None:
        total = len(df_validacao)
        st.write(f"📦 Total de empresas: {total}")
        progresso = st.progress(st.session_state.indice_lote / total)

        if st.button("⏸️ Pausar/Retomar"):
            st.session_state.pausado = not st.session_state.pausado

        if st.session_state.pausado:
            st.warning("⏸️ Validação pausada. Clique novamente para retomar.")
            st.stop()

        if st.button("✅ Validar próximo lote"):
            contagem_regressiva(tempo_entre_lotes)
            resultados = []
            i = st.session_state.indice_lote
            lote = df_validacao.iloc[i:i+3]

            for idx, row in lote.iterrows():
                cnpj = row["CNPJ"]
                nome = row.get("Nome", "")
                telefone = row.get("Telefone", "")

                cursor.execute("SELECT situacao_rf FROM empresas WHERE cnpj = %s", (cnpj,))
                resultado_existente = cursor.fetchone()

                if resultado_existente:
                    situacao = resultado_existente[0]
                    st.write(f"🔁 {cnpj}: já registrado como '{situacao}'")
                else:
                    situacao = consultar_cnpj(cnpj)
                    time.sleep(5)

                    cursor.execute("""
                        INSERT INTO empresas (cnpj, nome, telefone, situacao_rf, created_at)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """, (cnpj, nome, telefone, situacao))
                    conn.commit()

                    st.write(f"✅ {cnpj}: {situacao}")

                resultados.append({
                    "CNPJ": cnpj,
                    "Nome": nome,
                    "Telefone": telefone,
                    "Situação RF": situacao
                })

            st.session_state.indice_lote += 3
            progresso.progress(min(st.session_state.indice_lote / total, 1.0))

        if st.session_state.indice_lote >= total:
            st.success("🎉 Validação concluída!")

with aba2:
    st.subheader("📊 Dashboard de Situação dos CNPJs")

    cursor.execute("SELECT situacao_rf FROM empresas")
    dados = cursor.fetchall()
    if dados:
        df_dashboard = pd.DataFrame(dados, columns=["Situação RF"])
        contagem = df_dashboard["Situação RF"].value_counts()

        st.bar_chart(contagem)

        fig, ax = plt.subplots()
        ax.pie(contagem, labels=contagem.index, autopct="%1.1f%%", startangle=90)
        ax.axis("equal")
        st.pyplot(fig)

        st.write("📋 Distribuição das situações:", contagem)
    else:
        st.info("Nenhum dado encontrado no banco ainda.")

with aba3:
    st.subheader("📦 Histórico de registros salvos no banco Neon")

    data_inicio = st.date_input("📅 Data inicial", value=date(2024, 1, 1))
    data_fim = st.date_input("📅 Data final", value=date.today())

    if st.button("🔎 Buscar registros por data"):
        cursor.execute("""
            SELECT cnpj, nome, telefone, situacao_rf, created_at
            FROM empresas
            WHERE DATE(created_at) BETWEEN %s AND %s
            ORDER BY id DESC
        """, (data_inicio, data_fim))
        dados = cursor.fetchall()

        if dados:
            df_banco = pd.DataFrame(dados, columns=["CNPJ", "Nome", "Telefone", "Situação RF", "Data"])

            situacoes = st.multiselect("📌 Filtrar por situação RF", options=df_banco["Situação RF"].unique())
            if situacoes:
                df_banco = df_banco[df_banco["Situação RF"].isin(situacoes)]

            st.dataframe(df_banco)

            csv = df_banco.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥
