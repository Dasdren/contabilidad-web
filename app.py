import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import re

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
    # Lógica decimal estricta para evitar el error -3495
    if ',' in s:
        s = s.replace('.', '') # Quitamos puntos de miles
        s = s.replace(',', '.') # Cambiamos la coma decimal por el punto de Python
    try:
        return float(s)
    except:
        return 0.0

# --- CARGA DE DATOS (PROTECCIÓN ANTI-ERRORES) ---
def load_data():
    try:
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
    except:
        df = pd.DataFrame()

    # Estructura interna necesaria
    columnas_finales = ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]
    for col in columnas_finales:
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

# --- SIDEBAR: IMPORTACIÓN ESPECÍFICA SANTANDER ---
st.sidebar.header("📥 Importar CSV Santander")
archivo = st.sidebar.file_uploader("Sube el CSV descargado del banco", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar e Importar"):
        try:
            # Buscamos la fila donde empiezan los datos reales
            raw_content = archivo.getvalue().decode("utf-8").splitlines()
            start_row = 0
            for i, line in enumerate(raw_content):
                if "Fecha operación" in line:
                    start_row = i
                    break
            
            archivo.seek(0)
            df_new = pd.read_csv(archivo, skiprows=start_row, dtype=str)
            
            # 1. EQUIVALENCIAS: Solo Fecha operación, Concepto e Importe
            df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
            df_new = df_new.rename(columns={
                'Fecha operación': 'Fecha',
                'Concepto': 'Descripcion'
            })

            # 2. PROCESAMIENTO NUMÉRICO
            df_new["Importe_Num"] = df_new["Importe"].apply(limpiar_importe_santander)
            df_new["Tipo"] = np.where(df_new["Importe_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            
            # 3. DETECCIÓN AUTOMÁTICA DE FIJOS (REPETICIÓN MES A MES)
            df_new['Fecha_DT_Tmp'] = pd.to_datetime(df_new['Fecha'], dayfirst=True, errors='coerce')
            df_new['Mes'] = df_new['Fecha_DT_Tmp'].dt.to_period('M')
            
            # Unimos con el histórico para ver si se repiten en meses distintos
            if not df_hist.empty:
                df_hist_tmp = df_hist.copy()
                df_hist_tmp['Mes'] = pd.to_datetime(df_hist_tmp['Fecha'], dayfirst=True, errors='coerce').dt.to_period('M')
                full_check = pd.concat([
                    df_hist_tmp[["Descripcion", "Importe_Num", "Mes"]],
                    df_new[["Descripcion", "Importe_Num", "Mes"]]
                ])
            else:
                full_check = df_new[["Descripcion", "Importe_Num", "Mes"]].copy()

            # Marcamos como fijo si misma descripción e importe aparecen en >1 mes distinto
            frecuencia = full_check.groupby(['Descripcion', 'Importe_Num'])['Mes'].nunique().reset_index()
            fijos_list = frecuencia[frecuencia['Mes'] > 1]
            
            df_new["Es_Fijo"] = "NO"
            for _, row in fijos_list.iterrows():
                mask = (df_new["Descripcion"] == row["Descripcion"]) & (df_new["Importe_Num"] == row["Importe_Num"])
                df_new.loc[mask, "Es_Fijo"] = "SÍ"

            # 4. GUARDAR EN GOOGLE SHEETS
            # Convertimos el número a string con punto decimal para que Sheets no se líe
            df_new["Importe_Final"] = df_new["Importe_Num"].astype(str)
            final_save = df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe_Final", "Es_Fijo"]]
            sheet.append_rows(final_save.values.tolist())
            
            st.sidebar.success(f"✅ ¡{len(df_new)} movimientos importados!")
            st.rerun()
            
        except Exception as e:
            st.sidebar.error(f"Error procesando el CSV: {e}")

# --- PESTAÑAS ---
with t1:
    if not df_hist.empty and df_hist["Fecha_DT"].notnull().any():
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance Total", f"{df_hist['Importe_Num'].sum():,.2f} €")
        c2.metric("Ingresos", f"{df_hist[df_hist['Importe_Num']>0]['Importe_Num'].sum():,.2f} €")
        c3.metric("Gastos", f"{df_hist[df_hist['Importe_Num']<0]['Importe_Num'].sum():,.2f} €")
        st.plotly_chart(px.line(df_hist.sort_values("Fecha_DT"), x="Fecha_DT", y="Importe_Num", color="Tipo"), use_container_width=True)

with t2:
    st.subheader("📋 Planificador Mensual (Gastos Fijos)")
    st.info("Aquí cada gasto fijo solo cuenta una vez para tu previsión mensual.")
    if not df_hist.empty:
        fijos_only = df_hist[(df_hist["Es_Fijo_Clean"] == "SÍ") & (df_hist["Importe_Num"] < 0)]
        # DEDUPLICAR: Solo nos importa el concepto y el importe una vez para el presupuesto
        presupuesto = fijos_only.drop_duplicates(subset=['Descripcion', 'Importe_Num'], keep='last')
        st.metric("Total Suelo Mensual (Previsión)", f"{presupuesto['Importe_Num'].sum():,.2f} €")
        st.dataframe(presupuesto[["Descripcion", "Importe_Num"]], use_container_width=True)

with t4:
    if not df_hist.empty:
        st.dataframe(df_hist.sort_values("Fecha_DT", ascending=False), use_container_width=True)
