import streamlit as st
import pandas as pd
import requests
import time

# Função para consultar CNPJ na ReceitaWS
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

# Interface Streamlit
st.title("🔍 Validador de CNPJs com ReceitaWS")
arquivo = st.file_uploader("📄 Envie sua planilha com CNPJs", type=["xlsx", "csv"])

if arquivo:
    df = pd.read_excel(arquivo) if arquivo.name.endswith(".xlsx") else pd.read_csv(arquivo)
    st.write("📋 Empresas carregadas:", df.shape[0])
    
    if st.button("🚀 Iniciar validação em tempo real"):
        resultados = []
        total = len(df)
        for i in range(0, total, 3):
            lote = df.iloc[i:i+3]
            for idx, row in lote.iterrows():
                cnpj = row["CNPJ"]
                situacao = consultar_cnpj(cnpj)
                resultados.append({"CNPJ": cnpj, "Situação": situacao})
                st.write(f"✅ {cnpj}: {situacao}")
            
            st.info(f"⏳ Aguardando 3 minutos para o próximo lote...")
            time.sleep(180)  # Espera 3 minutos

        st.success("🎉 Validação concluída!")
        resultado_df = pd.DataFrame(resultados)
        st.dataframe(resultado_df)

#conectar ao banco de dados do neon.tech

import streamlit as st
import psycopg2

# Conectar ao banco usando secrets
conn = psycopg2.connect(st.secrets["database"]["url"])
cursor = conn.cursor()

# Teste simples
cursor.execute("SELECT version();")
versao = cursor.fetchone()
st.write("Conectado ao banco Neon!")
st.write("Versão do PostgreSQL:", versao)

