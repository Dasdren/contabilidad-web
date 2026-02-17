import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import google.generativeai as genai

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Multi-Bank Cyber Dashboard", layout="wide", page_icon="🌙")

st.markdown("""
<style>
    .stApp { background-color: #000000 !important; color: #FFFFFF !important; }
    h1, h2, h3, p, span, label { color: #FFFFFF !important; }
    [data-testid="metric-container"] {
        background-color: #111111; border: 1px solid #333333; padding: 20px; border-radius: 12px; text-align: center;
    }
    .green-led { color: #2ecc71 !important; font-size: 2.2rem; font-weight: 800; text-shadow: 0 0 10px #2ecc7144; }
    .red-led { color: #e63946 !important; font-size: 2.2rem; font-weight: 800; text-shadow: 0 0 10px #e6394644; }
    .blue-led { color: #3498db !important; font-size: 2.2rem; font-weight: 800; text-shadow: 0 0 10px #3498db44; }
    .label-led { color: #AAAAAA !important; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1px; }
    .stTabs [data-baseweb="tab-list"] { background-color: #000000; }
    .stDataFrame, [data-testid="stDataEditor"] { background-color: #111111 !important; }
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
        st.error("⚠️ Error de conexión con Google Sheets.")
        st.stop()

sheet = conectar_google_sheets()

# --- LIMPIEZA DE IMPORTES ---
def limpiar_importe(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('−', '-')
    if ',' in s: s = s.replace('.', '').replace(',', '.')
    s = "".join(c for c in s if c.isdigit() or c in '.-')
    try: return float(s)
    except: return 0.0

# --- CARGA DE DATOS ---
def load_data():
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    for col in ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo", "Banco"]:
        if col not in df.columns: df[col] = "Desconocido"
    
    if not df.empty:
        df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Año"] = df["Fecha_DT"].dt.year
        df["Mes"] = df["Fecha_DT"].dt.strftime('%m - %b')
    return df

# --- INTERFAZ ---
df_raw = load_data()
st.title("🌙 Multi-Bank Cyber Dashboard")



with st.sidebar:
    st.header("📥 Importación Masiva")
    banco_csv = st.radio("Entidad Emisora:", ["Santander", "Cajamar"])
    archivos = st.file_uploader(f"Subir CSV de {banco_csv}", type=["csv"], accept_multiple_files=True)
    
    if archivos and st.button("🚀 Procesar e Importar"):
        datos_subir = []
        for archivo in archivos:
            try:
                lineas = archivo.getvalue().decode("utf-8").splitlines()
                skip_rows = 0
                col_fecha = "Fecha operación" if banco_csv == "Santander" else "Fecha"
                
                for i, line in enumerate(lineas):
                    if col_fecha in line: skip_rows = i; break
                
                archivo.seek(0)
                sep = ';' if ';' in lineas[skip_rows] else ','
                df_new = pd.read_csv(archivo, skiprows=skip_rows, sep=sep, dtype=str, engine='python')
                df_new.columns = df_new.columns.str.strip()
                
                df_new = df_new[[col_fecha, 'Concepto', 'Importe']].copy()
                df_new.columns = ["Fecha", "Descripcion", "Importe"]
                df_new["Tipo"] = np.where(df_new["Importe"].apply(limpiar_importe) < 0, "Gasto", "Ingreso")
                df_new["Categoria"] = "Varios"
                df_new["Es_Fijo"] = "NO"
                df_new["Banco"] = banco_csv
                
                datos_subir.extend(df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo", "Banco"]].values.tolist())
            except Exception as e: st.error(f"Error en {archivo.name}: {e}")
        
        if datos_subir:
            sheet.append_rows(datos_subir); st.success("✅ Importado"); st.rerun()

    st.divider()
    st.header("⚙️ Filtros")
    vista_banco = st.selectbox("Banco a Visualizar", ["Ambos", "Santander", "Cajamar"])
    años = sorted([int(a) for a in df_raw["Año"].dropna().unique() if a >= 2025], reverse=True)
    año_sel = st.selectbox("Año Actual", años if años else [2026])

# FILTRADO
df = df_raw[df_raw["Año"] == año_sel].copy() if not df_raw.empty else pd.DataFrame()
if vista_banco != "Ambos":
    df = df[df["Banco"] == vista_banco]

t1, t2, t3, t4 = st.tabs(["📊 Resumen", "📅 Planificador Fijos", "🤖 Experto IA", "📂 Editor Vivo"])

with t1:
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        ing = df[df["Importe_Num"] > 0]["Importe_Num"].sum()
        gas = abs(df[df["Importe_Num"] < 0]["Importe_Num"].sum())
        with c1: st.markdown(f'<p class="label-led">Ingresos</p><p class="green-led">+{ing:,.2f} €</p>', unsafe_allow_html=True)
        with c2: st.markdown(f'<p class="label-led">Gastos</p><p class="red-led">-{gas:,.2f} €</p>', unsafe_allow_html=True)
        with c3: st.markdown(f'<p class="label-led">Balance</p><p class="blue-led">{(ing-gas):,.2f} €</p>', unsafe_allow_html=True)
        
        st.divider()
        
        if vista_banco == "Ambos":
            st.subheader("📉 Comparativa por Entidad")
            col_s, col_c = st.columns(2)
            with col_s:
                st.write("**Santander**")
                df_s = df[df["Banco"] == "Santander"].groupby(["Mes", "Tipo"])["Importe_Num"].sum().abs().reset_index()
                # FIX: Añadimos 'key' única para evitar DuplicateElementId
                st.plotly_chart(px.bar(df_s, x="Mes", y="Importe_Num", color="Tipo", barmode="group", template="plotly_dark", color_discrete_map={"Ingreso": "#2ecc71", "Gasto": "#e63946"}), use_container_width=True, key="chart_santander")
            with col_c:
                st.write("**Cajamar**")
                df_c = df[df["Banco"] == "Cajamar"].groupby(["Mes", "Tipo"])["Importe_Num"].sum().abs().reset_index()
                # FIX: Añadimos 'key' única
                st.plotly_chart(px.bar(df_c, x="Mes", y="Importe_Num", color="Tipo", barmode="group", template="plotly_dark", color_discrete_map={"Ingreso": "#2ecc71", "Gasto": "#e63946"}), use_container_width=True, key="chart_cajamar")
        else:
            st.subheader(f"📈 Evolución {vista_banco}")
            df_m = df.groupby(["Mes", "Tipo"])["Importe_Num"].sum().abs().reset_index()
            st.plotly_chart(px.bar(df_m, x="Mes", y="Importe_Num", color="Tipo", barmode="group", template="plotly_dark", color_discrete_map={"Ingreso": "#2ecc71", "Gasto": "#e63946"}), use_container_width=True, key="chart_single")

with t2:
    st.header("📅 Planificador de Fijos")
    fijos = df[(df["Es_Fijo"].str.upper() == "SÍ") & (df["Importe_Num"] < 0)]
    presu = fijos.drop_duplicates(subset=['Descripcion', 'Banco'], keep='last')
    st.markdown(f'<p class="label-led">Suelo Mensual ({vista_banco})</p><p class="blue-led">{abs(presu["Importe_Num"].sum()):,.2f} €</p>', unsafe_allow_html=True)
    st.dataframe(presu[["Banco", "Descripcion", "Importe", "Categoria"]], use_container_width=True)

with t4:
    st.header("📂 Editor Vivo")
    if not df.empty:
        df_editor = df[["Fecha", "Banco", "Categoria", "Descripcion", "Importe_Num", "Es_Fijo"]].copy()
        
        edited_df = st.data_editor(
            df_editor,
            column_config={
                "Importe_Num": st.column_config.NumberColumn("Importe (€)", format="%.2f", disabled=False),
                "Categoria": st.column_config.SelectboxColumn("Categoría", options=["Varios", "Vivienda", "Ocio", "Alimentación", "Suscripciones", "Transporte", "Salud"], disabled=False),
                "Descripcion": st.column_config.TextColumn("Descripción", disabled=False),
                "Es_Fijo": st.column_config.SelectboxColumn("Fijo", options=["SÍ", "NO"], disabled=False),
                "Banco": st.column_config.TextColumn("Entidad", disabled=True),
                "Fecha": st.column_config.TextColumn("Fecha", disabled=True)
            },
            use_container_width=True,
            num_rows="fixed",
            key="main_data_editor" # Key única para el editor
        )

        if st.button("💾 Guardar Cambios"):
            with st.spinner("Sincronizando..."):
                try:
                    for idx, row in edited_df.iterrows():
                        actual_row = idx + 2
                        rango = f"C{actual_row}:F{actual_row}"
                        nuevos_datos = [[row["Categoria"], row["Descripcion"], str(row["Importe_Num"]), row["Es_Fijo"]]]
                        sheet.update(rango, nuevos_datos)
                    st.success("✅ ¡Hecho!"); st.rerun()
                except Exception as e: st.error(f"Error: {e}")
