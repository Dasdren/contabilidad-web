import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import google.generativeai as genai

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Santander Smart Dashboard", layout="wide", page_icon="📊")

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
        st.error("⚠️ Error de conexión con Google Sheets.")
        st.stop()

sheet = conectar_google_sheets()

# --- IA: CONSULTA ---
def consultar_gemini(datos_contexto):
    try:
        api_key = st.secrets["gemini_api_key"]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"Analiza estos datos financieros y dame 3 sugerencias críticas de ahorro e inversión: {datos_contexto}. Se muy breve, usa viñetas y habla de tú."
        response = model.generate_content(prompt)
        return response.text
    except:
        return "No se han podido generar sugerencias en este momento."

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
    cols_base = ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]
    for c in cols_base:
        if c not in df.columns: df[c] = ""
    df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
    df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
    df["Mes"] = df["Fecha_DT"].dt.strftime('%b')
    df["Año"] = df["Fecha_DT"].dt.year
    return df

# --- INTERFAZ PRINCIPAL ---
df = load_data()
st.title("📊 Centro de Control Financiero")

# --- SIDEBAR: IMPORTACIÓN ---
with st.sidebar:
    st.header("📥 Importar Santander")
    archivo = st.sidebar.file_uploader("Subir CSV", type=["csv"])
    if archivo:
        if st.button("🚀 Procesar CSV"):
            # Lógica de importación (resumida para brevedad)
            raw = archivo.getvalue().decode("utf-8").splitlines()
            skip = 0
            for i, line in enumerate(raw):
                if "Fecha operación" in line: skip = i; break
            archivo.seek(0)
            df_new = pd.read_csv(archivo, skiprows=skip, dtype=str, engine='python')
            df_new.columns = df_new.columns.str.strip()
            df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
            df_new.columns = ["Fecha", "Descripcion", "Importe"]
            df_new["Importe_Num"] = df_new["Importe"].apply(limpiar_importe)
            df_new["Tipo"] = np.where(df_new["Importe_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            df_new["Es_Fijo"] = "NO"
            sheet.append_rows(df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]].values.tolist())
            st.success("¡Importado!")
            st.rerun()

# --- PESTAÑAS ---
t1, t2, t3, t4 = st.tabs(["🏠 Resumen General", "📅 Planificador", "🤖 Consultor IA", "📂 Editor Vivo"])

with t1:
    if not df.empty:
        año_actual = datetime.now().year
        df_year = df[df["Año"] == año_actual]
        
        # 1. MÉTRICAS ANUALES
        st.subheader(f"📈 Balance Anual {año_actual}")
        c1, c2, c3, c4 = st.columns(4)
        ingresos = df_year[df_year["Importe_Num"] > 0]["Importe_Num"].sum()
        gastos = df_year[df_year["Importe_Num"] < 0]["Importe_Num"].sum()
        balance = ingresos + gastos
        
        c1.metric("Ingresos Año", f"{ingresos:,.2f} €")
        c2.metric("Gastos Año", f"{abs(gastos):,.2f} €", delta_color="inverse")
        c3.metric("Balance Neto", f"{balance:,.2f} €")
        c4.metric("Ahorro %", f"{(balance/ingresos*100 if ingresos != 0 else 0):.1f}%")

        # 2. GRÁFICAS DE CONTROL
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.write("**Evolución Mensual (Flujo de Caja)**")
            df_mes = df_year.groupby(["Mes", "Tipo"])["Importe_Num"].sum().reset_index()
            fig_evol = px.bar(df_mes, x="Mes", y="Importe_Num", color="Tipo", barmode="group",
                             color_discrete_map={"Ingreso": "#2ecc71", "Gasto": "#e74c3c"})
            st.plotly_chart(fig_evol, use_container_width=True)
            
        with col_g2:
            st.write("**Desglose de Gastos por Categoría**")
            df_gastos = df_year[df_year["Importe_Num"] < 0]
            fig_pie = px.pie(df_gastos, values=abs(df_gastos["Importe_Num"]), names="Categoria", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

        # 3. SUGERENCIAS IA Y DESGLOSE DETALLADO
        col_inf1, col_inf2 = st.columns([1, 1.5])
        
        with col_inf1:
            st.write("✨ **Sugerencias de la IA**")
            if st.button("Generar Insights"):
                ctx = f"Gastos: {abs(gastos)}€. Ingresos: {ingresos}€."
                st.info(consultar_gemini(ctx))
            else:
                st.caption("Pulsa para que la IA analice tu año.")
                
        with col_inf2:
            st.write("**Top 5 Gastos más grandes**")
            top_gastos = df_year[df_year["Importe_Num"] < 0].sort_values("Importe_Num").head(5)
            st.table(top_gastos[["Fecha", "Descripcion", "Importe"]])

with t2:
    st.header("Planificador de Suelo Mensual")
    fijos = df[(df["Es_Fijo"].str.upper() == "SÍ") & (df["Importe_Num"] < 0)]
    presupuesto = fijos.drop_duplicates(subset=['Descripcion', 'Importe_Num'], keep='last')
    st.metric("Total Gastos Fijos (Mes)", f"{presupuesto['Importe_Num'].sum():,.2f} €")
    st.dataframe(presupuesto[["Descripcion", "Importe"]], use_container_width=True)

with t4:
    st.header("📂 Editor en Vivo")
    st.write("Modifica aquí si un gasto es **SÍ** o **NO** Fijo. Al terminar, dale a Guardar.")
    
    # Editor de datos para Es_Fijo
    df_editor = df[["Fecha", "Descripcion", "Importe", "Es_Fijo"]].copy()
    edited_df = st.data_editor(df_editor, column_config={
        "Es_Fijo": st.column_config.SelectboxColumn("Fijo", options=["SÍ", "NO"])
    }, disabled=["Fecha", "Descripcion", "Importe"], use_container_width=True)

    if st.button("💾 Guardar Cambios"):
        vals = [[v] for v in edited_df["Es_Fijo"].values.tolist()]
        sheet.update(f"F2:F{len(vals)+1}", vals)
        st.success("Guardado en Google Sheets.")
        st.rerun()
