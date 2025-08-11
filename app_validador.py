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

# 🖥️ Interface com abas
st.title("🔍 Validador de CNPJs com ReceitaWS + Banco Neon")
aba1, aba2, aba3 = st.tabs(["📤 Validação", "📊 Dashboard", "📦 Histórico"])

with aba1:
    st.subheader("📤 Validação de CNPJs")

    # 📍 Instrução clara
    st.markdown("### 📎 Baixe a planilha modelo para garantir o formato correto")
    st.markdown("A planilha deve conter as colunas: **CNPJ**, **Nome**, **Telefone**")

    # 📄 Gerar planilha modelo
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

    # 📤 Upload da planilha
    arquivo = st.file_uploader("📄 Envie sua planilha preenchida", type=["xlsx", "csv"])
    colunas_esperadas = ["CNPJ", "Nome", "Telefone"]

    if "df_validacao" not in st.session_state:
        st.session_state.df_validacao = None
    if "indice_lote" not in st.session_state:
        st.session_state.indice_lote = 0

    if arquivo and st.session_state.df_validacao is None:
        df = pd.read_excel(arquivo) if arquivo.name.endswith(".xlsx") else pd.read_csv(arquivo)

        # ✅ Validação da estrutura
        if all(col in df.columns for col in colunas_esperadas):
            erros = []

            # 🔍 Validação de formato
            df["CNPJ"] = df["CNPJ"].astype(str).str.replace(r"\D", "", regex=True)
            df["Telefone"] = df["Telefone"].astype(str)

            for i, row in df.iterrows():
                cnpj = row["CNPJ"]
                telefone = row["Telefone"]

                if not cnpj.isdigit() or len(cnpj) != 14:
                    erros.append(f"Linha {i+2}: CNPJ inválido ({cnpj})")
                if len(''.join(filter(str.isdigit, telefone))) < 11:
                    erros.append(f"Linha {i+2}: Telefone inválido ({telefone})")

            # 🚫 Verificar duplicidade de CNPJs
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

        tempo_entre_lotes = st.number_input("⏱️ Tempo entre lotes (segundos)", min_value=60, max_value=600, value=180, step=30)

        if "validacao_automatica" not in st.session_state:
            st.session_state.validacao_automatica = False
        if "pausar_validacao" not in st.session_state:
            st.session_state.pausar_validacao = False

        col1, col2 = st.columns(2)
        with col1:
            if not st.session_state.validacao_automatica:
                if st.button("🚀 Iniciar validação automática"):
                    st.session_state.validacao_automatica = True
                    st.rerun()
        with col2:
            if st.session_state.validacao_automatica:
                if st.button("⏸️ Pausar validação"):
                    st.session_state.validacao_automatica = False
                    st.session_state.pausar_validacao = True
                    st.success("⏸️ Validação pausada.")

        if st.session_state.validacao_automatica and st.session_state.indice_lote < total:
            i = st.session_state.indice_lote
            lote = df_validacao.iloc[i:i+3]
            st.info(f"🔄 Validando lote {i+1} a {min(i+3, total)} de {total}")

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
                    with st.spinner(f"⏳ Consultando ReceitaWS para CNPJ {cnpj}..."):
                        situacao = consultar_cnpj(cnpj)
                        time.sleep(5)

                    cursor.execute("""
                        INSERT INTO empresas (cnpj, nome, telefone, situacao_rf, created_at)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """, (cnpj, nome, telefone, situacao))
                    conn.commit()

                    st.write(f"✅ {cnpj}: {situacao}")

            st.session_state.indice_lote += 3
            progresso.progress(min(st.session_state.indice_lote / total, 1.0))

            if st.session_state.indice_lote < total:
                st.info(f"⏳ Aguardando {tempo_entre_lotes} segundos para o próximo lote...")
                contador = st.empty()
                for t in range(tempo_entre_lotes, 0, -1):
                    contador.markdown(f"⌛ Próximo lote em **{t}** segundos...")
                    time.sleep(1)
                st.rerun()
            else:
                st.success("🎉 Validação automática concluída!")
                st.session_state.validacao_automatica = False

with aba2:
    st.subheader("📊 Dashboard de Situação dos CNPJs")

    cursor.execute("SELECT situacao_rf FROM empresas")
    dados = cursor.fetchall()
    if dados:
        df_dashboard = pd.DataFrame(dados, columns=["Situação RF"])
        contagem = df_dashboard["Situação RF"].value_counts()

        st.bar_chart(contagem)

        fig, ax = plt.subplots()
        ax.pie(contagem
