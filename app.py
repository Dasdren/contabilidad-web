import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import re

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Santander IA Pro", layout="wide", page_icon="🏦")

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

# --- EL LIMPIADOR INFALIBLE DE DECIMALES ---
def limpiar_importe_santander(valor):
    if pd.isna(valor) or str(valor).strip() == "":
        return 0.0
    
    # 1. Convertir a texto y quitar comillas/espacios
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('€', '')
    
    # 2. Corregir el signo menos especial del Santander (−) a guion estándar (-)
    s = s.replace('−', '-')
    
    # 3. TRATAMIENTO QUIRÚRGICO DE LA COMA:
    # Ejemplo: "1.200,50" o "-34,95"
    if ',' in s:
        # Primero quitamos el punto de los miles si existe
        s = s.replace('.', '')
        # Cambiamos la coma decimal por el punto de Python
        s = s.replace(',', '.')
    
    # 4. Filtro final: Nos quedamos SOLO con números, el punto y el signo menos
    # Esto evita que cualquier letra o símbolo rompa el proceso
    s = "".join(c for c in s if c.isdigit() or c in '.-')
    
    try:
        # Retornamos el float con sus decimales correctos
        return float(s)
    except:
        return 0.0

def load_data():
    try:
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
    except:
        df = pd.DataFrame()
    
    # Garantizar que las columnas técnicas existan siempre
    cols_necesarias = ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]
    for c in cols_necesarias:
        if c not in df.columns: df[c] = ""
    
    if not df.empty:
        df["Importe_Num"] = df["Importe"].apply(limpiar_importe_santander)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Es_Fijo_Clean"] = df["Es_Fijo"].astype(str).str.upper().str.strip()
    else:
        # Estructura de seguridad para hoja vacía
        df["Importe_Num"] = pd.Series(dtype=float)
        df["Fecha_DT"] = pd.to_datetime([])
        df["Es_Fijo_Clean"] = pd.Series(dtype=str)
    return df

# --- INTERFAZ ---
st.title("🏦 Santander Smart Finance")
df_hist = load_data()

t1, t2, t3, t4 = st.tabs(["📊 Dashboard", "📅 Planificador (Fijos)", "🤖 Asesor IA", "📂 Historial"])

# --- SIDEBAR: IMPORTACIÓN ---
st.sidebar.header("📥 Importar Santander")
archivo = st.sidebar.file_uploader("Sube el CSV del Santander", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar e Importar"):
        try:
            # 1. Identificar dónde empiezan los datos y el separador
            raw_data = archivo.getvalue().decode("utf-8").splitlines()
            skip_idx = 0
            for i, line in enumerate(raw_data):
                if "Fecha operación" in line:
                    skip_idx = i
                    break
            
            archivo.seek(0)
            # Leemos todo como TEXTO (dtype=str) para que no se pierdan las comas al abrirlo
            df_new = pd.read_csv(archivo, skiprows=skip_idx, dtype=str, sep=None, engine='python')
            
            # 2. Limpiar nombres de columnas
            df_new.columns = df_new.columns.str.strip().str.replace('"', '')
            
            # 3. Quedarnos solo con las 3 columnas del Santander
            df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
            df_new.columns = ["Fecha", "Descripcion", "Importe"]
            
            # 4. Limpieza numérica estricta
            df_new["Importe_Num"] = df_new["Importe"].apply(limpiar_importe_santander)
            df_new["Tipo"] = np.where(df_new["Importe_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            
            # 5. LÓGICA DE GASTOS FIJOS (REPETICIÓN)
            # Detectamos fijos comparando lo nuevo con el histórico
            df_new["Es_Fijo"] = "NO"
            
            # Concatenamos para ver frecuencia de concepto + importe
            if not df_hist.empty:
                full_temp = pd.concat([df_hist[['Descripcion', 'Importe_Num']], df_new[['Descripcion', 'Importe_Num']]])
            else:
                full_temp = df_new[['Descripcion', 'Importe_Num']].copy()
            
            # Si se repite más de una vez la combinación exacta, lo marcamos como fijo
            frecuencia = full_temp.groupby(['Descripcion', 'Importe_Num']).size().reset_index(name='cuenta')
            conceptos_fijos = frecuencia[frecuencia['cuenta'] > 1]

            for _, row in conceptos_fijos.iterrows():
                mask = (df_new["Descripcion"] == row["Descripcion"]) & (df_new["Importe_Num"] == row["Importe_Num"])
                df_new.loc[mask, "Es_Fijo"] = "SÍ"

            # 6. Guardar en Google Sheets
            # Convertimos a string para asegurar que GSheets no haga cosas raras
            final_rows = df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]]
            sheet.append_rows(final_rows.values.tolist())
            
            st.sidebar.success(f"✅ ¡{len(df_new)} movimientos importados!")
            st.rerun()
            
        except Exception as e:
            st.sidebar.error(f"Error procesando archivo: {e}")

# --- PESTAÑAS ---
with t1:
    if not df_hist.empty and df_hist["Fecha_DT"].notnull().any():
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance Total", f"{df_hist['Importe_Num'].sum():,.2f} €")
        c2.metric("Ingresos", f"{df_hist[df_hist['Importe_Num']>0]['Importe_Num'].sum():,.2f} €")
        c3.metric("Gastos", f"{df_hist[df_hist['Importe_Num']<0]['Importe_Num'].sum():,.2f} €")
        
        fig = px.line(df_hist.dropna(subset=['Fecha_DT']).sort_values("Fecha_DT"), x="Fecha_DT", y="Importe_Num", color="Tipo")
        st.plotly_chart(fig, use_container_width=True)

with t2:
    st.header("📋 Presupuesto Mensual (Gastos Fijos)")
    st.info("Aquí cada gasto fijo solo se suma UNA vez para calcular tu 'suelo' mensual de gastos.")
    if not df_hist.empty:
        # Filtramos fijos y quitamos duplicados (Misma descripción + importe = 1 gasto mensual)
        fijos = df_hist[(df_hist["Es_Fijo_Clean"] == "SÍ") & (df_hist["Importe_Num"] < 0)]
        
        # ELIMINAR DUPLICADOS PARA EL PLANIFICADOR
        presupuesto = fijos.drop_duplicates(subset=['Descripcion', 'Importe_Num'], keep='last')
        
        st.metric("Total Suelo Mensual (Sin duplicar)", f"{presupuesto['Importe_Num'].sum():,.2f} €")
        st.dataframe(presupuesto[["Fecha", "Descripcion", "Importe_Num"]], use_container_width=True)

with t4:
    if not df_hist.empty:
        st.dataframe(df_hist.sort_values("Fecha_DT", ascending=False, na_position='last'), use_container_width=True)
