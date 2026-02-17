import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import numpy as np
import re
import google.generativeai as genai
from sklearn.linear_model import LinearRegression

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Santander IA Manager", layout="wide", page_icon="🏦")

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
        st.error(f"⚠️ Error Sheets: {e}")
        st.stop()

sheet = conectar_google_sheets()

# --- CONEXIÓN GEMINI AI ---
def consultar_gemini(resumen_texto):
    try:
        api_key = st.secrets["gemini_api_key"]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"Actúa como asesor financiero. Analiza estos movimientos del Santander: {resumen_texto}. Dame 3 consejos breves de ahorro. Habla de tú."
        response = model.generate_content(prompt)
        return response.text
    except:
        return "IA ocupada. Prueba en unos minutos."

# --- LIMPIEZA ESPECÍFICA SANTANDER ---
def limpiar_monto_santander(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip()
    # Santander usa '−' (Unicode U+2212), lo cambiamos al '-' normal
    s = s.replace('−', '-').replace('"', '')
    # Quitar puntos de miles y cambiar coma por punto
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

# --- CARGA Y PROCESAMIENTO ---
def load_data():
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    cols = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
    for c in cols: 
        if c not in df.columns: df[c] = ""
    if not df.empty:
        df["Monto_Num"] = df["Monto"].apply(limpiar_monto_santander)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Es_Fijo_Clean"] = df["Es_Fijo"].astype(str).str.upper()
    return df

# --- INTERFAZ ---
df = load_data()
st.title("🏦 Santander Smart Finance")

t1, t2, t3, t4 = st.tabs(["📊 Balance", "📅 Planificador (Fijos)", "🤖 Asesor IA", "📂 Historial"])

# --- SIDEBAR: IMPORTADOR INTELIGENTE ---
st.sidebar.header("📥 Importar Santander")
archivo = st.sidebar.file_uploader("Sube tu CSV del Santander", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar Movimientos"):
        try:
            # Saltamos la cabecera del banco buscando 'Fecha operación'
            raw_lines = archivo.getvalue().decode("utf-8").splitlines()
            skip_n = 0
            for i, line in enumerate(raw_lines):
                if "Fecha operación" in line:
                    skip_n = i
                    break
            archivo.seek(0)
            new_data = pd.read_csv(archivo, skiprows=skip_n)
            
            # Mapeo de columnas Santander -> Nuestra App
            new_data = new_data.rename(columns={'Fecha operación': 'Fecha', 'Concepto': 'Descripcion', 'Importe': 'Monto'})
            new_data["Monto_Num"] = new_data["Monto"].apply(limpiar_monto_santander)
            new_data["Tipo"] = np.where(new_data["Monto_Num"] < 0, "Gasto", "Ingreso")
            new_data["Categoria"] = "Varios"
            
            # --- LÓGICA DE DETECCIÓN DE FIJOS ---
            new_data['Fecha_DT'] = pd.to_datetime(new_data['Fecha'], dayfirst=True)
            new_data['Mes'] = new_data['Fecha_DT'].dt.to_period('M')
            
            # Agrupamos por descripción e importe para ver si se repiten en meses distintos
            fijos_detectados = new_data.groupby(['Descripcion', 'Monto_Num'])['Mes'].nunique().reset_index()
            fijos_list = fijos_detectados[fijos_detectados['Mes'] > 1]
            
            new_data["Es_Fijo"] = "NO"
            for _, row in fijos_list.iterrows():
                mask = (new_data['Descripcion'] == row['Descripcion']) & (new_data['Monto_Num'] == row['Monto_Num'])
                new_data.loc[mask, "Es_Fijo"] = "SÍ"
            
            # Guardar en Google Sheets
            final_to_save = new_data[["Fecha", "Tipo", "Categoria", "Descripcion", "Monto_Num", "Es_Fijo"]]
            sheet.append_rows(final_to_save.values.tolist())
            st.sidebar.success("¡Importación completada!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error al leer CSV: {e}")

# --- PESTAÑAS ---
with t1:
    if not df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Saldo Actual", f"{df['Monto_Num'].sum():,.2f} €")
        col2.metric("Ingresos", f"{df[df['Monto_Num']>0]['Monto_Num'].sum():,.2f} €")
        col3.metric("Gastos", f"{df[df['Monto_Num']<0]['Monto_Num'].sum():,.2f} €", delta_color="inverse")
        
        fig = px.line(df.sort_values("Fecha_DT"), x="Fecha_DT", y="Monto_Num", color="Tipo", title="Flujo de Caja")
        st.plotly_chart(fig, use_container_width=True)

with t2:
    st.subheader("🔮 Gastos Fijos (Presupuesto Mensual)")
    st.write("Esta lista muestra tus gastos fijos recurrentes sin duplicarlos históricamente.")
    if not df.empty:
        # Filtramos fijos y eliminamos duplicados para el cálculo mensual
        fijos_only = df[(df["Es_Fijo_Clean"] == "SÍ") & (df["Monto_Num"] < 0)]
        presupuesto = fijos_only.drop_duplicates(subset=['Descripcion', 'Monto_Num'], keep='last')
        
        total_fijo = presupuesto["Monto_Num"].sum()
        st.metric("Total Fijo Mensual", f"{total_fijo:,.2f} €")
        st.table(presupuesto[["Categoria", "Descripcion", "Monto"]])

with t3:
    st.header("🤖 Asesoría Personalizada")
    if st.button("Analizar con Gemini"):
        resumen = f"Balance: {df['Monto_Num'].sum()}€. Gastos: {df[df['Monto_Num']<0]['Monto_Num'].sum()}€."
        st.write(consultar_gemini(resumen))

with t4:
    st.dataframe(df.sort_values("Fecha_DT", ascending=False), use_container_width=True)
