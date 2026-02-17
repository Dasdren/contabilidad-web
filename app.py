import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import re

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Gestor Santander Pro", layout="wide", page_icon="🏦")

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

# --- EL LIMPIADOR QUIRÚRGICO (Solución al 34,95) ---
def limpiar_importe_santander(valor):
    if pd.isna(valor) or str(valor).strip() == "":
        return 0.0
    
    # 1. Convertir a texto y quitar comillas/espacios
    s = str(valor).strip().replace('"', '').replace(' EUR', '')
    
    # 2. Corregir el signo menos especial del Santander (−)
    s = s.replace('−', '-')
    
    # 3. Lógica Decimal: "1.200,34" -> "1200.34"
    if ',' in s:
        s = s.replace('.', '') # Quitar punto de miles
        s = s.replace(',', '.') # Cambiar coma por punto decimal
    
    # 4. Limpieza final: quitar todo lo que no sea número, punto o signo menos
    s = re.sub(r'[^\d.-]', '', s)
    
    try:
        return float(s)
    except:
        return 0.0

def load_data():
    try:
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
    except:
        df = pd.DataFrame()
    
    # Garantizar columnas
    cols = ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]
    for c in cols:
        if c not in df.columns: df[c] = ""
    
    if not df.empty:
        df["Importe_Num"] = df["Importe"].apply(limpiar_importe_santander)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Es_Fijo_Clean"] = df["Es_Fijo"].astype(str).str.upper().str.strip()
    return df

# --- INTERFAZ ---
st.title("🏦 Gestor Santander Inteligente")
df_hist = load_data()

t1, t2, t3, t4 = st.tabs(["📊 Dashboard", "📅 Planificador (Fijos)", "🤖 Asesor IA", "📂 Historial"])

# --- SIDEBAR: IMPORTACIÓN ---
st.sidebar.header("📥 Importar Santander")
archivo = st.sidebar.file_uploader("Sube el CSV", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar e Importar"):
        try:
            # Leer saltando cabecera del banco
            raw = archivo.getvalue().decode("utf-8").splitlines()
            skip = 0
            for i, line in enumerate(raw):
                if "Fecha operación" in line:
                    skip = i
                    break
            
            archivo.seek(0)
            df_new = pd.read_csv(archivo, skiprows=skip, dtype=str)
            
            # Mapeo Santander
            df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
            df_new.columns = ["Fecha", "Descripcion", "Importe"]
            
            # Limpieza Numérica
            df_new["Importe_Num"] = df_new["Importe"].apply(limpiar_importe_santander)
            df_new["Tipo"] = np.where(df_new["Importe_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            
            # --- IA DE GASTOS FIJOS ---
            # Identificamos si se repite concepto e importe en meses distintos
            df_new['Fecha_DT_Tmp'] = pd.to_datetime(df_new['Fecha'], dayfirst=True, errors='coerce')
            df_new['Mes'] = df_new['Fecha_DT_Tmp'].dt.to_period('M')
            
            # Unimos con histórico para detectar recurrencia
            full_check = pd.concat([df_hist[['Descripcion', 'Importe_Num']], df_new[['Descripcion', 'Importe_Num']]])
            # (Simplificado: marcamos como fijo si hay más de 1 ocurrencia de ese importe y concepto)
            # En una app real compararíamos meses, aquí lo haremos por frecuencia para ser directos
            counts = full_check.groupby(['Descripcion', 'Importe_Num']).size().reset_index(name='f')
            fijos_ids = counts[counts['f'] > 1]

            df_new["Es_Fijo"] = "NO"
            for _, row in fijos_ids.iterrows():
                mask = (df_new["Descripcion"] == row["Descripcion"]) & (df_new["Importe_Num"] == row["Importe_Num"])
                df_new.loc[mask, "Es_Fijo"] = "SÍ"

            # Guardar (Convertimos el número a texto con punto para GSheets)
            df_new["Importe"] = df_new["Importe_Num"].astype(str)
            final_rows = df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]]
            sheet.append_rows(final_rows.values.tolist())
            
            st.sidebar.success("✅ Importación exitosa")
            st.rerun()
            
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

# --- PESTAÑAS ---
with t1:
    if not df_hist.empty and df_hist["Fecha_DT"].notnull().any():
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance", f"{df_hist['Importe_Num'].sum():,.2f} €")
        c2.metric("Ingresos", f"{df_hist[df_hist['Importe_Num']>0]['Importe_Num'].sum():,.2f} €")
        c3.metric("Gastos", f"{df_hist[df_hist['Importe_Num']<0]['Importe_Num'].sum():,.2f} €")
        
        st.plotly_chart(px.line(df_hist.sort_values("Fecha_DT"), x="Fecha_DT", y="Importe_Num", color="Tipo"), use_container_width=True)

with t2:
    st.subheader("📋 Presupuesto Mensual de Gastos Fijos")
    st.info("Aquí no se duplican los recibos. Solo ves cuánto te cuesta la vida cada mes.")
    if not df_hist.empty:
        # Filtramos fijos y eliminamos duplicados (Misma descripción + importe = 1 solo gasto mensual)
        fijos = df_hist[(df_hist["Es_Fijo_Clean"] == "SÍ") & (df_hist["Importe_Num"] < 0)]
        presupuesto = fijos.drop_duplicates(subset=['Descripcion', 'Importe_Num'], keep='last')
        
        st.metric("Total Suelo Mensual", f"{presupuesto['Importe_Num'].sum():,.2f} €")
        st.dataframe(presupuesto[["Descripcion", "Importe_Num"]], use_container_width=True)

with t4:
    if not df_hist.empty:
        st.dataframe(df_hist.sort_values("Fecha_DT", ascending=False), use_container_width=True)
