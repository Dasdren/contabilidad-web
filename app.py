if st.sidebar.button("Procesar e Importar"):
        try:
            # INTENTO 1: Leer como UTF-8 (Estándar moderno)
            df_upload = pd.read_csv(uploaded_file)
        except UnicodeDecodeError:
            # INTENTO 2: Si falla, rebobinamos y probamos con formato Windows/Excel (Latin-1)
            uploaded_file.seek(0)
            df_upload = pd.read_csv(uploaded_file, encoding='ISO-8859-1')
        except Exception as e:
            st.sidebar.error(f"Error desconocido: {e}")
            st.stop()

        try:
            # Verificamos que tenga las columnas correctas
            columnas_necesarias = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
            
            # Normalizamos nombres de columnas (quitamos espacios extra por si acaso)
            df_upload.columns = df_upload.columns.str.strip()

            if not all(col in df_upload.columns for col in columnas_necesarias):
                st.sidebar.error(f"El CSV debe tener estas columnas: {columnas_necesarias}")
            else:
                # Resto del código de procesamiento...
                df_upload["Fecha"] = pd.to_datetime(df_upload["Fecha"], dayfirst=True).dt.strftime("%Y-%m-%d")
                
                # Preparamos los datos
                datos_para_subir = df_upload[columnas_necesarias].values.tolist()
                
                sheet.append_rows(datos_para_subir)
                
                st.sidebar.success(f"✅ ¡{len(datos_para_subir)} movimientos importados!")
                st.rerun()
                
        except Exception as e:
            st.sidebar.error(f"Error procesando los datos: {e}")
