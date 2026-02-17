import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import google.generativeai as genai

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Finanzas Cyber Dashboard", layout="wide", page_icon="🌙")

# --- CSS: MODO OSCURO TOTAL Y COLORES LED ---
st.markdown("""
<style>
    .stApp { background-color: #000000 !important; color: #FFFFFF !important; }
    h1, h2, h3, p, span, label { color: #FFFFFF !important; }
    [data-testid="metric-container"] {
        background-color: #111111; border: 1px solid #333333; padding: 20px; border-radius: 12px; text-align: center;
    }
    .green-led { color: #2ecc71 !important; font-size: 2.5rem; font-weight: 800; }
    .red-led { color: #e63946 !important; font-size: 2.5rem; font-weight: 800; }
    .blue-led { color: #3498db !important; font-size: 2.5rem; font-weight: 800; }
    .label-led { color: #AAAAAA !important; font-size: 1rem; text-transform: uppercase; }
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

# --- IA: EXPERTO FINANCIERO ---
def llamar_experto_ia(contexto):
    try:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"Eres un experto financiero. Analiza estos datos: {contexto}. Sé breve y profesional."
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error en IA: {e}"

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
    if not df.empty:
        df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Año"] = df["Fecha_DT"].dt.year
        df["Mes"] = df["Fecha_DT"].dt.strftime('%m - %b')
    return df

# --- INTERFAZ ---
df_raw = load_data()
st.title("🌙 Santander Cyber Dashboard")

with st.sidebar:
    st.header("📥 Importación Masiva")
    archivos = st.file_uploader("Sube uno o varios CSV", type=["csv"], accept_multiple_files=True)
    if archivos:
        if st.button("🚀 Procesar e Importar Todo"):
            datos_para_subir = []
            for archivo in archivos:
                try:
                    lineas = archivo.getvalue().decode("utf-8").splitlines()
                    skip_rows = 0
                    for i, line in enumerate(lineas):
                        if "Fecha operación" in line: skip_rows = i; break
                    archivo.seek(0)
                    sep = ';' if ';' in lineas[skip_rows] else ','
                    df_new = pd.read_csv(archivo, skiprows=skip_rows, sep=sep, dtype=str, engine='python')
                    df_new.columns = df_new.columns.str.strip()
                    df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
                    df_new.columns = ["Fecha", "Descripcion", "Importe"]
                    df_new["Tipo"] = np.where(df_new["Importe"].apply(limpiar_importe) < 0, "Gasto", "Ingreso")
                    df_new["Categoria"] = "Varios"; df_new["Es_Fijo"] = "NO"
                    datos_para_subir.extend(df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]].values.tolist())
                except Exception as e: st.error(f"Error en {archivo.name}: {e}")
            if datos_para_subir:
                sheet.append_rows(datos_para_subir); st.success("✅ ¡Hecho!"); st.rerun()

    st.divider()
    años = sorted([int(a) for a in df_raw["Año"].dropna().unique() if a >= 2025], reverse=True)
    año_sel = st.selectbox("Año Actual", años if años else [2026])

df = df_raw[df_raw["Año"] == año_sel].copy() if not df_raw.empty else pd.DataFrame()

t1, t2, t3, t4 = st.tabs(["📊 Resumen Ejecutivo", "📅 Planificador Fijos", "🤖 Experto IA", "📂 Editor Vivo"])

with t1:
    if not df.empty:
        ing = df[df["Importe_Num"] > 0]["Importe_Num"].sum()
        gas = abs(df[df["Importe_Num"] < 0]["Importe_Num"].sum())
        bal = ing - gas
        c1, c2, c3 = st.columns(3)
        c1.markdown(f'<p class="label-led">Ingresos</p><p class="green-led">{ing:,.2f} €</p>', unsafe_allow_html=True)
        c2.markdown(f'<p class="label-led">Gastos</p><p class="red-led">{gas:,.2f} €</p>', unsafe_allow_html=True)
        c3.markdown(f'<p class="label-led">Balance</p><p class="blue-led">{bal:,.2f} €</p>', unsafe_allow_html=True)
        st.divider()
        g1, g2 = st.columns([2, 1])
        with g1:
            df_m = df.groupby(["Mes", "Tipo"])["Importe_Num"].sum().abs().reset_index()
            fig = px.bar(df_m, x="Mes", y="Importe_Num", color="Tipo", barmode="group", template="plotly_dark", color_discrete_map={"Ingreso": "#2ecc71", "Gasto": "#e63946"})
            st.plotly_chart(fig, use_container_width=True)
        with g2:
            df_p = df[df["Importe_Num"] < 0].copy(); df_p["Val"] = df_p["Importe_Num"].abs()
            st.plotly_chart(px.pie(df_p, values="Val", names="Categoria", hole=0.5, template="plotly_dark"), use_container_width=True)

with t2:
    st.header("📋 Suelo de Gastos Fijos")
    if not df.empty:
        fijos = df[(df["Es_Fijo"].str.upper() == "SÍ") & (df["Importe_Num"] < 0)]
        presu = fijos.drop_duplicates(subset=['Descripcion'], keep='last')
        st.markdown(f'<p class="label-led">Necesidad Mensual</p><p class="blue-led">{abs(presu["Importe_Num"].sum()):,.2f} €</p>', unsafe_allow_html=True)
        st.dataframe(presu[["Descripcion", "Importe", "Categoria"]], use_container_width=True)

with t3:
    st.header("🤖 Consultoría Experto Gem")
    if st.button("✨ Ejecutar Análisis Estratégico"):
        with st.spinner("Analizando..."):
            resumen = f"Ingresos: {ing}€, Gastos: {gas}€, Balance: {bal}€"
            st.markdown(f"### 💡 Informe:\n{llamar_experto_ia(resumen)}")

# --- TAB 4: EDITOR VIVO (DESBLOQUEO DEFINITIVO) ---
with t4:
    st.header("📂 Editor de Datos")
    st.write("Haz doble clic en cualquier celda para editar (incluido el Importe).")
    if not df.empty:
        # Aseguramos que Importe_Num sea flotante para el NumberColumn
        df_editor = df[["Fecha", "Categoria", "Descripcion", "Importe_Num", "Es_Fijo"]].copy()
        
        cats = ["Varios", "Vivienda", "Ocio", "Suministros", "Alimentación", "Transporte", "Suscripciones", "Salud"]
        
        edited_df = st.data_editor(
            df_editor,
            column_config={
                "Importe_Num": st.column_config.NumberColumn(
                    "Importe (€)", 
                    help="Cantidad del movimiento",
                    format="%.2f", 
                    disabled=False  # <--- DESBLOQUEADO
                ),
                "Categoria": st.column_config.SelectboxColumn("Categoría", options=cats, disabled=False),
                "Descripcion": st.column_config.TextColumn("Descripción", disabled=False),
                "Es_Fijo": st.column_config.SelectboxColumn("Fijo", options=["SÍ", "NO"], disabled=False),
                "Fecha": st.column_config.TextColumn("Fecha", disabled=True)
            },
            use_container_width=True,
            num_rows="fixed"
        )

        if st.button("💾 Guardar cambios en la Nube"):
            with st.spinner("Sincronizando..."):
                try:
                    # Obtenemos los índices del filtro actual para actualizar las filas correctas
                    for idx, row in edited_df.iterrows():
                        actual_row = idx + 2
                        rango = f"C{actual_row}:F{actual_row}"
                        # Convertimos el número de vuelta a string para Google Sheets
                        nuevos_datos = [[row["Categoria"], row["Descripcion"], str(row["Importe_Num"]), row["Es_Fijo"]]]
                        sheet.update(rango, nuevos_datos)
                    st.success("✅ ¡Todo actualizado!")
                    st.rerun()
                except Exception as e: st.error(f"Error: {e}")
