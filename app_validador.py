import streamlit as st
import pandas as pd
import requests
import time
import psycopg2
import io
from datetime import date
from streamlit_sortables import sortables

# --- Conexão com banco ---
conn = psycopg2.connect(st.secrets["database"]["url"])
cursor = conn.cursor()

# --- Criação e alteração da tabela com colunas CRM ---
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
    # Adicionar colunas que possam faltar (exemplo: caso tenha tabela mas falte colunas)
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

# --- Função para consultar CNPJ ReceitaWS ---
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

# --- Função contagem regressiva ---
def contagem_regressiva(segundos):
    for i in range(segundos, 0, -1):
        st.write(f"⏳ Próximo lote em {i} segundos...")
        time.sleep(1)

# --- Configuração da página ---
st.set_page_config(page_title="Validador + CRM Kanban", layout="wide")
st.title("🔍 Validador de CNPJs + CRM Kanban")

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
    cursor.execute("SELECT situacao_rf FROM empresas")
    dados = cursor.fetchall()
    if dados:
        df_dashboard = pd.DataFrame(dados, columns=["Situação RF"])
        contagem = df_dashboard["Situação RF"].value_counts()
        st.bar_chart(contagem)

        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        ax.pie(contagem, labels=contagem.index, autopct="%1.1f%%", startangle=90)
        ax.axis("equal")
        st.pyplot(fig)
        st.write("📋 Distribuição das situações:", contagem)
    else:
        st.info("Nenhum dado encontrado.")

# --- Aba 3: Histórico / CRM Kanban ---
with aba3:
    st.subheader("📦 Histórico / CRM Kanban")

    # Status fixos (Kanban)
    status_list = ["Prospect", "Em Negociação", "Cliente", "Perdido"]

    # Pegar todas as empresas do banco
    cursor.execute("""
        SELECT id, cnpj, nome, telefone, situacao_rf, crm_status, crm_notas, proximo_contato 
        FROM empresas
        ORDER BY id
    """)
    empresas = cursor.fetchall()

    # Organizar por status
    empresas_por_status = {status: [] for status in status_list}
    id_to_empresa = {}
    for e in empresas:
        id_, cnpj, nome, telefone, situacao_rf, crm_status, crm_notas, proximo_contato = e
        if crm_status not in status_list:
            crm_status = "Prospect"
        card = {
            "id": id_,
            "cnpj": cnpj,
            "nome": nome,
            "telefone": telefone,
            "situacao_rf": situacao_rf,
            "crm_notas": crm_notas or "",
            "proximo_contato": proximo_contato.strftime("%Y-%m-%d") if proximo_contato else "",
        }
        empresas_por_status[crm_status].append(card)
        id_to_empresa[id_] = card

    # Função para salvar atualizações
    def salvar_empresa(id_, notas, proximo_contato):
        cursor.execute("""
            UPDATE empresas SET crm_notas=%s, proximo_contato=%s WHERE id=%s
        """, (notas, proximo_contato if proximo_contato != "" else None, id_))
        conn.commit()

    def alterar_status(id_, novo_status):
        cursor.execute("""
            UPDATE empresas SET crm_status=%s WHERE id=%s
        """, (novo_status, id_))
        conn.commit()

    # Mostrar cards no kanban com streamlit-sortables
    colunas_kanban = []
    for status in status_list:
        colunas_kanban.append({
            "id": status,
            "title": status,
            "cards": empresas_por_status[status]
        })

    # Componente kanban (drag & drop)
    kanban = sortables(
        colunas_kanban,
        direction="horizontal",
        key="kanban_empresas",
        item_renderer=lambda card: f"{card['nome']} ({card['cnpj']})\nTelefone: {card['telefone']}\nSituação RF: {card['situacao_rf']}"
    )

    # Detectar mudanças no kanban e salvar status no banco
    if kanban:
        # kanban = lista de colunas com cards atualizados após drag & drop
        # para cada coluna, atualizar status
        for coluna in kanban:
            status_coluna = coluna["id"]
            for card in coluna["cards"]:
                id_ = card["id"]
                if id_to_empresa[id_]["crm_status"] != status_coluna:
                    alterar_status(id_, status_coluna)
                    id_to_empresa[id_]["crm_status"] = status_coluna

    st.markdown("---")

    # Selecionar cliente para editar notas e próxima data contato
    st.markdown("### ✏️ Editar notas e próxima data de contato")
    cnpj_para_editar = st.selectbox("Selecione o CNPJ do cliente", options=[f"{c['cnpj']} - {c['nome']}" for c in empresas])
    if cnpj_para_editar:
        cnpj_selecionado = cnpj_para_editar.split(" - ")[0]
        cursor.execute("""
            SELECT id, crm_notas, proximo_contato FROM empresas WHERE cnpj = %s
        """, (cnpj_selecionado,))
        res = cursor.fetchone()
        if res:
            id_edit, notas_edit, proximo_edit = res
            notas_edit = notas_edit or ""
            proximo_edit = proximo_edit or date.today()
            novas_notas = st.text_area("Notas", value=notas_edit, key="notas_edit")
            nova_data = st.date_input("Próxima data de contato", value=proximo_edit, key="data_edit")
            if st.button("💾 Salvar alterações", key="salvar_edit"):
                salvar_empresa(id_edit, novas_notas, nova_data)
                st.success("Informações atualizadas!")

