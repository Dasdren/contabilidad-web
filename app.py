import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import google.generativeai as genai

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Santander IA Expert 2026", layout="wide", page_icon="📈")

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
        st.error("⚠️ Error de conexión con Google Sheets. Revisa tus Secrets.")
        st.stop()

sheet = conectar_google_sheets()

# --- IA: EXPERTO FINANCIERO (CONEXIÓN CORREGIDA) ---
def llamar_experto_ia(contexto):
    try:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        # Usamos el nombre de modelo más compatible
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        instrucciones_gem = """
        Eres el 'Experto Financiero' personal del usuario. 
        Tu misión es analizar los movimientos bancarios del Santander.
        Personalidad: Analítico, directo, con visión de ahorro a largo plazo.
        Analiza los datos y proporciona:
        1. Estado de salud financiera (Rating A+ a E).
        2. Alerta de 'Fugas de Capital' (Gastos variables excesivos).
        3. Plan de acción concreto para este mes.
        """
        
        response = model.generate_content(f"{instrucciones_gem}\n\nDATOS:\n{contexto}")
        return response.text
    except Exception as e:
        return f"❌ Error de conexión con el Experto: {str(e)}"

# --- LIMPIEZA Y CARGA ---
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
    # Columnas: Fecha, Tipo, Categoria, Descripcion, Importe, Es_Fijo
    df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
    df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
    df["Año"] = df["Fecha_DT"].dt.year
    df["Mes"] = df["Fecha_DT"].dt.strftime('%m - %b')
    return df

# --- INTERFAZ ---
df = load_data()
st.title("🏦 Santander Smart Dashboard 2026")

# Selector de Año en Sidebar (Desde 2025)
años = sorted([int(a) for a in df["Año"].dropna().unique() if a >= 2025], reverse=True)
if not años: años = [2026]
año_sel = st.sidebar.selectbox("📅 Año Fiscal", años)
df_year = df[df["Año"] == año_sel]

t1, t2, t3, t4 = st.tabs(["🏠 Resumen Anual", "📅 Planificador de Fijos", "🤖 Experto Financiero Gem", "📂 Editor Vivo"])

with t1:
    if not df_year.empty:
        # 1. BALANCE ANUAL
        ingresos = df_year[df_year["Importe_Num"] > 0]["Importe_Num"].sum()
        gastos = abs(df_year[df_year["Importe_Num"] < 0]["Importe_Num"].sum())
        balance = ingresos - gastos
        ahorro_pct = (balance / ingresos * 100) if ingresos > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Ingresos Año", f"{ingresos:,.2f} €")
        c2.metric("📉 Gastos Año", f"{gastos:,.2f} €", delta_color="inverse")
        c3.metric("⚖️ Balance Neto", f"{balance:,.2f} €")
        c4.metric("📈 % Ahorro", f"{ahorro_pct:.1f}%")

        st.divider()

        # 2. GRÁFICAS DE CONTROL
        col_g1, col_g2 = st.columns([2, 1])
        with col_g1:
            st.subheader("📊 Flujo de Caja Mensual")
            df_mes = df_year.groupby(["Mes", "Tipo"])["Importe_Num"].sum().abs().reset_index()
            fig_bar = px.bar(df_mes, x="Mes", y="Importe_Num", color="Tipo", barmode="group",
                             color_discrete_map={"Ingreso": "#2ecc71", "Gasto": "#e74c3c"})
            st.plotly_chart(fig_bar, use_container_width=True)
        
        with col_g2:
            st.subheader("🍩 Gastos por Categoría")
            fig_pie = px.pie(df_year[df_year["Importe_Num"]<0], values=abs(df_year["Importe_Num"]), names="Categoria", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

        # 3. TOP GASTOS
        st.subheader("🔍 Desglose de Gastos Críticos")
        st.dataframe(df_year[df_year["Importe_Num"] < 0].sort_values("Importe_Num").head(10)[["Fecha", "Descripcion", "Importe", "Categoria"]], use_container_width=True)
    else:
        st.info("Sube datos para ver el resumen del año.")

with t3:
    st.header("🤖 Consultoría con Experto Financiero")
    st.write("Haz clic en el botón para que tu 'Gem' analice tu historial completo del año.")
    
    if st.button("✨ Ejecutar Análisis Estratégico", type="primary"):
        with st.spinner("Tu Experto Financiero está procesando los números..."):
            # Resumen para la IA
            top_gastos = df_year[df_year["Importe_Num"] < 0].sort_values("Importe_Num").head(5).to_string()
            fijos_total = df_year[df_year["Es_Fijo"] == "SÍ"]["Importe_Num"].sum()
            
            contexto = f"""
            Año: {año_sel} | Balance: {balance}€ | Ingresos: {ingresos}€ | Gastos: {gastos}€
            Total Gastos Fijos: {abs(fijos_total)}€
            Mayores gastos: {top_gastos}
            """
            
            informe = llamar_experto_ia(contexto)
            st.markdown(f"### 🖋️ Informe del Experto\n{informe}")

with t4:
    st.header("📂 Gestión de Gastos Fijos")
    st.write("Modifica la columna **Es_Fijo** y pulsa Guardar para actualizar tu planificador.")
    df_editor = df_year[["Fecha", "Descripcion", "Importe", "Es_Fijo"]].copy()
    
    edited_df = st.data_editor(df_editor, column_config={
        "Es_Fijo": st.column_config.SelectboxColumn("Gasto Fijo", options=["SÍ", "NO"])
    }, disabled=["Fecha", "Descripcion", "Importe"], use_container_width=True)

    if st.button("💾 Sincronizar con Google Sheets"):
        # Importante: Actualizamos el histórico completo
        indices_fijos = edited_df["Es_Fijo"].values.tolist()
        # Nota: Aquí actualizamos solo el bloque visualizado para evitar desajustes
        sheet.update(f"F2:F{len(indices_fijos)+1}", [[x] for x in indices_fijos])
        st.success("¡Sincronizado!")
        st.rerun()
