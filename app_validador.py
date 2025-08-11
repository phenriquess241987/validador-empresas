with aba1:
    st.subheader("📤 Validação de CNPJs")

    # 🔹 Instruções e planilha modelo
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

    # 🔹 Upload da planilha do usuário
    arquivo = st.file_uploader("📄 Envie sua planilha com CNPJs, Nomes e Telefones", type=["xlsx", "csv"])

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

            # 🔍 Verificação de formato e duplicidade
            df["CNPJ"] = df["CNPJ"].astype(str).str.replace(r"\D", "", regex=True)
            df["Telefone"] = df["Telefone"].astype(str)

            for i, row in df.iterrows():
                cnpj = row["CNPJ"]
                telefone = row["Telefone"]

                if not cnpj.isdigit() or len(cnpj) != 14:
                    erros.append(f"Linha {i+2}: CNPJ inválido ({cnpj})")
                if len(''.join(filter(str.isdigit, telefone))) < 10:
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

        if st.button("✅ Validar próximo lote"):
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
