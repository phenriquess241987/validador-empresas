if st.button("🚀 Iniciar validação e salvar no banco"):
    resultados = []
    total = len(df)
    for i in range(0, total, 3):
        lote = df.iloc[i:i+3]
        for idx, row in lote.iterrows():
            cnpj = row["CNPJ"]
            nome = row.get("Nome", "")
            telefone = row.get("Telefone", "")

            # 🧠 Verificar se já existe no banco
            cursor.execute("SELECT situacao_rf FROM empresas WHERE cnpj = %s", (cnpj,))
            resultado_existente = cursor.fetchone()

            if resultado_existente:
                situacao = resultado_existente[0]
                st.write(f"🔁 {cnpj}: já registrado como '{situacao}'")
            else:
                situacao = consultar_cnpj(cnpj)
                time.sleep(5)  # ⏳ Espera entre requisições

                # 💾 Inserir no banco Neon
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

        st.info("⏳ Aguardando 3 minutos para o próximo lote...")
        time.sleep(180)

    st.success("🎉 Validação concluída e dados salvos no banco!")
    resultado_df = pd.DataFrame(resultados)
    st.session_state["resultado_df"] = resultado_df
    st.dataframe(resultado_df)
