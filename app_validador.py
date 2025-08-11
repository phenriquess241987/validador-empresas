import streamlit as st
import pandas as pd
import requests
import time
import psycopg2

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
        situacao_rf TEXT
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

# 🖥️ Interface Streamlit
st.title("🔍 Validador de CNPJs com ReceitaWS + Banco Neon")
arquivo = st.file_uploader("📄 Envie sua planilha com CNPJs, Nomes e Telefones", type=["xlsx", "csv"])

if arquivo:
    df = pd.read_excel(arquivo) if arquivo.name.endswith(".xlsx") else pd.read_csv(arquivo)
    st.write("📋 Empresas carregadas:", df.shape[0])
    
    if st.button("🚀 Iniciar validação e salvar no banco"):
        resultados = []
        total = len(df)
        for i in range(0, total, 3):
            lote = df.iloc[i:i+3]
            for idx, row in lote.iterrows():
                cnpj = row["CNPJ"]
                nome = row.get("Nome", "")
                telefone = row.get("Telefone", "")
                situacao = consultar_cnpj(cnpj)

                resultados.append({
                    "CNPJ": cnpj,
                    "Nome": nome,
                    "Telefone": telefone,
                    "Situação RF": situacao
                })

                # 💾 Inserir no banco Neon
                cursor.execute("""
                    INSERT INTO empresas (cnpj, nome, telefone, situacao_rf)
                    VALUES (%s, %s, %s, %s)
                """, (cnpj, nome, telefone, situacao))
                conn.commit()

                st.write(f"✅ {cnpj}: {situacao}")
            
            st.info("⏳ Aguardando 3 minutos para o próximo lote...")
            time.sleep(180)

        st.success("🎉 Validação concluída e dados salvos no banco!")
        resultado_df = pd.DataFrame(resultados)
        st.dataframe(resultado_df)

# 📦 Consulta dos dados salvos
st.markdown("---")
st.subheader("📦 Consultar dados salvos no banco Neon")

if st.button("🔎 Ver registros salvos"):
    cursor.execute("SELECT cnpj, nome, telefone, situacao_rf FROM empresas ORDER BY id DESC")
    dados = cursor.fetchall()

    if dados:
        df_banco = pd.DataFrame(dados, columns=["CNPJ", "Nome", "Telefone", "Situação RF"])
        st.dataframe(df_banco)

        # 📥 Botão para baixar como CSV
        csv = df_banco.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar registros como CSV",
            data=csv,
            file_name="empresas_salvas.csv",
            mime="text/csv"
        )
    else:
        st.info("Nenhum dado encontrado no banco ainda.")
