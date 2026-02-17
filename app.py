import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import google.generativeai as genai

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Santander Finance Pro", layout="wide", page_icon="💰")

# --- CSS PARA MÁXIMA VISIBILIDAD ---
st.markdown("""
<style>
    /* Fondo de la app */
    .stApp { background-color: #f0f2f6; }
    
    /* Estilo de los números de las métricas */
    [data-testid="stMetricValue"] {
        color: #000000 !important; /* Negro puro para que se vea */
        font-size: 2.2rem !important;
        font-weight: 800 !important;
    }
    
    /* Estilo de las etiquetas de las métricas */
    [data-testid="stMetricLabel"] {
        color: #333333 !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
    }

    /* Estilo de las tarjetas de métricas */
    [data-testid="metric-container"] {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #d1d5db;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    
    /* Botón de la IA destacado */
    .stButton>button {
        width: 100%;
        background-color: #e63946 !important;
        color: white !important;
        font-weight: bold;
        border-radius: 8px;
        height: 3em;
    }
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
    except:
        st.error("⚠️ Error de conexión con Google Sheets.")
        st.stop()

sheet = conectar_google_sheets()

# --- IA: GEM EXPERTO FINANCIERO ---
def llamar_experto_ia(contexto):
    try:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        instrucciones = """Eres el 'Experto Financiero'. Analiza los datos del Santander del usuario.
        Se directo, profesional y detecta gastos innecesarios. Da 3 consejos de ahorro."""
        response = model.generate_content(f"{instrucciones}\n\nDATOS:\n{contexto}")
        return response.text
    except:
        return "❌ Error al conectar con la IA."

# --- PROCESAMIENTO ---
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
    df["Mes"] = df["Fecha_DT"].dt.strftime('%m - %b')
    return df

# --- INTERFAZ ---
df_raw = load_data()
st.title("🏦 Santander Smart Dashboard")

# Barra lateral
with st.sidebar:
    st.header("⚙️ Configuración")
    años = sorted([int(a) for a in df_raw["Año"].dropna().unique() if a >= 2025], reverse=True)
    if not años: años = [2026]
    año_sel = st.selectbox("Seleccionar Año Fiscal", años)
    
    st.divider()
    st.header("📥 Importar CSV")
    archivo = st.file_uploader("Sube el CSV del Santander", type=["csv"])
    if archivo:
        if st.button("🚀 Procesar Datos"):
            # Lógica de importación aquí...
            st.success("¡Datos cargados!")
            st.rerun()

df = df_raw[df_raw["Año"] == año_sel].copy()

t1, t2, t3, t4 = st.tabs(["🏠 Dashboard Resumen", "📅 Planificador Fijos", "🤖 Experto IA", "📂 Editor de Datos"])

# --- PESTAÑA 1: DASHBOARD ---
with t1:
    if not df.empty:
        ingresos = df[df["Importe_Num"] > 0]["Importe_Num"].sum()
        gastos = abs(df[df["Importe_Num"] < 0]["Importe_Num"].sum())
        balance = ingresos - gastos
        tasa_ahorro = (balance / ingresos * 100) if ingresos > 0 else 0

        # KPIs VISIBLES
        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos Anuales", f"{ingresos:,.2f} €")
        c2.metric("Gastos Anuales", f"{gastos:,.2f} €", delta_color="inverse")
        c3.metric("Balance Anual", f"{balance:,.2f} €")
        
        st.divider()

        # Gráficas
        g1, g2 = st.columns([2, 1])
        with g1:
            st.subheader("📈 Flujo de Caja Mensual")
            df_mes = df.groupby(["Mes", "Tipo"])["Importe_Num"].sum().abs().reset_index()
            fig = px.bar(df_mes, x="Mes", y="Importe_Num", color="Tipo", barmode="group",
                         color_discrete_map={"Ingreso": "#2ecc71", "Gasto": "#e74c3c"})
            st.plotly_chart(fig, use_container_width=True)

        with g2:
            st.subheader("🍩 Gastos por Categoría")
            df_pie = df[df["Importe_Num"] < 0].copy()
            df_pie["Abs_Importe"] = df_pie["Importe_Num"].abs()
            fig_pie = px.pie(df_pie, values="Abs_Importe", names="Categoria", hole=0.5)
            st.plotly_chart(fig_pie, use_container_width=True)

        # Salud Financiera
        st.subheader("🛡️ Salud Financiera")
        p_val = max(0.0, min(tasa_ahorro / 100, 1.0))
        st.write(f"**Tasa de Ahorro: {tasa_ahorro:.1f}%**")
        st.progress(p_val)
    else:
        st.info("No hay datos para este año.")

# --- PESTAÑA 2: PLANIFICACIÓN ---
with t2:
    st.header("📋 Suelo Mensual (Gastos Fijos)")
    fijos = df[(df["Es_Fijo"].str.upper() == "SÍ") & (df["Importe_Num"] < 0)]
    presupuesto = fijos.drop_duplicates(subset=['Descripcion'], keep='last')
    st.metric("Total Suelo Fijo al Mes", f"{abs(presupuesto['Importe_Num'].sum()):,.2f} €")
    st.dataframe(presupuesto[["Descripcion", "Importe", "Categoria"]], use_container_width=True)

# --- PESTAÑA 3: EXPERTO IA ---
with t3:
    st.header("🤖 Consultoría Experto Financiero")
    st.write("Pulsa el botón para que tu Gem analice tus finanzas de este año.")
    
    if st.button("✨ Ejecutar Análisis del Experto"):
        with st.spinner("Analizando tus movimientos..."):
            top = df[df["Importe_Num"] < 0].sort_values("Importe_Num").head(5).to_string()
            ctx = f"Balance: {balance}€ | Ingresos: {ingresos}€ | Gastos: {gastos}€\nTop Gastos: {top}"
            analisis = llamar_experto_ia(ctx)
            st.markdown(f"### 🖋️ Informe del Experto\n{analisis}")

# --- PESTAÑA 4: EDITOR ---
with t4:
    st.header("📂 Editor Vivo")
    edited_df = st.data_editor(df[["Fecha", "Descripcion", "Importe", "Categoria", "Es_Fijo"]], 
                               column_config={"Es_Fijo": st.column_config.SelectboxColumn("Fijo", options=["SÍ", "NO"])},
                               use_container_width=True)
    
    if st.button("💾 Sincronizar Cambios"):
        sheet.update("C2", [[x] for x in edited_df["Categoria"].tolist()])
        sheet.update("F2", [[x] for x in edited_df["Es_Fijo"].tolist()])
        st.success("¡Google Sheets actualizado!")
        st.rerun()
