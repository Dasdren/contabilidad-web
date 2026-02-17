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

# --- CONFIGURACIÓN DE PÁGINA ---
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
        prompt = f"Asesor financiero. Analiza estos movimientos: {resumen_texto}. Dame 3 consejos de ahorro. Habla de tú."
        response = model.generate_content(prompt)
        return response.text
    except:
        return "IA ocupada. Revisa tu API Key en los Secrets."

# --- LIMPIEZA ESPECÍFICA SANTANDER ---
def limpiar_monto_santander(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip()
    # Santander usa '−' (Unicode U+2212) en lugar del guion normal
    s = s.replace('−', '-').replace('"', '').replace(' EUR', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

# --- CARGA Y PROCESAMIENTO ---
def load_data():
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
    except:
        df = pd.DataFrame()
    
    # Columnas base obligatorias
    cols = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
    for c in cols: 
        if c not in df.columns: df[c] = ""
    
    # Si hay datos, procesamos. Si no, creamos estructura vacía para evitar errores
    if not df.empty and len(df) > 0:
        df["Monto_Num"] = df["Monto"].apply(limpiar_monto_santander)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Es_Fijo_Clean"] = df["Es_Fijo"].astype(str).str.upper()
    else:
        df["Monto_Num"] = 0.0
        df["Fecha_DT"] = pd.NaT
        df["Es_Fijo_Clean"] = "NO"
        
    return df

# --- INTERFAZ ---
df = load_data()
st.title("🏦 Santander Smart Finance + IA")

t1, t2, t3, t4 = st.tabs(["📊 Balance Histórico", "📅 Planificador (Fijos)", "🤖 Asesor IA", "📂 Historial Completo"])

# --- SIDEBAR: IMPORTADOR SANTANDER ---
st.sidebar.header("📥 Importar Santander")
archivo = st.sidebar.file_uploader("Sube tu CSV del Santander", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar Santander"):
        try:
            # Buscamos la fila donde empieza el contenido real
            raw_lines = archivo.getvalue().decode("utf-8").splitlines()
            skip_n = 0
            for i, line in enumerate(raw_lines):
                if "Fecha operación" in line:
                    skip_n = i
                    break
            archivo.seek(0)
            new_data = pd.read_csv(archivo, skiprows=skip_n)
            
            # Renombrar columnas Santander a nuestro formato
            new_data = new_data.rename(columns={
                'Fecha operación': 'Fecha', 
                'Concepto': 'Descripcion', 
                'Importe': 'Monto'
            })
            
            # Limpieza básica
            new_data["Monto_Num"] = new_data["Monto"].apply(limpiar_monto_santander)
            new_data["Tipo"] = np.where(new_data["Monto_Num"] < 0, "Gasto", "Ingreso")
            new_data["Categoria"] = "Varios"
            
            # --- LÓGICA DE DETECCIÓN DE FIJOS ---
            new_data['Fecha_DT_Tmp'] = pd.to_datetime(new_data['Fecha'], dayfirst=True)
            new_data['Mes_Tmp'] = new_data['Fecha_DT_Tmp'].dt.to_period('M')
            
            # Marcamos como fijo si misma descripción e importe aparecen en meses distintos
            frecuencia = new_data.groupby(['Descripcion', 'Monto_Num'])['Mes_Tmp'].nunique().reset_index()
            fijos_list = frecuencia[frecuencia['Mes_Tmp'] > 1]
            
            new_data["Es_Fijo"] = "NO"
            for _, row in fijos_list.iterrows():
                mask = (new_data['Descripcion'] == row['Descripcion']) & (new_data['Monto_Num'] == row['Monto_Num'])
                new_data.loc[mask, "Es_Fijo"] = "SÍ"
            
            # Guardar en Google Sheets
            final_to_save = new_data[["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]]
            sheet.append_rows(final_to_save.values.tolist())
            
            st.sidebar.success("¡Importado! Recargando...")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error procesando: {e}")

# --- PESTAÑAS ---
with t1:
    if not df.empty and df["Fecha_DT"].notnull().any():
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance Total", f"{df['Monto_Num'].sum():,.2f} €")
        c2.metric("Ingresos", f"{df[df['Monto_Num']>0]['Monto_Num'].sum():,.2f} €")
        c3.metric("Gastos", f"{df[df['Monto_Num']<0]['Monto_Num'].sum():,.2f} €", delta_color="inverse")
        
        fig = px.line(df.dropna(subset=['Fecha_DT']).sort_values("Fecha_DT"), x="Fecha_DT", y="Monto_Num", color="Tipo")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sube tu primer archivo CSV del Santander para activar los gráficos.")

with t2:
    st.header("📋 Coste de Vida Mensual (Gastos Fijos)")
    st.info("Aquí no duplicamos: si pagas el alquiler todos los meses, solo se cuenta una vez para tu presupuesto mensual.")
    if not df.empty:
        # Filtramos gastos fijos
        fijos = df[(df["Es_Fijo_Clean"] == "SÍ") & (df["Monto_Num"] < 0)]
        
        # ELIMINAR DUPLICADOS: Solo nos importa el concepto y el importe una vez
        presupuesto = fijos.drop_duplicates(subset=['Descripcion', 'Monto_Num'], keep='last')
        
        st.metric("Total Gastos Fijos (Al mes)", f"{presupuesto['Monto_Num'].sum():,.2f} €")
        st.dataframe(presupuesto[["Categoria", "Descripcion", "Monto"]], use_container_width=True)
    else:
        st.write("No hay gastos fijos detectados.")

with t3:
    st.header("🤖 Consultor IA Gemini")
    if st.button("✨ Analizar mis movimientos"):
        if not df.empty:
            resumen = f"Saldo: {df['Monto_Num'].sum()}€. Gastos: {df[df['Monto_Num']<0]['Monto_Num'].sum()}€."
            st.write(consultar_gemini(resumen))

with t4:
    if not df.empty and "Fecha_DT" in df.columns:
        # Ordenamos por fecha real (Fecha_DT) para que el historial tenga sentido
        st.dataframe(df.sort_values("Fecha_DT", ascending=False, na_position='last'), use_container_width=True)
