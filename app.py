import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import re
import google.generativeai as genai
from sklearn.linear_model import LinearRegression

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Gestor Santander IA", layout="wide", page_icon="🏦")

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
        st.error(f"⚠️ Error Sheets: {e}")
        st.stop()

sheet = conectar_google_sheets()

# --- CONEXIÓN GEMINI AI ---
def consultar_gemini(resumen_texto):
    try:
        api_key = st.secrets["gemini_api_key"]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"Asesor financiero. Analiza estos datos: {resumen_texto}. Dame 3 consejos de ahorro. Habla de tú."
        response = model.generate_content(prompt)
        return response.text
    except:
        return "IA temporalmente no disponible."

# --- LIMPIEZA DE DATOS (ESPECÍFICA SANTANDER) ---
def limpiar_monto_santander(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip()
    # Santander usa el carácter Unicode '−' (U+2212) no el guion '-'
    s = s.replace('−', '-').replace('€', '').replace('EUR', '').replace('?', '')
    # Quitar puntos de miles y cambiar coma por punto decimal
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

# --- LÓGICA DE CARGA ---
def load_data():
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    # Asegurar columnas
    cols = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
    for c in cols: 
        if c not in df.columns: df[c] = ""
    
    if not df.empty:
        df["Monto_Num"] = df["Monto"].apply(limpiar_monto_santander)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], errors='coerce')
        df["Es_Fijo_Clean"] = df["Es_Fijo"].astype(str).str.upper()
    return df

# --- INTERFAZ ---
st.title("🏦 Mi Gestor Santander + IA")
df = load_data()

# --- SIDEBAR: IMPORTACIÓN SANTANDER ---
st.sidebar.header("📥 Importar CSV Santander")
archivo = st.sidebar.file_uploader("Sube el CSV descargado del banco", type=["csv"])

if archivo is not None:
    if st.sidebar.button("Procesar Santander"):
        try:
            # Leer saltando las filas de resumen del banco hasta encontrar 'Fecha operación'
            # Buscamos la fila que contiene los datos reales
            raw_lines = archivo.getvalue().decode("utf-8").splitlines()
            start_idx = 0
            for i, line in enumerate(raw_lines):
                if "Fecha operación" in line:
                    start_idx = i
                    break
            
            archivo.seek(0)
            df_new = pd.read_csv(archivo, skiprows=start_idx)
            
            # Limpiar columnas de Santander
            df_new = df_new.rename(columns={
                'Fecha operación': 'Fecha',
                'Concepto': 'Descripcion',
                'Importe': 'Monto'
            })
            
            # Procesar importes
            df_new["Monto_Num"] = df_new["Monto"].apply(limpiar_monto_santander)
            df_new["Tipo"] = np.where(df_new["Monto_Num"] < 0, "Gasto", "Ingreso")
            df_new["Categoria"] = "Varios"
            
            # --- DETECTOR DE GASTOS FIJOS (IA INTERNA) ---
            # Identificamos como fijo si el mismo concepto e importe aparece en meses distintos
            df_new['Fecha_DT'] = pd.to_datetime(df_new['Fecha'], dayfirst=True)
            df_new['Mes_Año'] = df_new['Fecha_DT'].dt.strftime('%Y-%m')
            
            # Agrupamos para ver repeticiones
            frecuencia = df_new.groupby(['Descripcion', 'Monto_Num'])['Mes_Año'].nunique().reset_index()
            conceptos_fijos = frecuencia[frecuencia['Mes_Año'] > 1] # Si aparece en más de 1 mes es fijo
            
            # Marcamos
            df_new['Es_Fijo'] = "NO"
            for _, row in conceptos_fijos.iterrows():
                mask = (df_new['Descripcion'] == row['Descripcion']) & (df_new['Monto_Num'] == row['Monto_Num'])
                df_new.loc[mask, 'Es_Fijo'] = "SÍ"

            # Formatear para Google Sheets
            df_final = df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Monto_Num", "Es_Fijo"]]
            sheet.append_rows(df_final.values.tolist())
            
            st.sidebar.success(f"✅ ¡{len(df_final)} movimientos importados!")
            st.rerun()
            
        except Exception as e:
            st.sidebar.error(f"Error formato: {e}")

# --- PESTAÑAS ---
t1, t2, t3, t4 = st.tabs(["📊 Balance Histórico", "📅 Planificador (Fijos)", "🔮 Previsiones", "📂 Movimientos"])

with t1:
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Saldo Actual", f"{df['Monto_Num'].sum():,.2f} €")
        c2.metric("Ingresos", f"{df[df['Monto_Num']>0]['Monto_Num'].sum():,.2f} €")
        c3.metric("Gastos", f"{df[df['Monto_Num']<0]['Monto_Num'].sum():,.2f} €")
        
        fig = px.area(df.sort_values("Fecha_DT"), x="Fecha_DT", y="Monto_Num", color="Tipo", title="Evolución de cuenta")
        st.plotly_chart(fig, use_container_width=True)

with t2:
    st.header("📋 Presupuesto Fijo Mensual")
    st.info("Aquí solo contamos cada gasto fijo UNA VEZ, sin importar cuántas veces aparezca en el historial.")
    
    if not df.empty:
        # Filtramos fijos únicos para el presupuesto mensual
        fijos = df[(df["Es_Fijo_Clean"] == "SÍ") & (df["Monto_Num"] < 0)]
        fijos_mensuales = fijos.drop_duplicates(subset=['Descripcion', 'Monto_Num'], keep='last')
        
        coste = fijos_mensuales["Monto_Num"].sum()
        st.metric("Tu 'Suelo' de Gastos (Mes)", f"{coste:,.2f} €")
        st.dataframe(fijos_mensuales[["Categoria", "Descripcion", "Monto_Num"]], use_container_width=True)

with t3:
    st.header("🔮 Tendencia")
    if len(df) > 5:
        df_p = df.sort_values("Fecha_DT").dropna(subset=["Fecha_DT"])
        df_p["Acum"] = df_p["Monto_Num"].cumsum()
        df_p["Ord"] = df_p["Fecha_DT"].map(datetime.toordinal)
        model = LinearRegression().fit(df_p[["Ord"]].values, df_p["Acum"].values)
        
        fechas = [df_p["Fecha_DT"].max() + timedelta(days=x) for x in range(1, 31)]
        preds = model.predict(np.array([d.toordinal() for d in fechas]).reshape(-1, 1))
        
        fig_p = px.line(x=fechas, y=preds, title="Proyección a 30 días")
        st.plotly_chart(fig_p, use_container_width=True)

with t4:
    st.dataframe(df.sort_values("Fecha_DT", ascending=False))
