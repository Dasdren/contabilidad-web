import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import re

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
        st.error("⚠️ Error de conexión. Revisa tus Secrets.")
        st.stop()

sheet = conectar_google_sheets()

# --- FUNCIONES DE LIMPIEZA ---

def limpiar_importe_santander(valor):
    """Convierte el formato del Santander (-34,95) a número real de Python (-34.95)"""
    if pd.isna(valor) or str(valor).strip() == "":
        return 0.0
    
    # 1. Convertir a texto y quitar espacios/basura
    s = str(valor).strip().replace('"', '').replace(' EUR', '')
    
    # 2. Arreglar el signo menos especial del Santander
    s = s.replace('−', '-')
    
    # 3. Quitar cualquier carácter que no sea número, coma, punto o guion
    s = re.sub(r'[^\d,.-]', '', s)
    
    # 4. LÓGICA DECIMAL ESPAÑOLA: 1.200,50 -> 1200.50
    if ',' in s:
        # Si hay puntos (miles), los borramos
        s = s.replace('.', '')
        # Cambiamos la coma por punto decimal
        s = s.replace(',', '.')
    
    try:
        return float(s)
    except:
        return 0.0

def load_data():
    """Carga los datos de Google Sheets"""
    try:
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
    except:
        df = pd.DataFrame()
    
    # Asegurar columnas correctas
    cols_base = ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]
    for c in cols_base:
        if c not in df.columns: df[c] = ""
    
    if not df.empty:
        df["Importe_Num"] = df["Importe"].apply(limpiar_importe_santander)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Es_Fijo_Clean"] = df["Es_Fijo"].astype(str).str.upper().str.strip()
    return df

# --- INTERFAZ ---
st.title("🏦 Santander Smart Finance")
df_historico = load_data()

t1, t2, t3, t4 = st.tabs(["📊 Dashboard", "📅 Planificación (Fijos)", "🤖 Asesor IA", "📂 Historial"])

# --- SIDEBAR: IMPORTACIÓN ---
st.sidebar.header("📥 Importar CSV Santander")
archivo = st.sidebar.file_uploader("Sube el archivo", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar e Importar"):
        try:
            # 1. Leer el archivo saltando la cabecera del banco
            raw_content = archivo.getvalue().decode("utf-8").splitlines()
            skip_n = 0
            for i, line in enumerate(raw_content):
                if "Fecha operación" in line:
                    skip_n = i
                    break
            
            archivo.seek(0)
            df_new = pd.read_csv(archivo, skiprows=skip_n, dtype=str)
            
            # 2. Filtrar columnas útiles
            df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
            df_new.columns = ["Fecha", "Descripcion", "Importe"]
            
            # 3. Limpieza de números
            df_new["Importe_Num"] = df_new["Importe"].apply(limpiar_importe_santander)
            df_new["Tipo"] = np.where(df_new["Importe_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            
            # 4. DETECCIÓN AUTOMÁTICA DE FIJOS
            # Comparamos lo nuevo con lo que ya existe en el histórico
            df_new["Es_Fijo"] = "NO"
            
            # Unimos temporalmente para ver repeticiones
            if not df_historico.empty:
                full_temp = pd.concat([df_historico[["Descripcion", "Importe_Num", "Fecha"]], 
                                      df_new[["Descripcion", "Importe_Num", "Fecha"]]])
            else:
                full_temp = df_new[["Descripcion", "Importe_Num", "Fecha"]].copy()
            
            full_temp["Mes"] = pd.to_datetime(full_temp["Fecha"], dayfirst=True, errors='coerce').dt.to_period('M')
            
            # Detectar conceptos que aparecen en más de un mes
            frecuencia = full_temp.groupby(["Descripcion", "Importe_Num"])["Mes"].nunique().reset_index()
            conceptos_fijos = frecuencia[frecuencia["Mes"] > 1]
            
            # Aplicar la marca "SÍ"
            for _, row in conceptos_fijos.iterrows():
                mask = (df_new["Descripcion"] == row["Descripcion"]) & (df_new["Importe_Num"] == row["Importe_Num"])
                df_new.loc[mask, "Es_Fijo"] = "SÍ"

            # 5. Guardar en Google Sheets (usando el número ya corregido)
            # Pasamos el número como string con punto para que Google lo entienda bien
            df_new["Importe"] = df_new["Importe_Num"].astype(str)
            
            final_save = df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]]
            sheet.append_rows(final_save.values.tolist())
            
            st.sidebar.success("✅ Importado con éxito.")
            st.rerun()
            
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

# --- PESTAÑAS ---
with t1:
    if not df_historico.empty and df_historico["Fecha_DT"].notnull().any():
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance Total", f"{df_historico['Importe_Num'].sum():,.2f} €")
        c2.metric("Ingresos", f"{df_historico[df_historico['Importe_Num']>0]['Importe_Num'].sum():,.2f} €")
        c3.metric("Gastos", f"{df_historico[df_historico['Importe_Num']<0]['Importe_Num'].sum():,.2f} €")
        
        st.plotly_chart(px.line(df_historico.sort_values("Fecha_DT"), x="Fecha_DT", y="Importe_Num", color="Tipo"), use_container_width=True)

with t2:
    st.header("📋 Gastos Fijos (Suelo Mensual)")
    st.info("Aquí cada gasto recurrente solo aparece UNA vez para que sepas cuánto necesitas al mes.")
    if not df_historico.empty:
        # Filtramos fijos y quitamos duplicados para ver el presupuesto mensual real
        fijos = df_historico[(df_historico["Es_Fijo_Clean"] == "SÍ") & (df_historico["Importe_Num"] < 0)]
        presupuesto = fijos.drop_duplicates(subset=['Descripcion', 'Importe_Num'], keep='last')
        
        st.metric("Total Gastos Fijos (Al mes)", f"{presupuesto['Importe_Num'].sum():,.2f} €")
        st.dataframe(presupuesto[["Descripcion", "Importe_Num"]], use_container_width=True)

with t4:
    if not df_historico.empty:
        st.dataframe(df_historico.sort_values("Fecha_DT", ascending=False), use_container_width=True)
