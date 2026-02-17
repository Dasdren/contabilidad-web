import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import google.generativeai as genai

# --- CONFIGURACIÓN VISUAL (MODO CYBER) ---
st.set_page_config(page_title="Santander Cyber Dashboard", layout="wide", page_icon="🌙")

st.markdown("""
<style>
    .stApp { background-color: #000000 !important; color: #FFFFFF !important; }
    h1, h2, h3, p, span, label { color: #FFFFFF !important; }
    [data-testid="metric-container"] { background-color: #111111; border: 1px solid #333333; padding: 20px; border-radius: 12px; }
    .green-led { color: #2ecc71 !important; font-size: 2rem; font-weight: 800; }
    .red-led { color: #e63946 !important; font-size: 2rem; font-weight: 800; }
    .blue-led { color: #3498db !important; font-size: 2rem; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN GOOGLE SHEETS ---
def conectar_google_sheets():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Contabilidad_App").sheet1
        return sheet
    except Exception as e:
        st.error(f"Error conexión Sheets: {e}")
        st.stop()

sheet = conectar_google_sheets()

# --- IA: EXPERTO FINANCIERO (FIX 404) ---
def llamar_experto_ia(contexto):
    try:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        # Nombre de modelo corregido para evitar el 404
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"Actúa como Experto Financiero. Analiza estos datos: {contexto}. Sé breve y da 3 consejos."
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Error en la IA: {str(e)}"

# --- LIMPIEZA DE IMPORTES ---
def limpiar_importe(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('−', '-')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    s = "".join(c for c in s if c.isdigit() or c in '.-')
    try: return float(s)
    except: return 0.0

# --- CARGA DE DATOS ---
def load_data():
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    if not df.empty:
        df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Año"] = df["Fecha_DT"].dt.year
    return df

# --- INTERFAZ ---
df_raw = load_data()
st.title("🌙 Santander Cyber Dashboard")

with st.sidebar:
    st.header("📥 Importar Santander")
    archivo = st.file_uploader("Sube el CSV", type=["csv"])
    if archivo:
        if st.button("🚀 Procesar e Importar"):
            try:
                # FIX: Detección automática de separador (Santander suele usar ;)
                raw_data = archivo.getvalue().decode("utf-8")
                sep = ';' if ';' in raw_data.splitlines()[header_idx if 'header_idx' in locals() else 0] else ','
                
                archivo.seek(0)
                # Buscamos la fila de cabecera real
                df_new = pd.read_csv(archivo, sep=None, engine='python', dtype=str)
                df_new.columns = df_new.columns.str.strip()
                
                # Mapeo exacto basado en tu imagen
                df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
                df_new.columns = ["Fecha", "Descripcion", "Importe"]
                df_new["Tipo"] = "Gasto"
                df_new["Categoria"] = "Varios"
                df_new["Es_Fijo"] = "NO"
                
                sheet.append_rows(df_new.values.tolist())
                st.success("¡Importado con éxito!")
                st.rerun()
            except Exception as e:
                st.error(f"Error procesando CSV: {e}")

# --- PESTAÑAS ---
t1, t2, t3, t4 = st.tabs(["📊 Resumen", "📅 Fijos", "🤖 Experto IA", "📂 Editor"])

df = df_raw if 'df_raw' in locals() else pd.DataFrame()

with t1:
    if not df.empty:
        ing = df[df["Importe_Num"] > 0]["Importe_Num"].sum()
        gas = abs(df[df["Importe_Num"] < 0]["Importe_Num"].sum())
        c1, c2, c3 = st.columns(3)
        c1.markdown(f'<p class="green-led">+{ing:,.2f} €</p>', unsafe_allow_html=True)
        c2.markdown(f'<p class="red-led">-{gas:,.2f} €</p>', unsafe_allow_html=True)
        c3.markdown(f'<p class="blue-led">{(ing-gas):,.2f} €</p>', unsafe_allow_html=True)

with t3:
    st.header("🤖 Consultoría Experto Gem")
    if st.button("✨ Ejecutar Análisis Estratégico"):
        # Sistema de seguridad para no colgar la app
        with st.spinner("Analizando..."):
            resumen = f"Ingresos: {ing}€, Gastos: {gas}€" if 'ing' in locals() else "Sin datos"
            respuesta = llamar_experto_ia(resumen)
            st.markdown(f"### 🖋️ Resultado:\n{respuesta}")
