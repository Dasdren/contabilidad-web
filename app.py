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
        st.error(f"⚠️ Error de conexión con Google Sheets. Revisa tus Secrets.")
        st.stop()

sheet = conectar_google_sheets()

# --- LIMPIEZA DE MONTO (ESPECÍFICA SANTANDER) ---
def limpiar_monto_santander(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip().replace('"', '')
    # El Santander usa el signo '−' (Unicode U+2212), lo cambiamos al guion normal
    s = s.replace('−', '-').replace('€', '').replace('EUR', '')
    # Quitar puntos de miles y cambiar coma por punto decimal
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except:
        return 0.0

# --- CARGA DE DATOS (CON FILTRO DE SEGURIDAD) ---
def load_data():
    try:
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
    except:
        df = pd.DataFrame()

    # Si la hoja está vacía, creamos la estructura mínima para que no de error
    columnas_necesarias = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
    for col in columnas_necesarias:
        if col not in df.columns:
            df[col] = None

    if not df.empty:
        # Forzamos la creación de Fecha_DT para evitar el KeyError
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        # Limpiamos el monto por si Google Sheets lo guardó como texto
        df["Monto_Num"] = df["Monto"].apply(limpiar_monto_santander)
        # Normalizamos la columna Es_Fijo
        df["Es_Fijo"] = df["Es_Fijo"].astype(str).str.upper().fillna("NO")
    else:
        # Si está vacío, creamos columnas vacías pero con el nombre correcto
        df["Fecha_DT"] = pd.to_datetime([])
        df["Monto_Num"] = pd.Series(dtype=float)

    return df

# --- INTERFAZ ---
st.title("🏦 Santander Smart Finance")
df = load_data()

# --- PESTAÑAS ---
t1, t2, t3, t4 = st.tabs(["📊 Balance Histórico", "📅 Planificador (Fijos)", "🤖 Asesor IA", "📂 Historial Completo"])

# --- SIDEBAR: IMPORTACIÓN SANTANDER ---
st.sidebar.header("📥 Importar Santander")
archivo = st.sidebar.file_uploader("Sube el CSV del Santander", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar y Guardar"):
        try:
            # Santander tiene filas de basura al inicio. Buscamos 'Fecha operación'
            raw_content = archivo.getvalue().decode("utf-8").splitlines()
            start_row = 0
            for i, line in enumerate(raw_content):
                if "Fecha operación" in line:
                    start_row = i
                    break
            
            archivo.seek(0)
            df_new = pd.read_csv(archivo, skiprows=start_row)
            
            # 1. MAPEO DE COLUMNAS (Santander -> App)
            # El Santander usa: 'Fecha operación', 'Concepto', 'Importe'
            df_new = df_new.rename(columns={
                'Fecha operación': 'Fecha',
                'Concepto': 'Descripcion',
                'Importe': 'Monto'
            })

            # 2. LIMPIEZA DE DATOS
            df_new["Monto_Num"] = df_new["Monto"].apply(limpiar_monto_santander)
            df_new["Tipo"] = np.where(df_new["Monto_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            
            # 3. IA DE GASTOS FIJOS (REPETICIÓN)
            # Miramos si el mismo concepto e importe aparece en diferentes fechas
            df_new['Fecha_DT_Tmp'] = pd.to_datetime(df_new['Fecha'], dayfirst=True)
            df_new['Mes_Año'] = df_new['Fecha_DT_Tmp'].dt.strftime('%Y-%m')
            
            # Si una Descripción + Monto aparece en más de un mes diferente, es Fijo
            frecuencia = df_new.groupby(['Descripcion', 'Monto_Num'])['Mes_Año'].nunique().reset_index()
            conceptos_fijos = frecuencia[frecuencia['Mes_Año'] > 1]
            
            df_new["Es_Fijo"] = "NO"
            for _, row in conceptos_fijos.iterrows():
                mask = (df_new['Descripcion'] == row['Descripcion']) & (df_new['Monto_Num'] == row['Monto_Num'])
                df_new.loc[mask, "Es_Fijo"] = "SÍ"

            # 4. SUBIR A GOOGLE SHEETS
            final_to_save = df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Monto_Num", "Es_Fijo"]]
            sheet.append_rows(final_to_save.values.tolist())
            
            st.sidebar.success(f"✅ ¡{len(df_new)} movimientos importados!")
            st.rerun()
            
        except Exception as e:
            st.sidebar.error(f"Error procesando el archivo: {e}")

# --- CONTENIDO DE PESTAÑAS ---
with t1:
    if not df.empty and df["Fecha_DT"].notnull().any():
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance Total", f"{df['Monto_Num'].sum():,.2f} €")
        c2.metric("Ingresos", f"{df[df['Monto_Num']>0]['Monto_Num'].sum():,.2f} €")
        c3.metric("Gastos", f"{df[df['Monto_Num']<0]['Monto_Num'].sum():,.2f} €")
        
        df_plot = df.dropna(subset=['Fecha_DT']).sort_values("Fecha_DT")
        st.plotly_chart(px.line(df_plot, x="Fecha_DT", y="Monto_Num", color="Tipo"), use_container_width=True)
    else:
        st.info("Sube tu archivo CSV en la barra lateral para empezar.")

with t2:
    st.header("📅 Tu Presupuesto Mensual (Gastos Fijos)")
    st.write("Aquí cada gasto recurrente solo cuenta una vez para que sepas cuánto dinero necesitas al mes.")
    
    if not df.empty:
        # Filtramos solo lo marcado como fijo y que sea gasto (negativo)
        fijos = df[(df["Es_Fijo"] == "SÍ") & (df["Monto_Num"] < 0)]
        
        # ELIMINAR DUPLICADOS: Solo queremos ver el concepto y su importe una vez
        presupuesto = fijos.drop_duplicates(subset=['Descripcion', 'Monto_Num'], keep='last')
        
        st.metric("Total Gasto Mensual Estimado", f"{presupuesto['Monto_Num'].sum():,.2f} €")
        st.table(presupuesto[["Descripcion", "Monto_Num"]])
    else:
        st.write("No hay gastos fijos detectados todavía.")

with t4:
    if not df.empty and "Fecha_DT" in df.columns:
        # Ordenamos por fecha descendente
        st.dataframe(df.sort_values("Fecha_DT", ascending=False), use_container_width=True)
