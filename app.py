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
st.set_page_config(page_title="Santander Smart Manager", layout="wide", page_icon="🏦")

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
        st.error("⚠️ Error de conexión. Revisa tus Secrets.")
        st.stop()

sheet = conectar_google_sheets()

# --- LIMPIEZA DE IMPORTES (SANTANDER) ---
def limpiar_importe_santander(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip().replace('"', '')
    # Traducimos el menos especial del Santander (−) a guion normal (-)
    s = s.replace('−', '-')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except:
        return 0.0

# --- CARGA DE DATOS ---
def load_data():
    try:
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
    except:
        df = pd.DataFrame()

    # Columnas que nuestra base de datos interna espera (Asegúrate que en Google Sheets sea 'Importe')
    columnas_finales = ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]
    
    for col in columnas_finales:
        if col not in df.columns:
            df[col] = None

    if not df.empty:
        df["Importe_Num"] = pd.to_numeric(df["Importe"].apply(limpiar_importe_santander), errors='coerce').fillna(0.0)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Es_Fijo_Clean"] = df["Es_Fijo"].astype(str).str.upper().fillna("NO")
    else:
        df["Importe_Num"] = pd.Series(dtype=float)
        df["Fecha_DT"] = pd.to_datetime([])
        df["Es_Fijo_Clean"] = pd.Series(dtype=str)

    return df

# --- INTERFAZ ---
st.title("🏦 Santander Smart Manager")
df = load_data()

t1, t2, t3, t4 = st.tabs(["📊 Dashboard", "📅 Planificador (Fijos)", "🤖 Asesor IA", "📂 Historial"])

# --- SIDEBAR: IMPORTACIÓN ROBUSTA SANTANDER ---
st.sidebar.header("📥 Importar CSV Santander")
archivo = st.sidebar.file_uploader("Sube el CSV descargado del banco", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar e Importar"):
        try:
            # 1. LEER ARCHIVO Y BUSCAR CABECERA
            raw_content = archivo.getvalue().decode("utf-8").splitlines()
            header_row = -1
            sep_detectado = ","
            
            for i, line in enumerate(raw_content):
                if "Fecha operación" in line:
                    header_row = i
                    # Detectar si el separador es coma o punto y coma
                    if ";" in line: sep_detectado = ";"
                    break
            
            if header_row == -1:
                st.sidebar.error("No se encontró la fila 'Fecha operación'. ¿Es el archivo correcto?")
                st.stop()
            
            # 2. LEER CON EL SEPARADOR DETECTADO
            archivo.seek(0)
            df_new = pd.read_csv(archivo, skiprows=header_row, sep=sep_detectado, engine='python')
            
            # 3. LIMPIEZA RADICAL DE NOMBRES DE COLUMNAS
            # Quitamos espacios, comillas y caracteres invisibles
            df_new.columns = df_new.columns.str.strip().str.replace('"', '').str.replace('\'', '')
            
            # 4. FILTRADO Y RENOMBRADO
            # Usamos lógica flexible por si el nombre varía mínimamente
            col_fecha = [c for c in df_new.columns if "Fecha operación" in c][0]
            col_concepto = [c for c in df_new.columns if "Concepto" in c][0]
            col_importe = [c for c in df_new.columns if "Importe" in c][0]
            
            df_new = df_new[[col_fecha, col_concepto, col_importe]].copy()
            df_new.columns = ["Fecha", "Descripcion", "Importe"]

            # 5. PROCESAMIENTO
            df_new["Importe_Num"] = df_new["Importe"].apply(limpiar_importe_santander)
            df_new["Tipo"] = np.where(df_new["Importe_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            
            # DETECCIÓN DE FIJOS
            df_new['Fecha_DT_Tmp'] = pd.to_datetime(df_new['Fecha'], dayfirst=True, errors='coerce')
            df_new['Mes_Año'] = df_new['Fecha_DT_Tmp'].dt.strftime('%Y-%m')
            
            frecuencia = df_new.groupby(['Descripcion', 'Importe_Num'])['Mes_Año'].nunique().reset_index()
            fijos_list = frecuencia[frecuencia['Mes_Año'] > 1]
            
            df_new["Es_Fijo"] = "NO"
            for _, row in fijos_list.iterrows():
                mask = (df_new['Descripcion'] == row['Descripcion']) & (df_new['Importe_Num'] == row['Monto_Num'] if 'Monto_Num' in row else df_new['Importe_Num'] == row['Importe_Num'])
                df_new.loc[mask, "Es_Fijo"] = "SÍ"

            # 6. GUARDAR
            final_save = df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]]
            sheet.append_rows(final_save.values.tolist())
            
            st.sidebar.success("✅ Importado con éxito")
            st.rerun()
            
        except Exception as e:
            st.sidebar.error(f"Error procesando el CSV: {e}")

# --- PESTAÑAS (Mantenemos la lógica de visualización) ---
with t1:
    if not df.empty and df["Fecha_DT"].notnull().any():
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance Neto", f"{df['Importe_Num'].sum():,.2f} €")
        c2.metric("Ingresos", f"{df[df['Importe_Num']>0]['Importe_Num'].sum():,.2f} €")
        c3.metric("Gastos", f"{df[df['Importe_Num']<0]['Importe_Num'].sum():,.2f} €")
        st.plotly_chart(px.line(df.dropna(subset=['Fecha_DT']).sort_values("Fecha_DT"), x="Fecha_DT", y="Importe_Num", color="Tipo"), use_container_width=True)

with t2:
    if not df.empty:
        fijos_only = df[(df["Es_Fijo_Clean"] == "SÍ") & (df["Importe_Num"] < 0)]
        presupuesto = fijos_only.drop_duplicates(subset=['Descripcion', 'Importe_Num'], keep='last')
        st.metric("Suelo Mensual", f"{presupuesto['Importe_Num'].sum():,.2f} €")
        st.dataframe(presupuesto[["Fecha", "Descripcion", "Importe"]], use_container_width=True)

with t4:
    if not df.empty:
        st.dataframe(df.sort_values("Fecha_DT", ascending=False, na_position='last'), use_container_width=True)
