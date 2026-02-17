import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
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

# --- LA FUNCIÓN CLAVE: LIMPIEZA DE DECIMALES ---
def limpiar_dinero_santander(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    
    # 1. Convertir a texto y limpiar basura (comillas, espacios, EUR)
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('€', '')
    
    # 2. Manejar el signo negativo especial del Santander (−)
    s = s.replace('−', '-')
    
    # 3. LÓGICA DE DECIMALES ESPAÑOLES:
    # Ejemplo: "1.200,50" -> Queremos "1200.50"
    if ',' in s:
        s = s.replace('.', '')  # Quitamos el punto de los miles (si existe)
        s = s.replace(',', '.') # Cambiamos la coma decimal por el punto de Python
    
    try:
        return float(s)
    except:
        # Si falla, intentamos quitar cualquier carácter que no sea número, punto o menos
        s = re.sub(r'[^\d.-]', '', s)
        try: return float(s)
        except: return 0.0

# --- CARGA DE DATOS ---
def load_data():
    try:
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
    except:
        df = pd.DataFrame()

    # Columnas que Google Sheets debe tener (Asegúrate de que la E1 sea 'Importe')
    columnas_base = ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]
    for col in columnas_base:
        if col not in df.columns: df[col] = None

    if not df.empty:
        # Aplicamos la limpieza ultra-reforzada
        df["Importe_Num"] = df["Importe"].apply(limpiar_dinero_santander)
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

t1, t2, t3, t4 = st.tabs(["📊 Dashboard", "📅 Planificador (Fijos)", "🤖 Asesor IA", "📂 Datos"])

# --- SIDEBAR: IMPORTACIÓN ---
st.sidebar.header("📥 Importar Santander")
archivo = st.sidebar.file_uploader("Sube el CSV del Santander", type=["csv"])

if archivo:
    if st.sidebar.button("🚀 Procesar e Importar"):
        try:
            # Detectar cabecera y separador
            raw_content = archivo.getvalue().decode("utf-8").splitlines()
            header_row = -1
            sep_detectado = ","
            for i, line in enumerate(raw_content):
                if "Fecha operación" in line:
                    header_row = i
                    if ";" in line: sep_detectado = ";"
                    break
            
            if header_row == -1:
                st.sidebar.error("No se encontró 'Fecha operación'.")
                st.stop()
            
            archivo.seek(0)
            # Leemos todo como TEXTO (dtype=str) para que no rompa los decimales antes de tiempo
            df_new = pd.read_csv(archivo, skiprows=header_row, sep=sep_detectado, dtype=str, engine='python')
            
            # Limpieza de nombres de columnas
            df_new.columns = df_new.columns.str.strip().str.replace('"', '')
            
            # Filtrar por las columnas que sabemos que existen por tu foto
            # Fecha operación | Concepto | Importe
            df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
            df_new.columns = ["Fecha", "Descripcion", "Importe"]

            # Aplicar limpieza numérica
            df_new["Importe_Num"] = df_new["Importe"].apply(limpiar_dinero_santander)
            df_new["Tipo"] = np.where(df_new["Importe_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            
            # IA DE GASTOS FIJOS
            df_new['Fecha_DT_Tmp'] = pd.to_datetime(df_new['Fecha'], dayfirst=True, errors='coerce')
            df_new['Mes_Año'] = df_new['Fecha_DT_Tmp'].dt.strftime('%Y-%m')
            
            # Si una Descripción + Importe aparece en más de un mes diferente, es Fijo
            frecuencia = df_new.groupby(['Descripcion', 'Importe_Num'])['Mes_Año'].nunique().reset_index()
            fijos_detectados = frecuencia[frecuencia['Mes_Año'] > 1]
            
            df_new["Es_Fijo"] = "NO"
            for _, row in fijos_detectados.iterrows():
                mask = (df_new['Descripcion'] == row['Descripcion']) & (df_new['Importe_Num'] == row['Importe_Num'])
                df_new.loc[mask, "Es_Fijo"] = "SÍ"

            # Guardar en Google Sheets (usamos el texto original limpio para no perder decimales en la subida)
            final_save = df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe_Num", "Es_Fijo"]]
            sheet.append_rows(final_save.values.tolist())
            
            st.sidebar.success(f"✅ ¡{len(df_new)} movimientos añadidos correctamente!")
            st.rerun()
            
        except Exception as e:
            st.sidebar.error(f"Error procesando: {e}")

# --- PESTAÑAS ---
with t1:
    if not df.empty and df["Fecha_DT"].notnull().any():
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance Total", f"{df['Importe_Num'].sum():,.2f} €")
        c2.metric("Ingresos", f"{df[df['Importe_Num']>0]['Importe_Num'].sum():,.2f} €")
        c3.metric("Gastos", f"{df[df['Importe_Num']<0]['Importe_Num'].sum():,.2f} €")
        
        df_sort = df.dropna(subset=['Fecha_DT']).sort_values("Fecha_DT")
        st.plotly_chart(px.line(df_sort, x="Fecha_DT", y="Importe_Num", color="Tipo"), use_container_width=True)

with t2:
    st.subheader("📅 Gastos Fijos (Presupuesto Mensual)")
    if not df.empty:
        # Filtramos fijos y deduplicamos para ver solo el coste mensual único
        fijos = df[(df["Es_Fijo_Clean"] == "SÍ") & (df["Importe_Num"] < 0)]
        presupuesto = fijos.drop_duplicates(subset=['Descripcion', 'Importe_Num'], keep='last')
        
        st.metric("Total Suelo Mensual", f"{presupuesto['Importe_Num'].sum():,.2f} €")
        st.dataframe(presupuesto[["Descripcion", "Importe_Num"]], use_container_width=True)

with t4:
    st.dataframe(df.sort_values("Fecha_DT", ascending=False, na_position='last'), use_container_width=True)
