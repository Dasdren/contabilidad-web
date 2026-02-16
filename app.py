import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np

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
    st.error("⚠️ Error de conexión. Revisa tus Secrets en la configuración de Streamlit.")
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

# --- BARRA LATERAL: IMPORTAR CSV (CORREGIDO PARA ESPAÑA) ---
st.sidebar.markdown("---")
st.sidebar.header("📥 Importar CSV")
uploaded_file = st.sidebar.file_uploader("Sube tu archivo aquí", type=["csv"])

if uploaded_file is not None:
    if st.sidebar.button("Procesar e Importar"):
        try:
            # 1. INTENTO DE LECTURA (UTF-8 con BOM o Latin-1)
            uploaded_file.seek(0)
            try:
                # Engine python es más lento pero más flexible con separadores
                df_upload = pd.read_csv(uploaded_file, encoding='utf-8-sig', sep=None, engine='python')
            except:
                uploaded_file.seek(0)
                df_upload = pd.read_csv(uploaded_file, encoding='latin-1', sep=';')
            
            # 2. LIMPIEZA DE NOMBRES DE COLUMNAS
            df_upload.columns = df_upload.columns.str.strip().str.replace('ï»¿', '')
            
            columnas_necesarias = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
            
            # Verificamos si están las columnas
            if not all(col in df_upload.columns for col in columnas_necesarias):
                st.sidebar.error(f"Error de formato. Columnas encontradas: {list(df_upload.columns)}")
            else:
                # 3. LIMPIEZA INTELIGENTE DE DATOS
                
                # --- A) ARREGLO DEL DINERO (FORMATO ESPAÑOL) ---
                df_upload["Monto"] = df_upload["Monto"].astype(str)
                # 1. Quitamos símbolos raros (?, €)
                df_upload["Monto"] = df_upload["Monto"].str.replace('?', '', regex=False)
                df_upload["Monto"] = df_upload["Monto"].str.replace('€', '', regex=False)
                
                # 2. ELIMINAR EL PUNTO DE MILES (Ej: 1.200 -> 1200)
                # OJO: Hacemos esto antes de tocar la coma
                df_upload["Monto"] = df_upload["Monto"].str.replace('.', '', regex=False)
                
                # 3. CAMBIAR COMA POR PUNTO (Ej: 30,79 -> 30.79)
                df_upload
