import streamlit as st
import pandas as pd
import requests
import time
import psycopg2
import io
from datetime import date
import matplotlib.pyplot as plt

# --- Conexão com banco ---
conn = psycopg2.connect(st.secrets["database"]["url"])
cursor = conn.cursor()

# --- Inicializa tabela e colunas CRM ---
def inicializar_banco():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS empresas (
        id SERIAL PRIMARY KEY,
        cnpj TEXT UNIQUE,
        nome TEXT,
        telefone TEXT,
        situacao_rf TEXT,
        crm_status TEXT DEFAULT 'Prospect',
        crm_notas TEXT,
        proximo_contato DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()

    for coluna, tipo, default in [
        ("crm_status", "TEXT", "'Prospect'"),
        ("crm_notas", "TEXT", "NULL"),
        ("proximo_contato", "DATE", "NULL"),
    ]:
        cursor.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns WHERE table_name='empresas' AND column_name='{coluna}'
            ) THEN
                ALTER TABLE empresas ADD COLUMN {coluna} {tipo} DEFAULT {default};
            END IF;
        END$$;
        """)
    conn.commit()

inicializar_banco()

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

def contagem_regressiva(segundos):
    for i in range(segundos, 0, -1):
        st.write(f"⏳ Próximo lote em {i} segundos...")
        time.sleep(1)

st.set_page_config(page_title="Validador + CRM Simplificado", layout="wide")
st.title("🔍 Validador de CNPJs + CRM Simplificado")

aba1, aba2, aba3 = st.tabs(["📤 Validação", "📊 Dashboard", "📦 Histórico / CRM"])

# --- Aba 1: Validação ---
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
                            ON CONFLICT (cnpj) DO NOTHING
                        """, (cnpj, nome, telefone, situacao))
                        conn.commit()
                        st.write(f"✅ {cnpj}: {situacao}")

                st.session_state.indice_lote += 3
                progresso.progress(min(st.session_state.indice_lote / total, 1.0))

        if st.session_state.indice_lote >= total:
            st.success("🎉 Validação concluída!")

# --- Aba 2: Dashboard ---
with aba2:
    st.subheader("📊 Dashboard de Situação dos CNPJs")

    # Dados situação RF
    cursor.execute("SELECT situacao_rf FROM empresas")
    dados_rf = cursor.fetchall()
    df_rf = pd.DataFrame(dados_rf, columns=["Situação RF"]) if dados_rf else pd.DataFrame(columns=["Situação RF"])
    contagem_rf = df_rf["Situação RF"].value_counts()

    # Dados CRM
    cursor.execute("SELECT crm_status FROM empresas")
    dados_crm = cursor.fetchall()
    df_crm = pd.DataFrame(dados_crm, columns=["CRM Status"]) if dados_crm else pd.DataFrame(columns=["CRM Status"])
    contagem_crm = df_crm["CRM Status"].value_counts()

    # Quatro colunas iguais lado a lado
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.write("📊 Situação RF (Barras)")
        st.bar_chart(contagem_rf)

    with col2:
        st.write("📋 Distribuição das situações RF")
        st.dataframe(contagem_rf.to_frame().rename(columns={"Situação RF": "Quantidade"}))

    with col3:
        st.write("📊 Distribuição CRM Status")
        fig_crm, ax_crm = plt.subplots(figsize=(3, 3))
        ax_crm.pie(contagem_crm, labels=contagem_crm.index, autopct="%1.1f%%", startangle=90)
        ax_crm.axis("equal")
        st.pyplot(fig_crm, use_container_width=True)

    with col4:
        st.write("🍰 Situação RF (Pizza)")
        fig_rf, ax_rf = plt.subplots(figsize=(3, 3))
        ax_rf.pie(contagem_rf, labels=contagem_rf.index, autopct="%1.1f%%", startangle=90)
        ax_rf.axis("equal")
        st.pyplot(fig_rf, use_container_width=True)

# --- Aba 3: Histórico / CRM Simplificado ---
with aba3:
    st.subheader("📦 Histórico / CRM Simplificado")

    status_list = ["Prospect", "Em Negociação", "Cliente", "Perdido"]

    cursor.execute("""
        SELECT id, cnpj, nome, telefone, situacao_rf, crm_status, crm_notas, proximo_contato 
        FROM empresas
        ORDER BY id
    """)
    empresas = cursor.fetchall()

    empresas_por_status = {status: [] for status in status_list}
    for e in empresas:
        id_, cnpj, nome, telefone, situacao_rf, crm_status, crm_notas, proximo_contato = e
        if crm_status not in status_list:
            crm_status = "Prospect"
        empresas_por_status[crm_status].append({
            "id": id_,
            "cnpj": cnpj,
            "nome": nome,
            "telefone": telefone,
            "situacao_rf": situacao_rf,
            "crm_notas": crm_notas or "",
            "proximo_contato": proximo_contato.strftime("%Y-%m-%d") if proximo_contato else "",
        })

    col1, col2, col3, col4 = st.columns(4)
    colunas = [col1, col2, col3, col4]

    def atualizar_status(id_, novo_status):
        cursor.execute("UPDATE empresas SET crm_status=%s WHERE id=%s", (novo_status, id_))
        conn.commit()

    def salvar_notas(id_, notas, data_contato):
        cursor.execute("""
            UPDATE empresas SET crm_notas=%s, proximo_contato=%s WHERE id=%s
        """, (notas, data_contato if data_contato else None, id_))
        conn.commit()

    for i, status in enumerate(status_list):
        with colunas[i]:
            st.markdown(f"### {status} ({len(empresas_por_status[status])})")
            for empresa in empresas_por_status[status]:
                st.markdown(f"**{empresa['nome']}** ({empresa['cnpj']})")
                st.write(f"Telefone: {empresa['telefone']}")
                st.write(f"Situação RF: {empresa['situacao_rf']}")
                col_move = st.columns([1, 2, 1])
                with col_move[0]:
                    if st.button("⬅️", key=f"voltar_{empresa['id']}") and status != status_list[0]:
                        idx = status_list.index(status)
                        atualizar_status(empresa["id"], status_list[idx - 1])
                        st.session_state["needs_rerun"] = True
                with col_move[2]:
                    if st.button("➡️", key=f"avancar_{empresa['id']}") and status != status_list[-1]:
                        idx = status_list.index(status)
                        atualizar_status(empresa["id"], status_list[idx + 1])
                        st.session_state["needs_rerun"] = True
                notas = st.text_area("Notas", value=empresa['crm_notas'], key=f"notas_{empresa['id']}")
                data_contato = st.date_input(
                    "Próximo contato",
                    value=pd.to_datetime(empresa['proximo_contato']).date() if empresa['proximo_contato'] else date.today(),
                    key=f"data_{empresa['id']}"
                )
                if st.button("Salvar", key=f"salvar_{empresa['id']}"):
                    salvar_notas(empresa["id"], notas, data_contato)
                    st.success("Atualizado!")
                    st.session_state["needs_rerun"] = True
                st.markdown("---")

# --- Controle seguro do rerun ---
if st.session_state.get("needs_rerun", False):
    st.session_state["needs_rerun"] = False
    st.experimental_rerun()
