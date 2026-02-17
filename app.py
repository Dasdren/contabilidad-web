import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import google.generativeai as genai

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Santander Cyber Dashboard", layout="wide", page_icon="🌙")

# --- CSS: MODO OSCURO TOTAL Y COLORES LED ---
st.markdown("""
<style>
    /* Fondo negro para toda la aplicación */
    .stApp {
        background-color: #000000 !important;
        color: #FFFFFF !important;
    }
    
    /* Títulos y textos en blanco */
    h1, h2, h3, p, span, label {
        color: #FFFFFF !important;
    }

    /* Estilo para las tarjetas de métricas */
    [data-testid="metric-container"] {
        background-color: #111111;
        border: 1px solid #333333;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
    }

    /* Colores específicos para los números (LED effect) */
    /* Usaremos IDs o clases personalizadas vía Markdown para asegurar el color */
    .green-led { color: #2ecc71 !important; font-size: 2.5rem; font-weight: 800; text-shadow: 0 0 10px #2ecc7144; }
    .red-led { color: #e63946 !important; font-size: 2.5rem; font-weight: 800; text-shadow: 0 0 10px #e6394644; }
    .blue-led { color: #3498db !important; font-size: 2.5rem; font-weight: 800; text-shadow: 0 0 10px #3498db44; }
    .label-led { color: #AAAAAA !important; font-size: 1rem; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 1px; }

    /* Estilo de los Tabs */
    .stTabs [data-baseweb="tab-list"] { background-color: #000000; }
    .stTabs [data-baseweb="tab"] { color: #888888 !important; }
    .stTabs [aria-selected="true"] { color: #FFFFFF !important; border-bottom-color: #3498db !important; }

    /* Tablas y Editores en modo oscuro */
    .stDataFrame, [data-testid="stDataEditor"] {
        background-color: #111111 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN GOOGLE SHEETS ---
def conectar_google_sheets():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Contabilidad_App").sheet1
        return sheet
    except:
        st.error("⚠️ Error de conexión.")
        st.stop()

sheet = conectar_google_sheets()

# --- CARGA Y LIMPIEZA ---
def limpiar_importe(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('−', '-')
    if ',' in s: s = s.replace('.', '').replace(',', '.')
    s = "".join(c for c in s if c.isdigit() or c in '.-')
    try: return float(s)
    except: return 0.0

def load_data():
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
    df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
    df["Año"] = df["Fecha_DT"].dt.year
    df["Mes"] = df["Fecha_DT"].dt.strftime('%m - %b')
    return df

# --- INTERFAZ ---
df_raw = load_data()
st.title("🌙 Santander Cyber Dashboard")

with st.sidebar:
    st.header("📅 Histórico")
    años = sorted([int(a) for a in df_raw["Año"].dropna().unique() if a >= 2025], reverse=True)
    año_sel = st.selectbox("Año", años if años else [2026])
    st.divider()
    st.image("https://via.placeholder.com/200x50/000000/FFFFFF?text=SANTANDER+AI")

df = df_raw[df_raw["Año"] == año_sel].copy()

t1, t2, t3, t4 = st.tabs(["📊 Resumen Ejecutivo", "📅 Planificador Fijos", "🤖 Experto IA", "📂 Editor Vivo"])

# --- DASHBOARD CON NÚMEROS DE COLORES ---
with t1:
    if not df.empty:
        ing = df[df["Importe_Num"] > 0]["Importe_Num"].sum()
        gas = abs(df[df["Importe_Num"] < 0]["Importe_Num"].sum())
        bal = ing - gas
        
        # Diseño de métricas personalizadas con colores
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f'<p class="label-led">Ingresos Anuales</p><p class="green-led">{ing:,.2f} €</p>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<p class="label-led">Gastos Anuales</p><p class="red-led">{gas:,.2f} €</p>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<p class="label-led">Balance Neto</p><p class="blue-led">{bal:,.2f} €</p>', unsafe_allow_html=True)

        st.divider()

        # Gráficas con estilo oscuro
        g1, g2 = st.columns([2, 1])
        with g1:
            df_mes = df.groupby(["Mes", "Tipo"])["Importe_Num"].sum().abs().reset_index()
            fig = px.bar(df_mes, x="Mes", y="Importe_Num", color="Tipo", barmode="group",
                         template="plotly_dark", color_discrete_map={"Ingreso": "#2ecc71", "Gasto": "#e63946"})
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
        
        with g2:
            df_pie = df[df["Importe_Num"] < 0].copy()
            df_pie["Val"] = df_pie["Importe_Num"].abs()
            fig_p = px.pie(df_pie, values="Val", names="Categoria", hole=0.5, template="plotly_dark")
            fig_p.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_p, use_container_width=True)
    else:
        st.info("Sin datos para este periodo.")

# --- PLANIFICADOR ---
with t2:
    st.header("📋 Suelo de Gastos Fijos")
    fijos = df[(df["Es_Fijo"].str.upper() == "SÍ") & (df["Importe_Num"] < 0)]
    presupuesto = fijos.drop_duplicates(subset=['Descripcion'], keep='last')
    
    total_f = abs(presupuesto['Importe_Num'].sum())
    st.markdown(f'<p class="label-led">Necesidad Mensual</p><p class="blue-led">{total_f:,.2f} €</p>', unsafe_allow_html=True)
    st.dataframe(presupuesto[["Descripcion", "Importe", "Categoria"]], use_container_width=True)

# --- IA Y EDITOR SE MANTIENEN ---
with t3:
    st.header("🤖 Consultoría Experto Gem")
    if st.button("✨ Ejecutar Análisis Estratégico"):
        st.write("Analizando...") # Aquí conectas tu función de IA

with t4:
    st.header("📂 Editor de Datos")
    st.data_editor(df[["Fecha", "Descripcion", "Importe", "Categoria", "Es_Fijo"]], use_container_width=True)
