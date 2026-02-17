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
        st.error("⚠️ Error de conexión con Google Sheets.")
        st.stop()

sheet = conectar_google_sheets()

# --- LIMPIADOR DE DECIMALES (RESUELTO ANTERIORMENTE) ---
def limpiar_importe_santander(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('€', '')
    s = s.replace('−', '-') # Signo menos Santander
    if ',' in s:
        s = s.replace('.', '') # Quitar miles
        s = s.replace(',', '.') # Coma a punto
    s = "".join(c for c in s if c.isdigit() or c in '.-')
    try: return float(s)
    except: return 0.0

# --- CARGA DE DATOS ---
def load_data():
    try:
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
    except:
        df = pd.DataFrame()

    # Columnas exactas de tu Excel del proyecto
    cols_excel = ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]
    for col in cols_excel:
        if col not in df.columns: df[col] = None

    if not df.empty:
        df["Importe_Num"] = df["Importe"].apply(limpiar_importe_santander)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Es_Fijo_Status"] = df["Es_Fijo"].astype(str).str.upper().str.strip()
    else:
        df["Importe_Num"] = pd.Series(dtype=float)
        df["Fecha_DT"] = pd.to_datetime([])
        df["Es_Fijo_Status"] = pd.Series(dtype=str)
    return df

# --- INTERFAZ ---
st.title("🏦 Santander Smart Finance")
df_hist = load_data()

t1, t2, t3, t4 = st.tabs(["📊 Dashboard", "📅 Planificador (Fijos)", "🤖 Asesor IA", "📂 Historial"])

# --- SIDEBAR: IMPORTACIÓN INTELIGENTE ---
st.sidebar.header("📥 Importar Santander")
archivo = st.sidebar.file_uploader("Sube el CSV del Santander", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar e Importar"):
        try:
            # 1. RASTREAR LA FILA DE CABECERA Y EL SEPARADOR
            raw_lines = archivo.getvalue().decode("utf-8").splitlines()
            header_idx = -1
            separador = "," # Por defecto
            
            for i, line in enumerate(raw_lines):
                if "Fecha operación" in line:
                    header_idx = i
                    if ";" in line: separador = ";"
                    break
            
            if header_idx == -1:
                st.sidebar.error("❌ No se encontró la columna 'Fecha operación'. Revisa el archivo.")
                st.stop()
            
            # 2. LEER DESDE LA FILA ENCONTRADA
            archivo.seek(0)
            df_new = pd.read_csv(archivo, skiprows=header_idx, sep=separador, dtype=str, engine='python')
            
            # Limpiar posibles espacios en los nombres de columnas
            df_new.columns = df_new.columns.str.strip()
            
            # 3. APLICAR EQUIVALENCIAS
            # Fecha operación -> Fecha | Concepto -> Descripcion | Importe -> Importe
            # Ignoramos: Fecha valor, Saldo, Divisa
            df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
            df_new.columns = ["Fecha", "Descripcion", "Importe"]
            
            # 4. PROCESAMIENTO Y LIMPIEZA
            df_new["Importe_Num"] = df_new["Importe"].apply(limpiar_importe_santander)
            df_new["Tipo"] = np.where(df_new["Importe_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            
            # 5. LÓGICA DE GASTOS FIJOS (REPETICIÓN)
            df_new["Fecha_DT_Tmp"] = pd.to_datetime(df_new["Fecha"], dayfirst=True, errors='coerce')
            df_new["Mes"] = df_new["Fecha_DT_Tmp"].dt.to_period('M')
            
            # Combinamos con histórico para detectar si se repite en meses distintos
            if not df_hist.empty:
                full_check = pd.concat([
                    df_hist[["Descripcion", "Importe_Num", "Fecha_DT"]].rename(columns={"Fecha_DT": "Mes"}),
                    df_new[["Descripcion", "Importe_Num", "Mes"]].rename(columns={"Mes": "Mes"})
                ])
                full_check["Mes"] = pd.to_datetime(full_check["Mes"]).dt.to_period('M')
            else:
                full_check = df_new[["Descripcion", "Importe_Num", "Mes"]].copy()

            # Marcamos "SÍ" si Descripción + Importe aparecen en más de 1 mes
            frecuencia = full_check.groupby(['Descripcion', 'Importe_Num'])['Mes'].nunique().reset_index()
            fijos_ids = frecuencia[frecuencia['Mes'] > 1]

            df_new["Es_Fijo"] = "NO"
            for _, row in fijos_ids.iterrows():
                mask = (df_new["Descripcion"] == row["Descripcion"]) & (df_new["Importe_Num"] == row["Importe_Num"])
                df_new.loc[mask, "Es_Fijo"] = "SÍ"

            # 6. GUARDAR EN GOOGLE SHEETS
            # Convertimos el número a string para evitar líos de formato en la celda
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
        st.plotly_chart(px.line(df_hist.dropna(subset=['Fecha_DT']).sort_values("Fecha_DT"), x="Fecha_DT", y="Importe_Num", color="Tipo"), use_container_width=True)

with t2:
    st.subheader("📋 Planificador Mensual (Sin Duplicados)")
    st.info("Aquí solo se cuenta cada gasto fijo una vez para saber tu 'suelo' de gastos al mes.")
    if not df_hist.empty:
        # Filtramos fijos y deduplicamos (Misma descripción + importe = 1 gasto mensual)
        fijos_only = df_hist[(df_hist["Es_Fijo_Status"] == "SÍ") & (df_hist["Importe_Num"] < 0)]
        presupuesto = fijos_only.drop_duplicates(subset=['Descripcion', 'Importe_Num'], keep='last')
        
        st.metric("Total Suelo Mensual", f"{presupuesto['Importe_Num'].sum():,.2f} €")
        st.dataframe(presupuesto[["Descripcion", "Importe_Num"]], use_container_width=True)

with t4:
    if not df_hist.empty:
        st.dataframe(df_hist.sort_values("Fecha_DT", ascending=False), use_container_width=True)
