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
        prompt = f"Asesor financiero. Analiza estos movimientos: {resumen_texto}. Dame 3 consejos de ahorro. Habla de tú."
        response = model.generate_content(prompt)
        return response.text
    except:
        return "IA ocupada. Revisa tu API Key en los Secrets."

# --- LIMPIEZA ESPECÍFICA SANTANDER ---
def limpiar_monto_santander(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip()
    # Santander usa '−' (Unicode U+2212)
    s = s.replace('−', '-').replace('"', '').replace(' EUR', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

# --- CARGA Y PROCESAMIENTO ---
def load_data():
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    
    # Columnas base que SIEMPRE deben existir para evitar KeyErrors
    cols = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
    for c in cols: 
        if c not in df.columns: df[c] = ""
    
    # Procesamos si hay datos reales
    if not df.empty and len(df) > 0:
        df["Monto_Num"] = df["Monto"].apply(limpiar_monto_santander)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Es_Fijo_Clean"] = df["Es_Fijo"].astype(str).str.upper()
    else:
        # Estructura mínima para evitar que la app explote si está vacía
        df["Monto_Num"] = 0.0
        df["Fecha_DT"] = pd.NaT
        df["Es_Fijo_Clean"] = "NO"
        
    return df

# --- INTERFAZ ---
df = load_data()
st.title("🏦 Santander Smart Finance")

t1, t2, t3, t4 = st.tabs(["📊 Balance", "📅 Planificador (Fijos)", "🤖 Asesor IA", "📂 Historial"])

# --- SIDEBAR: IMPORTADOR ---
st.sidebar.header("📥 Importar Santander")
archivo = st.sidebar.file_uploader("Sube tu CSV del Santander", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar Movimientos"):
        try:
            raw_lines = archivo.getvalue().decode("utf-8").splitlines()
            skip_n = 0
            for i, line in enumerate(raw_lines):
                if "Fecha operación" in line:
                    skip_n = i
                    break
            archivo.seek(0)
            new_data = pd.read_csv(archivo, skiprows=skip_n)
            
            # Mapeo Santander -> App
            new_data = new_data.rename(columns={'Fecha operación': 'Fecha', 'Concepto': 'Descripcion', 'Importe': 'Monto'})
            new_data["Monto_Num"] = new_data["Monto"].apply(limpiar_monto_santander)
            new_data["Tipo"] = np.where(new_data["Monto_Num"] < 0, "Gasto", "Ingreso")
            new_data["Categoria"] = "Varios"
            
            # --- DETECCIÓN AUTOMÁTICA DE FIJOS ---
            new_data['Fecha_DT_Temp'] = pd.to_datetime(new_data['Fecha'], dayfirst=True)
            new_data['Mes_Temp'] = new_data['Fecha_DT_Temp'].dt.to_period('M')
            
            # Identificamos fijos: misma descripción e importe en meses diferentes
            frecuencia = new_data.groupby(['Descripcion', 'Monto_Num'])['Mes_Temp'].nunique().reset_index()
            fijos_list = frecuencia[frecuencia['Mes_Temp'] > 1]
            
            new_data["Es_Fijo"] = "NO"
            for _, row in fijos_list.iterrows():
                mask = (new_data['Descripcion'] == row['Descripcion']) & (new_data['Monto_Num'] == row['Monto_Num'])
                new_data.loc[mask, "Es_Fijo"] = "SÍ"
            
            # Limpiar columnas temporales antes de subir
            final_to_save = new_data[["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]]
            
            sheet.append_rows(final_to_save.values.tolist())
            st.sidebar.success("¡Importado correctamente!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error procesando el CSV: {e}")

# --- PESTAÑAS ---
with t1:
    if not df.empty and df["Fecha_DT"].notnull().any():
        c1, c2, c3 = st.columns(3)
        c1.metric("Saldo Acumulado", f"{df['Monto_Num'].sum():,.2f} €")
        c2.metric("Ingresos", f"{df[df['Monto_Num']>0]['Monto_Num'].sum():,.2f} €")
        c3.metric("Gastos", f"{df[df['Monto_Num']<0]['Monto_Num'].sum():,.2f} €", delta_color="inverse")
        
        fig = px.line(df.dropna(subset=['Fecha_DT']).sort_values("Fecha_DT"), x="Fecha_DT", y="Monto_Num", color="Tipo")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sube tu primer CSV del Santander para activar el Dashboard.")

with t2:
    st.subheader("🔮 Gastos Fijos (Presupuesto Mensual)")
    st.info("Aquí solo se cuenta cada gasto fijo UNA VEZ para calcular tu coste de vida mensual real.")
    if not df.empty and "Es_Fijo_Clean" in df.columns:
        fijos_only = df[(df["Es_Fijo_Clean"] == "SÍ") & (df["Monto_Num"] < 0)]
        
        # LOGICA ANTI-DUPLICADOS: Agrupamos por descripción e importe
        presupuesto = fijos_only.drop_duplicates(subset=['Descripcion', 'Monto_Num'], keep='last')
        
        st.metric("Tu Suelo de Gastos Mensual", f"{presupuesto['Monto_Num'].sum():,.2f} €")
        st.table(presupuesto[["Fecha", "Descripcion", "Monto"]])
    else:
        st.write("No hay gastos fijos detectados.")

with t3:
    st.header("🤖 Asesoría IA")
    if st.button("Analizar mis finanzas"):
        resumen = f"Balance: {df['Monto_Num'].sum()}€. Gastos fijos detectados: {len(df[df['Es_Fijo_Clean']=='SÍ'])} movimientos."
        st.write(consultar_gemini(resumen))

with t4:
    if not df.empty and "Fecha_DT" in df.columns:
        st.dataframe(df.sort_values("Fecha_DT", ascending=False, na_position='last'), use_container_width=True)
