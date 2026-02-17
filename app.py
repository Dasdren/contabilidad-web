import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import google.generativeai as genai

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Santander IA Expert", layout="wide", page_icon="🏦")

# --- CONEXIÓN GOOGLE SHEETS (Mantenemos tu lógica) ---
def conectar_google_sheets():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Contabilidad_App").sheet1
        return sheet
    except:
        st.error("⚠️ Error de conexión.")
        st.stop()

sheet = conectar_google_sheets()

# --- LÓGICA DEL GEM "EXPERTO FINANCIERO" ---
def ejecutar_experto_financiero(contexto_datos):
    try:
        api_key = st.secrets["gemini_api_key"]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Aquí definimos las instrucciones que tiene tu "Gem"
        instrucciones_gem = """
        Eres 'Experto Financiero', un consultor de alto nivel. 
        Tu tono es profesional, analítico y motivador. 
        Tu objetivo es encontrar ineficiencias en el gasto y maximizar el ahorro.
        Analiza los datos que te paso y da:
        1. Un diagnóstico de salud (Semáforo: Verde, Ámbar, Rojo).
        2. Identificación de 'Gastos Vampiro'.
        3. Una estrategia concreta para el próximo mes.
        """
        
        prompt = f"{instrucciones_gem}\n\nDATOS REALES DEL USUARIO:\n{contexto_datos}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error al conectar con el Experto: {e}"

# --- LIMPIEZA Y CARGA (Mantenemos tus mejoras) ---
def limpiar_importe(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('−', '-')
    if ',' in s: s = s.replace('.', '').replace(',', '.')
    s = "".join(c for c in s if c.isdigit() or c in '.-')
    try: return float(s)
    except: return 0.0

def load_data():
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
    df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
    df["Año"] = df["Fecha_DT"].dt.year
    return df

# --- INTERFAZ ---
df = load_data()
st.title("🏦 Santander Smart Intelligence")

# Selector de año (Desde 2025)
años = sorted([int(a) for a in df["Año"].dropna().unique() if a >= 2025])
if not años: años = [2025]
año_sel = st.sidebar.selectbox("Selecciona Año", años)
df_year = df[df["Año"] == año_sel]

t1, t2, t3 = st.tabs(["🏠 Dashboard Anual", "📅 Planificador de Fijos", "📂 Editor Vivo"])

with t1:
    # MÉTRICAS RÁPIDAS
    ingresos = df_year[df_year["Importe_Num"] > 0]["Importe_Num"].sum()
    gastos = abs(df_year[df_year["Importe_Num"] < 0]["Importe_Num"].sum())
    balance = ingresos - gastos
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Ingresos Anuales", f"{ingresos:,.2f} €")
    c2.metric("Gastos Anuales", f"{gastos:,.2f} €")
    c3.metric("Balance Neto", f"{balance:,.2f} €")

    st.divider()

    # --- BOTÓN DEL GEM EXPERTO FINANCIERO ---
    st.subheader("🤖 Consultoría de 'Experto Financiero'")
    st.write("Pulsa el botón para que tu Gem analice automáticamente tus movimientos de este año.")
    
    if st.button("✨ Ejecutar Análisis del Experto", type="primary"):
        with st.spinner("Tu Experto Financiero está revisando las cuentas..."):
            # Preparamos el contexto para la IA
            top_gastos = df_year[df_year["Importe_Num"] < 0].sort_values("Importe_Num").head(8)
            fijos = df_year[df_year["Es_Fijo"] == "SÍ"]["Importe_Num"].sum()
            
            contexto = f"""
            Año analizado: {año_sel}
            Balance actual: {balance}€
            Total ingresos: {ingresos}€
            Total gastos: {gastos}€
            Gasto en Fijos (alquiler, suscripciones, etc): {fijos}€
            Lista de mayores gastos:
            {top_gastos[['Descripcion', 'Importe_Num']].to_string()}
            """
            
            analisis = ejecutar_experto_financiero(contexto)
            
            st.markdown("---")
            st.markdown(f"### 🖋️ Informe de tu Experto Financiero\n{analisis}")
            st.download_button("Descargar Informe (TXT)", analisis, file_name=f"Analisis_{año_sel}.txt")
            st.markdown("---")

    # GRÁFICAS (Mantenemos tus gráficas de control)
    col_a, col_b = st.columns(2)
    with col_a:
        st.plotly_chart(px.bar(df_year, x=df_year["Fecha_DT"].dt.month, y="Importe_Num", color="Tipo", title="Flujo de Caja"), use_container_width=True)
    with col_b:
        st.plotly_chart(px.pie(df_year[df_year["Importe_Num"]<0], values=abs(df_year["Importe_Num"]), names="Categoria", title="Gastos por Categoría"), use_container_width=True)

# (Pestañas de Planificador y Editor se mantienen con tu lógica actual)
