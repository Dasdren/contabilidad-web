import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import google.generativeai as genai

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Santander IA Expert", layout="wide", page_icon="🏦")

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
        st.error(f"⚠️ Error de conexión: {e}")
        st.stop()

sheet = conectar_google_sheets()

# --- LIMPIEZA DE IMPORTES ---
def limpiar_importe(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('−', '-')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    s = "".join(c for c in s if c.isdigit() or c in '.-')
    try: return float(s)
    except: return 0.0

# --- CARGA DE DATOS ---
def load_data():
    try:
        records = sheet.get_all_records()
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        
        # Columnas requeridas
        for col in ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]:
            if col not in df.columns: df[col] = None
            
        df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Año"] = df["Fecha_DT"].dt.year
        df["Mes_Nombre"] = df["Fecha_DT"].dt.strftime('%m - %b')
        return df
    except Exception as e:
        st.error(f"Error al leer la tabla: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
df = load_data()
st.title("📊 Santander Smart Dashboard")

# --- BARRA LATERAL: DIAGNÓSTICO ---
with st.sidebar:
    st.header("📥 Importar Datos")
    archivo = st.file_uploader("Sube el CSV del Santander", type=["csv"])
    if archivo:
        if st.button("🚀 Procesar CSV"):
            try:
                raw = archivo.getvalue().decode("utf-8").splitlines()
                skip = 0
                for i, line in enumerate(raw):
                    if "Fecha operación" in line: skip = i; break
                archivo.seek(0)
                df_new = pd.read_csv(archivo, skiprows=skip, dtype=str, sep=None, engine='python')
                df_new.columns = df_new.columns.str.strip()
                # Mapeo exacto pedido
                df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
                df_new.columns = ["Fecha", "Descripcion", "Importe"]
                df_new["Tipo"] = "Gasto" # Simplificado para el guardado
                df_new["Categoria"] = "Varios"
                df_new["Es_Fijo"] = "NO"
                
                sheet.append_rows(df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]].values.tolist())
                st.success("¡Datos guardados!")
                st.rerun()
            except Exception as e:
                st.error(f"Error en CSV: {e}")

    st.divider()
    if not df.empty:
        # Selector de año (Si está vacío, mostrará 2025 por defecto)
        lista_años = sorted(df["Año"].dropna().unique().astype(int))
        if not lista_años: lista_años = [2025]
        año_sel = st.selectbox("📅 Ver año:", lista_años, index=len(lista_años)-1)
    else:
        año_sel = 2025

# --- LÓGICA DE VISUALIZACIÓN ---
if df.empty:
    st.warning("📭 La base de datos está vacía.")
    st.info("Por favor, sube un archivo CSV desde la barra lateral o revisa que tu Google Sheets tenga datos debajo de los encabezados.")
    st.image("https://via.placeholder.com/800x200?text=Esperando+datos+de+Google+Sheets...")
else:
    df_filtrado = df[df["Año"] == año_sel].copy()
    
    if df_filtrado.empty:
        st.info(f"No hay movimientos registrados para el año {año_sel}.")
        st.write("Datos disponibles para otros años:", df["Año"].unique())
    else:
        # PESTAÑAS
        t1, t2, t3 = st.tabs(["🏠 Resumen", "🤖 Gem Experto", "📂 Editor Vivo"])
        
        with t1:
            # MÉTRICAS
            ing = df_filtrado[df_filtrado["Importe_Num"] > 0]["Importe_Num"].sum()
            gas = abs(df_filtrado[df_filtrado["Importe_Num"] < 0]["Importe_Num"].sum())
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Ingresos", f"{ing:,.2f} €")
            c2.metric("Gastos", f"{gas:,.2f} €", delta_color="inverse")
            c3.metric("Balance", f"{(ing-gas):,.2f} €")
            
            # GRÁFICAS (PROTEGIDAS CONTRA SHAPE ERROR)
            col_a, col_b = st.columns([2, 1])
            with col_a:
                st.subheader("Evolución Mensual")
                df_m = df_filtrado.groupby(["Mes_Nombre", "Tipo"])["Importe_Num"].sum().abs().reset_index()
                st.plotly_chart(px.bar(df_m, x="Mes_Nombre", y="Importe_Num", color="Tipo", barmode="group"), use_container_width=True)
            
            with col_b:
                st.subheader("Categorías")
                df_pie = df_filtrado[df_filtrado["Importe_Num"] < 0].copy()
                if not df_pie.empty:
                    df_pie["Abs_Importe"] = df_pie["Importe_Num"].abs()
                    st.plotly_chart(px.pie(df_pie, values="Abs_Importe", names="Categoria", hole=0.4), use_container_width=True)
                else:
                    st.write("No hay gastos para este año.")

        with t2:
            st.header("🤖 Gem: Experto Financiero")
            if st.button("✨ Analizar con IA"):
                st.write("Conectando con Gemini...")
                # (Aquí iría tu función llamar_experto_ia configurada)
