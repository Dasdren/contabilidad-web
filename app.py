import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import re

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Santander AI Manager", layout="wide", page_icon="🏦")

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

# --- LIMPIADOR MANUAL DE DECIMALES (SOLUCIÓN DEFINITIVA) ---
def limpiar_importe_santander(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    
    # 1. Limpieza de texto básica
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('€', '')
    s = s.replace('−', '-') # Signo menos especial
    
    # 2. Localizar la coma decimal (formato español)
    if ',' in s:
        # Quitamos puntos de miles (ej: 1.200,50 -> 1200,50)
        partes = s.split(',')
        euros = partes[0].replace('.', '')
        centimos = partes[1]
        # Reconstruimos con punto decimal
        s = f"{euros}.{centimos}"
    
    # 3. Solo dejamos números, el punto y el signo menos
    s = "".join(c for c in s if c.isdigit() or c in '.-')
    
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

    # Columnas que tu Google Sheets DEBE tener: Fecha | Tipo | Categoria | Descripcion | Importe | Es_Fijo
    cols_necesarias = ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]
    for col in cols_necesarias:
        if col not in df.columns: df[col] = None

    if not df.empty:
        df["Importe_Num"] = df["Importe"].apply(limpiar_importe_santander)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Es_Fijo_Clean"] = df["Es_Fijo"].astype(str).str.upper().str.strip()
    else:
        df["Importe_Num"] = pd.Series(dtype=float)
        df["Fecha_DT"] = pd.to_datetime([])
        df["Es_Fijo_Clean"] = pd.Series(dtype=str)
    return df

# --- INTERFAZ ---
st.title("🏦 Santander Smart Manager")
df_hist = load_data()

t1, t2, t3, t4 = st.tabs(["📊 Dashboard", "📅 Planificador (Fijos)", "🤖 Asesor IA", "📂 Historial"])

# --- SIDEBAR: IMPORTACIÓN ---
st.sidebar.header("📥 Importar Santander")
archivo = st.sidebar.file_uploader("Sube el CSV del Santander", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar e Importar"):
        try:
            # Detectar inicio de datos
            raw_lines = archivo.getvalue().decode("utf-8").splitlines()
            skip_idx = 0
            for i, line in enumerate(raw_lines):
                if "Fecha operación" in line:
                    skip_idx = i
                    break
            
            archivo.seek(0)
            df_new = pd.read_csv(archivo, skiprows=skip_idx, dtype=str, engine='python')
            
            # 1. EQUIVALENCIAS PEDIDAS
            df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
            df_new.columns = ["Fecha", "Descripcion", "Importe"]
            
            # 2. LIMPIEZA NUMÉRICA
            df_new["Importe_Num"] = df_new["Importe"].apply(limpiar_importe_santander)
            df_new["Tipo"] = np.where(df_new["Importe_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            
            # 3. DETECCIÓN INTELIGENTE DE FIJOS (Por meses)
            df_new["Fecha_DT_Tmp"] = pd.to_datetime(df_new["Fecha"], dayfirst=True, errors='coerce')
            df_new["Mes"] = df_new["Fecha_DT_Tmp"].dt.to_period('M')
            
            # Unimos con el histórico para ver repeticiones
            if not df_hist.empty:
                full_check = pd.concat([
                    df_hist[["Descripcion", "Importe_Num", "Fecha_DT"]].rename(columns={"Fecha_DT": "Mes"}),
                    df_new[["Descripcion", "Importe_Num", "Mes"]].rename(columns={"Mes": "Mes"})
                ])
                full_check["Mes"] = pd.to_datetime(full_check["Mes"]).dt.to_period('M')
            else:
                full_check = df_new[["Descripcion", "Importe_Num", "Mes"]].copy()

            # Marcamos como fijo si Descripción + Importe aparecen en más de un mes
            frecuencia = full_check.groupby(['Descripcion', 'Importe_Num'])['Mes'].nunique().reset_index()
            fijos_detectados = frecuencia[frecuencia['Mes'] > 1]

            df_new["Es_Fijo"] = "NO"
            for _, row in fijos_detectados.iterrows():
                mask = (df_new["Descripcion"] == row["Descripcion"]) & (df_new["Importe_Num"] == row["Importe_Num"])
                df_new.loc[mask, "Es_Fijo"] = "SÍ"

            # 4. GUARDAR EN GOOGLE SHEETS
            # Guardamos el número como string con punto para GSheets
            df_new["Importe"] = df_new["Importe_Num"].astype(str)
            final_save = df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]]
            sheet.append_rows(final_save.values.tolist())
            
            st.sidebar.success(f"✅ ¡{len(df_new)} movimientos importados!")
            st.rerun()
            
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

# --- PESTAÑAS ---
with t1:
    if not df_hist.empty and df_hist["Fecha_DT"].notnull().any():
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance Total", f"{df_hist['Importe_Num'].sum():,.2f} €")
        c2.metric("Ingresos", f"{df_hist[df_hist['Importe_Num']>0]['Importe_Num'].sum():,.2f} €")
        c3.metric("Gastos", f"{df_hist[df_hist['Importe_Num']<0]['Importe_Num'].sum():,.2f} €")
        st.plotly_chart(px.line(df_hist.sort_values("Fecha_DT"), x="Fecha_DT", y="Importe_Num", color="Tipo"), use_container_width=True)

with t2:
    st.subheader("📋 Previsión de Gastos Fijos (Suelo Mensual)")
    st.info("Aquí no duplicamos. Si pagas el alquiler cada mes, aquí solo cuenta una vez para tu presupuesto mensual.")
    if not df_hist.empty:
        # Filtramos fijos y deduplicamos (Misma descripción + importe = 1 gasto mensual)
        fijos_only = df_hist[(df_hist["Es_Fijo_Clean"] == "SÍ") & (df_hist["Importe_Num"] < 0)]
        presupuesto = fijos_only.drop_duplicates(subset=['Descripcion', 'Importe_Num'], keep='last')
        
        st.metric("Total Suelo Mensual (Gastos recurrentes)", f"{presupuesto['Importe_Num'].sum():,.2f} €")
        st.dataframe(presupuesto[["Descripcion", "Importe_Num"]], use_container_width=True)

with t4:
    if not df_hist.empty:
        st.dataframe(df_hist.sort_values("Fecha_DT", ascending=False), use_container_width=True)
