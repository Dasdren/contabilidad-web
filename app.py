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

# --- CARGA DE DATOS ---
def load_data():
    try:
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
    except:
        df = pd.DataFrame()

    # Columnas que nuestra base de datos NECESITA
    columnas_base = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
    
    # Si la hoja está vacía o faltan columnas, las creamos
    for col in columnas_base:
        if col not in df.columns:
            df[col] = None

    # Creamos siempre las columnas de cálculo para evitar KeyErrors
    if not df.empty:
        df["Monto_Num"] = pd.to_numeric(df["Monto"].apply(limpiar_importe_santander), errors='coerce').fillna(0.0)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Es_Fijo_Clean"] = df["Es_Fijo"].astype(str).str.upper().fillna("NO")
    else:
        df["Monto_Num"] = pd.Series(dtype=float)
        df["Fecha_DT"] = pd.to_datetime([])
        df["Es_Fijo_Clean"] = pd.Series(dtype=str)

    return df

# --- INTERFAZ ---
st.title("🏦 Santander Smart Finance")
df = load_data()

t1, t2, t3, t4 = st.tabs(["📊 Dashboard", "📅 Planificador (Fijos)", "🤖 Asesor IA", "📂 Datos"])

# --- SIDEBAR: IMPORTACIÓN ---
st.sidebar.header("📥 Importar Santander")
archivo = st.sidebar.file_uploader("Sube el CSV del Santander", type=["csv"])

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
            # Leemos el CSV ignorando las columnas que no queremos
            df_new = pd.read_csv(archivo, skiprows=start_row)
            
            # Solo nos quedamos con las que importan
            # Santander usa: Fecha operación, Concepto, Importe
            df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
            
            # Renombramos a nuestro formato interno
            df_new = df_new.rename(columns={
                'Fecha operación': 'Fecha',
                'Concepto': 'Descripcion',
                'Importe': 'Monto'
            })

            # Limpiamos números
            df_new["Monto_Num"] = df_new["Monto"].apply(limpiar_importe_santander)
            df_new["Tipo"] = np.where(df_new["Monto_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            
            # --- DETECTAR FIJOS ---
            df_new['Fecha_DT_Tmp'] = pd.to_datetime(df_new['Fecha'], dayfirst=True)
            df_new['Mes_Año'] = df_new['Fecha_DT_Tmp'].dt.strftime('%Y-%m')
            
            # Buscamos duplicados en distintos meses
            frecuencia = df_new.groupby(['Descripcion', 'Monto_Num'])['Mes_Año'].nunique().reset_index()
            fijos_detectados = frecuencia[frecuencia['Mes_Año'] > 1]
            
            df_new["Es_Fijo"] = "NO"
            for _, row in fijos_detectados.iterrows():
                mask = (df_new['Descripcion'] == row['Descripcion']) & (df_new['Monto_Num'] == row['Monto_Num'])
                df_new.loc[mask, "Es_Fijo"] = "SÍ"

            # Guardar en Google Sheets (Columnas finales)
            final_save = df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]]
            sheet.append_rows(final_save.values.tolist())
            
            st.sidebar.success(f"✅ ¡{len(df_new)} movimientos añadidos!")
            st.rerun()
            
        except Exception as e:
            st.sidebar.error(f"Error procesando: {e}")

# --- PESTAÑAS ---
with t1:
    if not df.empty and df["Fecha_DT"].notnull().any():
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance Total", f"{df['Monto_Num'].sum():,.2f} €")
        c2.metric("Ingresos", f"{df[df['Monto_Num']>0]['Monto_Num'].sum():,.2f} €")
        c3.metric("Gastos", f"{df[df['Monto_Num']<0]['Monto_Num'].sum():,.2f} €")
        
        st.plotly_chart(px.line(df.dropna(subset=['Fecha_DT']).sort_values("Fecha_DT"), 
                               x="Fecha_DT", y="Monto_Num", color="Tipo"), use_container_width=True)
    else:
        st.info("Sube tu primer CSV para ver las gráficas.")

with t2:
    st.subheader("🔮 Gastos Fijos (Sin duplicados)")
    st.write("Si un gasto se repite cada mes, aquí solo lo ves una vez para calcular tu presupuesto.")
    if not df.empty:
        # Filtramos fijos y quitamos duplicados para el cálculo mensual
        fijos = df[(df["Es_Fijo_Clean"] == "SÍ") & (df["Monto_Num"] < 0)]
        presupuesto = fijos.drop_duplicates(subset=['Descripcion', 'Monto_Num'], keep='last')
        
        st.metric("Total Suelo Mensual", f"{presupuesto['Monto_Num'].sum():,.2f} €")
        st.table(presupuesto[["Descripcion", "Monto"]])
    else:
        st.write("No hay gastos fijos.")

with t4:
    if not df.empty and "Fecha_DT" in df.columns:
        st.dataframe(df.sort_values("Fecha_DT", ascending=False, na_position='last'), use_container_width=True)
