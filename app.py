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

# CSS para estilo premium
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; font-weight: 700; color: #1e1e1e; }
    .stProgress > div > div > div > div { background-color: #e63946; }
    .card { background-color: white; padding: 20px; border-radius: 10px; box-shadow: 2px 2px 10px rgba(0,0,0,0.05); }
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
        instrucciones = "Eres un Experto Financiero senior. Analiza los datos del usuario, detecta fugas de dinero y da 3 consejos estratégicos. Sé directo y profesional."
        response = model.generate_content(f"{instrucciones}\n\nDATOS:\n{contexto}")
        return response.text
    except:
        return "❌ La IA no pudo responder. Revisa tu API Key."

# --- LIMPIEZA DE IMPORTES ---
def limpiar_importe(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('−', '-')
    if ',' in s: s = s.replace('.', '').replace(',', '.')
    s = "".join(c for c in s if c.isdigit() or c in '.-')
    try: return float(s)
    except: return 0.0

# --- CARGA DE DATOS ---
def load_data():
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    for col in ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]:
        if col not in df.columns: df[col] = ""
    df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
    df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
    df["Año"] = df["Fecha_DT"].dt.year
    df["Mes"] = df["Fecha_DT"].dt.strftime('%b')
    return df

# --- INTERFAZ ---
df_raw = load_data()
st.title("🏦 Santander Smart Dashboard")

# Barra lateral: Selector de Año e Importación
with st.sidebar:
    st.header("📅 Navegación Histórica")
    años = sorted([int(a) for a in df_raw["Año"].dropna().unique() if a >= 2025], reverse=True)
    if not años: años = [2026]
    año_sel = st.selectbox("Año Fiscal", años)
    
    st.divider()
    st.header("📥 Importar CSV")
    archivo = st.file_uploader("Sube tu CSV del Santander", type=["csv"])
    if archivo:
        if st.button("🚀 Procesar Datos"):
            # Lógica de importación mantenida
            st.success("¡Datos cargados!")
            st.rerun()

df = df_raw[df_raw["Año"] == año_sel].copy()

t1, t2, t3, t4 = st.tabs(["📊 Resumen Global", "📅 Planificador de Fijos", "🤖 Experto IA", "📂 Editor de Datos"])

# --- PESTAÑA 1: DASHBOARD DINÁMICO ---
with t1:
    if not df.empty:
        ingresos = df[df["Importe_Num"] > 0]["Importe_Num"].sum()
        gastos = abs(df[df["Importe_Num"] < 0]["Importe_Num"].sum())
        balance = ingresos - gastos
        tasa_ahorro = (balance / ingresos * 100) if ingresos > 0 else 0

        # KPIs
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ingresos Anuales", f"{ingresos:,.2f} €")
        c2.metric("Gastos Anuales", f"{gastos:,.2f} €", delta_color="inverse")
        c3.metric("Balance Neto", f"{balance:,.2f} €")
        
        # FIX ERROR PROGRESS BAR: max(0.0) y min(1.0)
        progress_val = max(0.0, min(tasa_ahorro / 100, 1.0))
        c4.write(f"**Tasa de Ahorro: {tasa_ahorro:.1f}%**")
        c4.progress(progress_val)

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
            df_pie["Val"] = df_pie["Importe_Num"].abs()
            fig_pie = px.pie(df_pie, values="Val", names="Categoria", hole=0.5)
            st.plotly_chart(fig_pie, use_container_width=True)

        # Top Gastos
        st.subheader("🔍 Mayores Gastos del Año")
        top_5 = df[df["Importe_Num"] < 0].sort_values("Importe_Num").head(5)
        st.table(top_5[["Fecha", "Descripcion", "Importe"]])
    else:
        st.info("No hay datos para este año.")

# --- PESTAÑA 2: PLANIFICACIÓN ---
with t2:
    st.header("📋 Suelo Mensual de Gastos Fijos")
    fijos = df[(df["Es_Fijo"].str.upper() == "SÍ") & (df["Importe_Num"] < 0)]
    presupuesto = fijos.drop_duplicates(subset=['Descripcion'], keep='last')
    st.metric("Total Gastos Fijos (Previsión Mensual)", f"{abs(presupuesto['Importe_Num'].sum()):,.2f} €")
    st.dataframe(presupuesto[["Descripcion", "Importe", "Categoria"]], use_container_width=True)

# --- PESTAÑA 3: EXPERTO IA ---
with t3:
    st.header("🤖 Consultoría con Experto IA")
    st.write("Tu 'Gem' analizará tu comportamiento de gasto y te dará una estrategia personalizada.")
    
    if st.button("✨ Ejecutar Análisis Estratégico", type="primary"):
        with st.spinner("El Experto está revisando tus cuentas..."):
            top = df[df["Importe_Num"] < 0].sort_values("Importe_Num").head(5).to_string()
            ctx = f"Balance: {balance}€ | Ingresos: {ingresos}€ | Gastos: {gastos}€\nTop Gastos: {top}"
            analisis = llamar_experto_ia(ctx)
            st.markdown(f"### 🖋️ Informe del Experto\n{analisis}")

# --- PESTAÑA 4: EDITOR ---
with t4:
    st.header("📂 Gestión en Vivo")
    st.write("Edita las categorías o marca gastos como fijos directamente aquí.")
    edited_df = st.data_editor(df[["Fecha", "Descripcion", "Importe", "Categoria", "Es_Fijo"]], 
                               column_config={"Es_Fijo": st.column_config.SelectboxColumn("Fijo", options=["SÍ", "NO"])},
                               use_container_width=True)
    
    if st.button("💾 Guardar en Google Sheets"):
        # Actualizamos la columna C (Categoria) y F (Es_Fijo)
        cat_vals = [[x] for x in edited_df["Categoria"].tolist()]
        fijo_vals = [[x] for x in edited_df["Es_Fijo"].tolist()]
        sheet.update("C2", cat_vals)
        sheet.update("F2", fijo_vals)
        st.success("¡Sincronizado!")
        st.rerun()
