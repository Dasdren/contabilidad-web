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
    # Quitamos puntos de miles y cambiamos coma por punto
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
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

    # Columnas que nuestra base de datos interna espera
    columnas_finales = ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]
    
    for col in columnas_finales:
        if col not in df.columns:
            df[col] = None

    # Creamos las columnas de cálculo SIEMPRE para evitar el KeyError: 'Fecha_DT'
    if not df.empty:
        df["Importe_Num"] = pd.to_numeric(df["Importe"].apply(limpiar_importe_santander), errors='coerce').fillna(0.0)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Es_Fijo_Clean"] = df["Es_Fijo"].astype(str).str.upper().fillna("NO")
    else:
        # Si está vacía, inicializamos las columnas técnicas vacías
        df["Importe_Num"] = pd.Series(dtype=float)
        df["Fecha_DT"] = pd.to_datetime([])
        df["Es_Fijo_Clean"] = pd.Series(dtype=str)

    return df

# --- INTERFAZ ---
st.title("🏦 Santander Smart Manager")
df = load_data()

t1, t2, t3, t4 = st.tabs(["📊 Dashboard", "📅 Planificador (Fijos)", "🤖 Asesor IA", "📂 Historial"])

# --- SIDEBAR: IMPORTACIÓN ESPECÍFICA SANTANDER ---
st.sidebar.header("📥 Importar CSV Santander")
archivo = st.sidebar.file_uploader("Sube el CSV descargado del banco", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar e Importar"):
        try:
            # Buscamos la fila donde empiezan los datos reales ('Fecha operación')
            raw_content = archivo.getvalue().decode("utf-8").splitlines()
            start_row = 0
            for i, line in enumerate(raw_content):
                if "Fecha operación" in line:
                    start_row = i
                    break
            
            archivo.seek(0)
            df_new = pd.read_csv(archivo, skiprows=start_row)
            
            # 1. FILTRADO: Solo nos quedamos con las 3 columnas que nos sirven
            # Santander usa: 'Fecha operación', 'Concepto', 'Importe'
            df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
            
            # 2. RENOMBRADO: Para que coincida con nuestra base de datos (GSheets)
            df_new = df_new.rename(columns={
                'Fecha operación': 'Fecha',
                'Concepto': 'Descripcion',
                'Importe': 'Importe' # Mantenemos el nombre que pediste
            })

            # 3. PROCESAMIENTO NUMÉRICO
            df_new["Importe_Num"] = df_new["Importe"].apply(limpiar_importe_santander)
            df_new["Tipo"] = np.where(df_new["Importe_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            
            # 4. DETECCIÓN AUTOMÁTICA DE GASTOS FIJOS
            df_new['Fecha_DT_Tmp'] = pd.to_datetime(df_new['Fecha'], dayfirst=True)
            df_new['Mes_Año'] = df_new['Fecha_DT_Tmp'].dt.strftime('%Y-%m')
            
            # Agrupamos por concepto e importe para ver si se repiten en meses distintos
            frecuencia = df_new.groupby(['Descripcion', 'Importe_Num'])['Mes_Año'].nunique().reset_index()
            fijos_detectados = frecuencia[frecuencia['Mes_Año'] > 1]
            
            df_new["Es_Fijo"] = "NO"
            for _, row in fijos_detectados.iterrows():
                mask = (df_new['Descripcion'] == row['Descripcion']) & (df_new['Importe_Num'] == row['Importe_Num'])
                df_new.loc[mask, "Es_Fijo"] = "SÍ"

            # 5. GUARDAR EN GOOGLE SHEETS
            final_save = df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]]
            sheet.append_rows(final_save.values.tolist())
            
            st.sidebar.success(f"✅ ¡{len(df_new)} movimientos importados!")
            st.rerun()
            
        except Exception as e:
            st.sidebar.error(f"Error procesando el CSV: {e}")

# --- PESTAÑAS ---
with t1:
    if not df.empty and df["Fecha_DT"].notnull().any():
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance Neto", f"{df['Importe_Num'].sum():,.2f} €")
        c2.metric("Ingresos Total", f"{df[df['Importe_Num']>0]['Importe_Num'].sum():,.2f} €")
        c3.metric("Gastos Total", f"{df[df['Importe_Num']<0]['Importe_Num'].sum():,.2f} €", delta_color="inverse")
        
        fig = px.line(df.dropna(subset=['Fecha_DT']).sort_values("Fecha_DT"), 
                               x="Fecha_DT", y="Importe_Num", color="Tipo", title="Evolución Temporal")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sube tu archivo CSV en el lateral para ver las estadísticas.")

with t2:
    st.subheader("🔮 Gastos Fijos (Presupuesto Mensual)")
    st.write("Esta pestaña muestra cuánto te cuestan tus fijos al mes. No se duplican recibos repetidos.")
    
    if not df.empty:
        # Filtramos solo lo marcado como fijo y que sea gasto
        fijos_only = df[(df["Es_Fijo_Clean"] == "SÍ") & (df["Importe_Num"] < 0)]
        
        # LOGICA DE NO DUPLICIDAD: Solo mostramos un registro por cada binomio (Descripción, Importe)
        presupuesto = fijos_only.drop_duplicates(subset=['Descripcion', 'Importe_Num'], keep='last')
        
        st.metric("Total Suelo Mensual (Sin duplicados)", f"{presupuesto['Importe_Num'].sum():,.2f} €")
        st.dataframe(presupuesto[["Fecha", "Descripcion", "Importe"]], use_container_width=True)
    else:
        st.write("No hay gastos fijos detectados todavía.")

with t4:
    if not df.empty and "Fecha_DT" in df.columns:
        # Ordenamos por fecha descendente usando la columna técnica
        st.dataframe(df.sort_values("Fecha_DT", ascending=False, na_position='last'), use_container_width=True)
