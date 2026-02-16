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

if uploaded_file is not None:
    if st.sidebar.button("Procesar e Importar"):
        try:
            # Leemos el CSV
            df_upload = pd.read_csv(uploaded_file)
            
            # Verificamos que tenga las columnas correctas
            columnas_necesarias = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
            
            # Si faltan columnas, avisamos
            if not all(col in df_upload.columns for col in columnas_necesarias):
                st.sidebar.error(f"El CSV debe tener estas columnas exactas: {columnas_necesarias}")
            else:
                # Convertimos todo a texto/números compatibles para Google Sheets
                # Aseguramos formato de fecha YYYY-MM-DD
                df_upload["Fecha"] = pd.to_datetime(df_upload["Fecha"]).dt.strftime("%Y-%m-%d")
                
                # Preparamos los datos como una lista de listas
                datos_para_subir = df_upload[columnas_necesarias].values.tolist()
                
                # Subimos todo de golpe (más rápido)
                sheet.append_rows(datos_para_subir)
                
                st.sidebar.success(f"✅ ¡{len(datos_para_subir)} movimientos importados!")
                st.rerun()
                
        except Exception as e:
            st.sidebar.error(f"Error al leer el CSV: {e}")

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
