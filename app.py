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

# --- IA: EXPERTO FINANCIERO (CONEXIÓN SEGURA) ---
def llamar_experto_ia(contexto):
    try:
        # Aseguramos el uso del modelo correcto para evitar el error 404
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        instrucciones = """
        Actúa como un 'Experto Financiero' de élite. 
        Analiza los datos bancarios y detecta fugas de dinero. 
        Sé directo, profesional y ofrece un plan de ahorro mensual.
        """
        response = model.generate_content(f"{instrucciones}\n\nDATOS:\n{contexto}")
        return response.text
    except Exception as e:
        return f"❌ Error IA: {str(e)}"

# --- PROCESAMIENTO DE DATOS ---
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
df = load_data()
st.title("📊 Dashboard: Histórico Financiero")

# Selector de Año (Histórico desde 2025)
años = sorted([int(a) for a in df["Año"].dropna().unique() if a >= 2025], reverse=True)
if not años: años = [2026]
año_sel = st.sidebar.selectbox("📅 Año", años)
df_year = df[df["Año"] == año_sel].copy()

t1, t2, t3, t4 = st.tabs(["🏠 Resumen", "📅 Planificador", "🤖 Gem: Experto", "📂 Editor Vivo"])

with t1:
    if not df_year.empty:
        # MÉTRICAS ANUALES
        ing = df_year[df_year["Importe_Num"] > 0]["Importe_Num"].sum()
        gas = abs(df_year[df_year["Importe_Num"] < 0]["Importe_Num"].sum())
        bal = ing - gas
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos Anuales", f"{ing:,.2f} €")
        c2.metric("Gastos Anuales", f"{gas:,.2f} €", delta_color="inverse")
        c3.metric("Balance Neto", f"{bal:,.2f} €")

        st.divider()

        # GRÁFICAS DE CONTROL
        col1, col2 = st.columns([2, 1])
        with col1:
            st.write("**Evolución Mensual**")
            df_m = df_year.groupby(["Mes", "Tipo"])["Importe_Num"].sum().abs().reset_index()
            st.plotly_chart(px.bar(df_m, x="Mes", y="Importe_Num", color="Tipo", barmode="group"), use_container_width=True)

        with col2:
            st.write("**Desglose de Gastos**")
            # SOLUCIÓN AL SHAPE ERROR: Filtramos y calculamos valores absolutos en el mismo DataFrame
            df_pie = df_year[df_year["Importe_Num"] < 0].copy()
            df_pie["Abs_Importe"] = df_pie["Importe_Num"].abs()
            
            # Ahora names y values tienen exactamente la misma longitud
            fig_pie = px.pie(df_pie, values="Abs_Importe", names="Categoria", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.warning("No hay datos para este año.")

with t3:
    st.header("🤖 Gem: Experto Financiero")
    if st.button("✨ Analizar Finanzas con Gem", type="primary"):
        with st.spinner("Analizando..."):
            top = df_year[df_year["Importe_Num"] < 0].sort_values("Importe_Num").head(5).to_string()
            ctx = f"Balance: {bal}€ | Gastos: {gas}€\nTop Gastos:\n{top}"
            st.markdown(f"### 🖋️ Diagnóstico\n{llamar_experto_ia(ctx)}")

with t4:
    st.header("📂 Editor de Datos")
    # Editor para marcar fijos
    res = st.data_editor(df_year[["Fecha", "Descripcion", "Importe", "Es_Fijo"]], use_container_width=True)
    if st.button("💾 Guardar"):
        sheet.update(f"F2:F{len(res)+1}", [[x] for x in res["Es_Fijo"].values.tolist()])
        st.success("Guardado.")
