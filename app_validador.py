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

# 🧱 Criar/alterar tabela para CRM
cursor.execute("""
    CREATE TABLE IF NOT EXISTS empresas (
        id SERIAL PRIMARY KEY,
        cnpj TEXT,
        nome TEXT,
        telefone TEXT,
        situacao_rf TEXT,
        crm_status TEXT DEFAULT 'Novo',
        crm_notas TEXT,
        proximo_contato DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
""")
conn.commit()

# 🔍 Função para consultar CNPJ na ReceitaWS
@st.cache_data(show_spinner=False)
def consultar_cnpj(cnpj):
    cnpj = ''.join(filter(str.isdigit, str(cnpj)))
    url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj}"
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
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
st.set_page_config(page_title="Validador + CRM", layout="wide")
st.title("🔍 Validador de CNPJs + CRM Básico")
aba1, aba2, aba3 = st.tabs(["📤 Validação", "📊 Dashboard", "📦 Histórico / CRM"])

# 📤 Aba 1: Validação
with aba1:
    st.subheader("📤 Validação de CNPJs")

    modelo_df = pd.DataFrame({"CNPJ": ["00000000000000"], "Nome": ["Empresa Exemplo"], "Telefone": ["(00) 00000-0000"]})
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        modelo_df.to_excel(writer, index=False, sheet_name="Modelo")
    st.download_button("📥 Baixar planilha modelo", excel_buffer.getvalue(), "modelo_planilha.xlsx")

    arquivo = st.file_uploader("📄 Envie sua planilha", type=["xlsx", "csv"])
    colunas_esperadas = ["CNPJ", "Nome", "Telefone"]

    if "df_validacao" not in st.session_state:
        st.session_state.df_validacao = None
    if "indice_lote" not in st.session_state:
        st.session_state.indice_lote = 0
    if "pausado" not in st.session_state:
        st.session_state.pausado = False

    tempo_entre_lotes = st.slider("⏱️ Tempo entre lotes (segundos)", 1, 30, 5)

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
                st.success("📋 Planilha carregada com sucesso!")
        else:
            st.error("❌ Estrutura inválida. Colunas necessárias: CNPJ, Nome, Telefone.")

    df_validacao = st.session_state.df_validacao
    if df_validacao is not None:
        total = len(df_validacao)
        st.write(f"📦 Total de empresas: {total}")
        progresso = st.progress(st.session_state.indice_lote / total)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("⏸️ Pausar/Retomar"):
                st.session_state.pausado = not st.session_state.pausado
        with col2:
            if st.button("✅ Validar próximo lote") and not st.session_state.pausado:
                contagem_regressiva(tempo_entre_lotes)
                lote = df_validacao.iloc[st.session_state.indice_lote:st.session_state.indice_lote+3]
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
                            INSERT INTO empresas (cnpj, nome, telefone, situacao_rf)
                            VALUES (%s, %s, %s, %s)
                        """, (cnpj, nome, telefone, situacao))
                        conn.commit()
                        st.write(f"✅ {cnpj}: {situacao}")

                st.session_state.indice_lote += 3
                progresso.progress(min(st.session_state.indice_lote / total, 1.0))

        if st.session_state.indice_lote >= total:
            st.success("🎉 Validação concluída!")

# 📊 Aba 2: Dashboard
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
        st.info("Nenhum dado encontrado.")

# 📦 Aba 3: Histórico / CRM
with aba3:
    st.subheader("📦 Histórico e CRM Básico")

    # Indicadores rápidos
    st.markdown("### 📌 Indicadores rápidos")
    cursor.execute("SELECT crm_status, COUNT(*) FROM empresas GROUP BY crm_status;")
    status_counts = dict(cursor.fetchall())
    st.write(status_counts)

    # Contatos para hoje
    st.markdown("### 📅 Contatos para hoje")
    cursor.execute("SELECT cnpj, nome, telefone, crm_status, proximo_contato FROM empresas WHERE proximo_contato = CURRENT_DATE")
    contatos_hoje = cursor.fetchall()
    if contatos_hoje:
        df_hoje = pd.DataFrame(contatos_hoje, columns=["CNPJ", "Nome", "Telefone", "Status CRM", "Próximo Contato"])
        st.dataframe(df_hoje)
    else:
        st.info("Nenhum contato agendado para hoje.")

    # Filtro e busca
    data_inicio = st.date_input("📅 Data inicial", value=date(2024, 1, 1))
    data_fim = st.date_input("📅 Data final", value=date.today())
    status_filtro = st.multiselect("📌 Filtrar por status CRM", options=["Novo", "Em Negociação", "Cliente Ativo", "Cliente Perdido"])

    if st.button("🔎 Buscar registros"):
        query = """
            SELECT cnpj, nome, telefone, situacao_rf, crm_status, crm_notas, proximo_contato, created_at
            FROM empresas
            WHERE DATE(created_at) BETWEEN %s AND %s
        """
        params = [data_inicio, data_fim]
        if status_filtro:
            query += " AND crm_status = ANY(%s)"
            params.append(status_filtro)

        cursor.execute(query, tuple(params))
        dados = cursor.fetchall()
        if dados:
            df_banco = pd.DataFrame(dados, columns=["CNPJ", "Nome", "Telefone", "Situação RF", "Status CRM", "Notas", "Próximo Contato", "Data Cadastro"])
            st.dataframe(df_banco)

            # Download CSV
            csv = df_banco.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Baixar CSV", csv, "historico_cnpjs.csv", "text/csv")

            # Download Excel
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                df_banco.to_excel(writer, index=False, sheet_name="Histórico CRM")
            st.download_button("📥 Baixar Excel", excel_buffer.getvalue(), "historico_cnpjs.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("Nenhum registro encontrado.")

    # Edição de cliente
    st.markdown("### ✏️ Editar informações do cliente")
    cnpj_edit = st.text_input("Digite o CNPJ para editar:")
    if cnpj_edit:
        cursor.execute("SELECT nome, telefone, crm_status, crm_notas, proximo_contato FROM empresas WHERE cnpj = %s", (cnpj_edit,))
        cliente = cursor.fetchone()
        if cliente:
            nome, telefone, status, notas, proximo = cliente
            novo_status = st.selectbox("Status CRM", ["Novo", "Em Negociação", "Cliente Ativo", "Cliente Perdido"], index=["Novo", "Em Negociação", "Cliente Ativo", "Cliente Perdido"].index(status or "Novo"))
            novas_notas = st.text_area("Notas internas", value=notas or "")
            nova_data = st.date_input("Próxima data de contato", value=proximo or date.today())
            if st.button("💾 Salvar alterações"):
                cursor.execute("""
                    UPDATE empresas
                    SET crm_status=%s, crm_notas=%s, proximo_contato=%s
                    WHERE cnpj=%s
                """, (novo_status, novas_notas, nova_data, cnpj_edit))
                conn.commit()
                st.success("Informações do cliente atualizadas!")
        else:
            st.error("CNPJ não encontrado.")
