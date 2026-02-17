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
        st.error("⚠️ Error de conexión con la base de datos.")
        st.stop()

sheet = conectar_google_sheets()

# --- LÓGICA DEL GEM: EXPERTO FINANCIERO ---
def llamar_experto_ia(contexto):
    try:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Aquí inyectamos la personalidad de tu Gem
        instrucciones_gem = """
        Eres el 'Experto Financiero'. Analizas datos bancarios con rigor y audacia.
        Tu tono es profesional, con toques de humor inteligente y siempre enfocado a la libertad financiera.
        Dime qué estoy haciendo mal, dónde están los gastos 'vampiro' y dame un plan de ahorro real.
        """
        
        response = model.generate_content(f"{instrucciones_gem}\n\nDATOS FINANCIEROS:\n{contexto}")
        return response.text
    except Exception as e:
        return f"❌ Error al conectar con tu Gem: {str(e)}"

# --- CARGA Y LIMPIEZA ---
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
st.title("📊 Centro de Control: Experto Financiero")

# Histórico desde 2025
años = sorted([int(a) for a in df["Año"].dropna().unique() if a >= 2025], reverse=True)
if not años: años = [2026]
año_sel = st.sidebar.selectbox("📅 Seleccionar Año Histórico", años)
df_year = df[df["Año"] == año_sel].copy()

t1, t2, t3, t4 = st.tabs(["🏠 Resumen General", "📅 Planificador de Fijos", "🤖 Consultar Gem Experto", "📂 Editor Vivo"])

with t1:
    if not df_year.empty:
        # MÉTRICAS ANUALES
        ing = df_year[df_year["Importe_Num"] > 0]["Importe_Num"].sum()
        gas = abs(df_year[df_year["Importe_Num"] < 0]["Importe_Num"].sum())
        bal = ing - gas
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ingresos Anuales", f"{ing:,.2f} €")
        c2.metric("Gastos Anuales", f"{gas:,.2f} €", delta_color="inverse")
        c3.metric("Balance Neto", f"{bal:,.2f} €")
        c4.metric("% Ahorro", f"{(bal/ing*100 if ing>0 else 0):.1f}%")

        st.divider()

        # GRÁFICAS DE CONTROL (CORREGIDAS)
        col1, col2 = st.columns([2, 1])
        with col1:
            st.write("**Flujo de Caja Mensual**")
            df_m = df_year.groupby(["Mes", "Tipo"])["Importe_Num"].sum().abs().reset_index()
            st.plotly_chart(px.bar(df_m, x="Mes", y="Importe_Num", color="Tipo", barmode="group"), use_container_width=True)

        with col2:
            st.write("**Gastos por Categoría**")
            # SOLUCIÓN AL SHAPE ERROR: Filtramos y creamos una columna de valores absolutos en el mismo DF
            df_gastos = df_year[df_year["Importe_Num"] < 0].copy()
            df_gastos["Val_Abs"] = df_gastos["Importe_Num"].abs()
            fig_pie = px.pie(df_gastos, values="Val_Abs", names="Categoria", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

        st.write("**Sugerencia Rápida:**")
        st.info("💡 Tu gasto más alto este año ha sido: " + df_gastos.sort_values("Importe_Num").iloc[0]["Descripcion"])
    else:
        st.warning("No hay datos para este año.")

with t3:
    st.header("🤖 Gem: Experto Financiero")
    st.write("Pulsa el botón para enviar tu balance actual a tu consultor personal.")
    
    if st.button("✨ Analizar Finanzas con Gem", type="primary"):
        with st.spinner("Conectando con tu experto..."):
            # Resumen para la IA
            top = df_year[df_year["Importe_Num"] < 0].sort_values("Importe_Num").head(5).to_string()
            ctx = f"Balance: {bal}€ | Ingresos: {ing}€ | Gastos: {gas}€\nGastos Críticos:\n{top}"
            
            informe = llamar_experto_ia(ctx)
            st.markdown(f"### 🖋️ Diagnóstico de tu Experto\n{informe}")

with t4:
    st.header("📂 Editor de Datos")
    st.write("Modifica aquí qué gastos son fijos y sincroniza con Google Sheets.")
    df_ed = df_year[["Fecha", "Descripcion", "Importe", "Es_Fijo"]].copy()
    
    res = st.data_editor(df_ed, column_config={
        "Es_Fijo": st.column_config.SelectboxColumn("Fijo", options=["SÍ", "NO"])
    }, use_container_width=True)

    if st.button("💾 Guardar Cambios"):
        sheet.update(f"F2:F{len(res)+1}", [[x] for x in res["Es_Fijo"].values.tolist()])
        st.success("¡Datos sincronizados!")
        st.rerun()
