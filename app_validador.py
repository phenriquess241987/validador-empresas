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
    # Ad
