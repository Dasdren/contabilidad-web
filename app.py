import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Mi Contabilidad Nube", layout="wide", page_icon="☁️")

# --- CONEXIÓN CON GOOGLE SHEETS ---
def conectar_google_sheets():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("Contabilidad_App").sheet1
    return sheet

try:
    sheet = conectar_google_sheets()
except Exception as e:
    st.error("⚠️ Error de conexión. Revisa tus Secrets.")
    st.stop()

# --- FUNCIONES ---
def load_data():
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    expected_cols = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = ""
    return df

def save_entry(fecha, tipo, categoria, descripcion, monto, es_fijo):
    fecha_str = fecha.strftime("%Y-%m-%d")
    es_fijo_str = "SÍ" if es_fijo else "NO"
    row = [fecha_str, tipo, categoria, descripcion, monto, es_fijo_str]
    sheet.append_row(row)

# --- BARRA LATERAL: INGRESO MANUAL ---
st.sidebar.header("📝 Nuevo Movimiento")

with st.sidebar.form("entry_form", clear_on_submit=True):
    fecha = st.date_input("Fecha", datetime.today())
    tipo = st.selectbox("Tipo", ["Gasto", "Ingreso"])
    categoria = st.text_input("Categoría (ej: Supermercado)")
    descripcion = st.text_input("Descripción")
    monto = st.number_input("Monto (€)", min_value=0.0, format="%.2f")
    es_fijo = st.checkbox("¿Es FIJO mensual?")
    
    submitted = st.form_submit_button("Guardar Manual")

    if submitted:
        if monto > 0:
            monto_final = -monto if tipo == "Gasto" else monto
            save_entry(fecha, tipo, categoria, descripcion, monto_final, es_fijo)
            st.success("✅ Guardado")
            st.rerun()

# --- BARRA LATERAL: IMPORTAR CSV ---
st.sidebar.markdown("---")
st.sidebar.header("📥 Importar CSV")
uploaded_file = st.sidebar.file_uploader("Sube tu archivo aquí", type=["csv"])

import numpy as np # Asegúrate de que esta línea esté al principio del archivo con los otros imports, si no, agrégala aquí abajo dentro de la función o arriba del todo.

# ... (El resto de tu código arriba) ...

# --- BARRA LATERAL: IMPORTAR CSV ---
st.sidebar.markdown("---")
st.sidebar.header("📥 Importar CSV")
uploaded_file = st.sidebar.file_uploader("Sube tu archivo aquí", type=["csv"])

if uploaded_file is not None:
    if st.sidebar.button("Procesar e Importar"):
        try:
            # INTENTO 1: Leer con 'utf-8-sig'
            uploaded_file.seek(0)
            df_upload = pd.read_csv(uploaded_file, encoding='utf-8-sig')
            
            # Si falla el separador (solo detecta 1 columna), probamos con punto y coma
            if len(df_upload.columns) <= 1:
                uploaded_file.seek(0)
                df_upload = pd.read_csv(uploaded_file, sep=';', encoding='latin-1')
            
            # Limpieza de nombres de columnas
            df_upload.columns = df_upload.columns.str.strip().str.replace('ï»¿', '')
            
            columnas_necesarias = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
            
            if not all(col in df_upload.columns for col in columnas_necesarias):
                st.sidebar.error(f"Error de columnas. Se detectaron: {list(df_upload.columns)}")
            else:
                # --- LIMPIEZA MAESTRA DE DATOS ---
                
                # 1. Limpiar la columna MONTO
                df_upload["Monto"] = df_upload["Monto"].astype(str)
                # Quitamos el '?' y el '€' explícitamente primero
                df_upload["Monto"] = df_upload["Monto"].str.replace('?', '', regex=False)
                df_upload["Monto"] = df_upload["Monto"].str.replace('€', '', regex=False)
                
                # Quitamos los PUNTOS de los miles (ej: 1.800,00 -> 1800,00) para no confundir a Python
                df_upload["Monto"] = df_upload["Monto"].str.replace('.', '', regex=False)
                
                # Cambiamos la COMA decimal por PUNTO (ej: 30,79 -> 30.79)
                df_upload["Monto"] = df_upload["Monto"].str.replace(',', '.', regex=False)
                
                # Convertimos a número
                df_upload["Monto"] = pd.to_numeric(df_upload["Monto"], errors='coerce')

                # 2. INTELIGENCIA DE SIGNOS (Aquí arreglamos el problema del guion faltante)
                # Si la columna Tipo contiene "Gasto", multiplicamos por -1 el valor absoluto
                # Si es "Ingreso", dejamos el valor absoluto positivo
                import numpy as np # Importamos aquí por si acaso
                df_upload["Monto"] = np.where(
                    df_upload["Tipo"].str.lower().str.contains("gasto"), 
                    -1 * df_upload["Monto"].abs(),  # Si es gasto, ponlo negativo
                    df_upload["Monto"].abs()        # Si es ingreso, ponlo positivo
                )

                # 3. Formatear la FECHA
                df_upload["Fecha"] = pd.to_datetime(df_upload["Fecha"], dayfirst=True, errors='coerce').dt.strftime("%Y-%m-%d")
                
                # Eliminamos errores
                df_upload = df_upload.dropna(subset=['Fecha', 'Monto'])

                # Subir
                datos_para_subir = df_upload[columnas_necesarias].values.tolist()
                
                if len(datos_para_subir) > 0:
                    sheet.append_rows(datos_para_subir)
                    st.sidebar.success(f"✅ ¡{len(datos_para_subir)} movimientos importados y corregidos!")
                    st.rerun()
                else:
                    st.sidebar.warning("Archivo vacío o datos inválidos.")
                
        except Exception as e:
            st.sidebar.error(f"Error técnico: {e}")

# --- CUERPO PRINCIPAL ---
df = load_data()

st.title("☁️ Contabilidad en la Nube")

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📅 Planificación Fija", "📂 Datos"])

with tab1:
    if not df.empty and "Monto" in df.columns:
        df["Monto"] = pd.to_numeric(df["Monto"], errors='coerce').fillna(0)
        total_balance = df["Monto"].sum()
        col1, col2, col3 = st.columns(3)
        col1.metric("Balance", f"{total_balance:.2f} €")
        col2.metric("Ingresos", f"{df[df['Monto'] > 0]['Monto'].sum():.2f} €")
        col3.metric("Gastos", f"{df[df['Monto'] < 0]['Monto'].sum():.2f} €")
        
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors='coerce')
        if not df["Fecha"].isnull().all():
            st.plotly_chart(px.line(df.sort_values("Fecha"), x="Fecha", y="Monto", color="Tipo"), use_container_width=True)

with tab2:
    if not df.empty and "Es_Fijo" in df.columns:
        fijos = df[(df["Es_Fijo"] == "SÍ") & (df["Monto"] < 0)]
        st.metric("Gasto Fijo Total", f"{fijos['Monto'].sum():.2f} €")
        st.dataframe(fijos, use_container_width=True)

with tab3:
    st.dataframe(df, use_container_width=True)
    # Botón para descargar plantilla CSV para importar
    plantilla = pd.DataFrame(columns=["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"])
    csv_plantilla = plantilla.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Descargar Plantilla CSV vacía", csv_plantilla, "plantilla_importacion.csv", "text/csv")



