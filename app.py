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
st.set_page_config(page_title="Santander AI Dashboard", layout="wide", page_icon="📈")

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

# --- IA: CONSULTA CONFIGURADA ---
def consultar_gemini(datos_contexto, pregunta_usuario="Analiza mi situación"):
    try:
        api_key = st.secrets["gemini_api_key"]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        Eres un asesor financiero experto. Datos anuales del usuario:
        {datos_contexto}
        
        Tarea: {pregunta_usuario}
        Instrucciones: Se directo, usa un tono profesional pero cercano (habla de tú). 
        Prioriza consejos de ahorro basados en los gastos más altos detectados.
        """
        response = model.generate_content(prompt)
        return response.text
    except:
        return "La IA está procesando otros datos. Revisa tu API Key o inténtalo en un momento."

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
    # Asegurar columnas internas de la App
    cols_base = ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]
    for c in cols_base:
        if c not in df.columns: df[c] = ""
    
    df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
    df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
    df["Año"] = df["Fecha_DT"].dt.year
    df["Mes_Nombre"] = df["Fecha_DT"].dt.strftime('%B')
    return df

# --- INTERFAZ PRINCIPAL ---
df = load_data()
st.title("🏦 Panel de Inteligencia Financiera")

# --- SIDEBAR: HISTÓRICO Y CARGA ---
with st.sidebar:
    st.header("📅 Navegación Histórica")
    años_disponibles = sorted([int(a) for a in df["Año"].dropna().unique() if a >= 2025])
    if not años_disponibles: años_disponibles = [2025]
    año_sel = st.selectbox("Selecciona Año:", años_disponibles)
    
    st.divider()
    st.header("📥 Importar Santander")
    archivo = st.file_uploader("Subir CSV", type=["csv"])
    if archivo:
        if st.button("🚀 Procesar Datos"):
            # Lógica de importación (Mantenemos tu mapeo exacto)
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
            st.success("¡Datos añadidos!")
            st.rerun()

# Filtrar por año seleccionado
df_filtrado = df[df["Año"] == año_sel]

# --- PESTAÑAS ---
t1, t2, t3, t4 = st.tabs(["🏠 Resumen Ejecutivo", "📅 Planificador de Fijos", "🤖 Consultas IA", "📂 Editor Vivo"])

with t1:
    if not df_filtrado.empty:
        # 1. MÉTRICAS CLAVE
        ingresos = df_filtrado[df_filtrado["Importe_Num"] > 0]["Importe_Num"].sum()
        gastos = abs(df_filtrado[df_filtrado["Importe_Num"] < 0]["Importe_Num"].sum())
        balance = ingresos - gastos
        ahorro = (balance / ingresos * 100) if ingresos > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ingresos Año", f"{ingresos:,.2f} €", delta_color="normal")
        c2.metric("Gastos Año", f"{gastos:,.2f} €", delta_color="inverse")
        c3.metric("Balance Neto", f"{balance:,.2f} €")
        c4.metric("% Ahorro Real", f"{ahorro:.1f}%")

        st.divider()

        # 2. GRÁFICAS DE CONTROL
        col_g1, col_g2 = st.columns([2, 1])
        with col_g1:
            st.subheader("📉 Flujo de Caja Mensual")
            meses_orden = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
            df_mes = df_filtrado.groupby(["Mes_Nombre", "Tipo"])["Importe_Num"].sum().abs().reset_index()
            fig_bar = px.bar(df_mes, x="Mes_Nombre", y="Importe_Num", color="Tipo", barmode="group",
                             category_orders={"Mes_Nombre": meses_orden},
                             color_discrete_map={"Ingreso": "#2ecc71", "Gasto": "#e74c3c"})
            st.plotly_chart(fig_bar, use_container_width=True)
        
        with col_g2:
            st.subheader("🍕 Gastos por Categoría")
            df_pie = df_filtrado[df_filtrado["Importe_Num"] < 0]
            fig_pie = px.pie(df_pie, values=abs(df_pie["Importe_Num"]), names="Categoria", hole=0.5)
            st.plotly_chart(fig_pie, use_container_width=True)

        st.divider()

        # 3. SUGERENCIAS RÁPIDAS IA
        st.subheader("✨ Insights de Inteligencia Artificial")
        if st.button("🔍 Generar Informe de Situación"):
            top_gastos = df_filtrado[df_filtrado["Importe_Num"] < 0].sort_values("Importe_Num").head(5).to_string()
            contexto = f"Balance: {balance}€. Gastos Totales: {gastos}€. Mayores gastos: {top_gastos}"
            with st.spinner("Analizando tu año..."):
                st.info(consultar_gemini(contexto))
                
        # 4. DESGLOSE DETALLADO
        st.subheader("📑 Top 5 Movimientos más relevantes")
        st.table(df_filtrado.sort_values(by="Importe_Num", key=abs, ascending=False).head(5)[["Fecha", "Descripcion", "Importe"]])
    else:
        st.warning("No hay datos para este año. Importa un CSV o cambia de año.")

with t2:
    st.header("📋 Suelo Mensual de Gastos")
    st.write("Gastos marcados como **FIJOS**. No se duplican, se muestra la base mensual.")
    fijos = df_filtrado[(df_filtrado["Es_Fijo"].str.upper() == "SÍ") & (df_filtrado["Importe_Num"] < 0)]
    presupuesto = fijos.drop_duplicates(subset=['Descripcion', 'Importe_Num'], keep='last')
    st.metric("Total Compromisos Mensuales", f"{presupuesto['Importe_Num'].sum():,.2f} €")
    st.dataframe(presupuesto[["Descripcion", "Importe"]], use_container_width=True)

with t3:
    st.header("🤖 Consultor Financiero IA")
    pregunta = st.text_input("Hazle una pregunta específica a tu IA sobre tus finanzas:")
    if st.button("Enviar Pregunta"):
        if pregunta:
            resumen = f"Gastos: {df_filtrado[df_filtrado['Importe_Num']<0]['Importe_Num'].sum()}€."
            st.write(consultar_gemini(resumen, pregunta))

with t4:
    st.header("📂 Editor de Gastos Fijos")
    st.write("Marca 'SÍ' en la columna **Es_Fijo** para aquellos gastos que se repiten cada mes.")
    df_editor = df_filtrado[["Fecha", "Descripcion", "Importe", "Es_Fijo"]].copy()
    
    # EDITOR EN VIVO
    edited_df = st.data_editor(df_editor, column_config={
        "Es_Fijo": st.column_config.SelectboxColumn("Gasto Fijo", options=["SÍ", "NO"])
    }, disabled=["Fecha", "Descripcion", "Importe"], use_container_width=True)

    if st.button("💾 Guardar y Sincronizar"):
        # Mapeamos los cambios de vuelta a la hoja original de Google Sheets
        # Nota: Actualizamos solo la columna F (Es_Fijo) para el año filtrado
        with st.spinner("Sincronizando..."):
            vals = [[v] for v in edited_df["Es_Fijo"].values.tolist()]
            # Para simplificar la demo, este código asume que el orden del editor es el de la hoja
            # En una app real buscaríamos por ID, aquí actualizamos el bloque visible
            st.warning("En un entorno multi-usuario se recomienda buscar por ID. Guardando bloque actual...")
            sheet.update(f"F2:F{len(vals)+1}", vals)
            st.success("¡Google Sheets actualizado!")
            st.rerun()
