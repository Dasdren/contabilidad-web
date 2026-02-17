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

# CSS: MODO OSCURO TOTAL Y COLORES LED
st.markdown("""
<style>
    .stApp { background-color: #000000 !important; color: #FFFFFF !important; }
    [data-testid="metric-container"] {
        background-color: #111111; border: 1px solid #333333; padding: 20px; border-radius: 12px;
    }
    .green-led { color: #2ecc71 !important; font-size: 2.2rem; font-weight: 800; }
    .red-led { color: #e63946 !important; font-size: 2.2rem; font-weight: 800; }
    .blue-led { color: #3498db !important; font-size: 2.2rem; font-weight: 800; }
    .label-led { color: #AAAAAA !important; font-size: 0.9rem; text-transform: uppercase; }
    .stTabs [data-baseweb="tab-list"] { background-color: #000000; }
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
    except Exception as e:
        st.error(f"⚠️ Error de conexión: {e}")
        st.stop()

sheet = conectar_google_sheets()

# --- LIMPIEZA Y CARGA ---
def limpiar_importe(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('−', '-')
    if ',' in s: s = s.replace('.', '').replace(',', '.')
    s = "".join(c for c in s if c.isdigit() or c in '.-')
    try: return float(s)
    except: return 0.0

def load_data():
    try:
        records = sheet.get_all_records()
        if not records: return pd.DataFrame()
        df = pd.DataFrame(records)
        # Asegurar que todas las columnas existan
        for col in ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo", "Banco"]:
            if col not in df.columns: df[col] = "Desconocido"
        
        df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Año"] = df["Fecha_DT"].dt.year
        df["Mes"] = df["Fecha_DT"].dt.strftime('%m - %b')
        return df
    except:
        return pd.DataFrame()

# --- CARGA INICIAL ---
df_raw = load_data()

# --- SIDEBAR: IMPORTACIÓN Y FILTROS ---
with st.sidebar:
    st.header("📥 Importación")
    banco_csv = st.radio("Entidad:", ["Santander", "Cajamar"])
    archivos = st.file_uploader("Subir CSVs", type=["csv"], accept_multiple_files=True)
    
    if archivos and st.button("🚀 Importar"):
        datos_nuevos = []
        for arc in archivos:
            try:
                lineas = arc.getvalue().decode("utf-8").splitlines()
                skip = 0
                col_f = "Fecha operación" if banco_csv == "Santander" else "Fecha"
                for i, l in enumerate(lineas):
                    if col_f in l: skip = i; break
                arc.seek(0)
                df_n = pd.read_csv(arc, skiprows=skip, sep=None, engine='python', dtype=str)
                df_n.columns = df_n.columns.str.strip()
                df_n = df_n[[col_f, 'Concepto', 'Importe']].copy()
                df_n.columns = ["Fecha", "Descripcion", "Importe"]
                df_n["Tipo"] = np.where(df_n["Importe"].apply(limpiar_importe) < 0, "Gasto", "Ingreso")
                df_n["Categoria"] = "Varios"; df_n["Es_Fijo"] = "NO"; df_n["Banco"] = banco_csv
                datos_nuevos.extend(df_n[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo", "Banco"]].values.tolist())
            except Exception as e: st.error(f"Error en {arc.name}: {e}")
        
        if datos_nuevos:
            sheet.append_rows(datos_nuevos)
            st.success("✅ ¡Importados!")
            st.rerun()

    st.divider()
    st.header("⚙️ Filtros")
    vista_banco = st.selectbox("Banco:", ["Ambos", "Santander", "Cajamar"])
    
    # Detectar años disponibles o usar el actual
    lista_años = [2026]
    if not df_raw.empty:
        lista_años = sorted(df_raw["Año"].dropna().unique().astype(int), reverse=True)
    año_sel = st.selectbox("Año:", lista_años)

# --- PROCESAMIENTO DE FILTROS ---
if not df_raw.empty:
    df_filtrado = df_raw[df_raw["Año"] == año_sel].copy()
    if vista_banco != "Ambos":
        df_filtrado = df_filtrado[df_filtrado["Banco"] == vista_banco]
else:
    df_filtrado = pd.DataFrame()

st.title("🌙 Multi-Bank Cyber Dashboard")



t1, t2, t3, t4 = st.tabs(["📊 Resumen", "📅 Planificador", "🤖 IA Experto", "📂 Editor Vivo"])

# --- TAB 1: RESUMEN ---
with t1:
    if df_filtrado.empty:
        st.warning(f"⚠️ No hay datos para el año {año_sel} ({vista_banco}).")
        st.info("Sube archivos CSV en la barra lateral para rellenar el historial.")
    else:
        ing = df_filtrado[df_filtrado["Importe_Num"] > 0]["Importe_Num"].sum()
        gas = abs(df_filtrado[df_filtrado["Importe_Num"] < 0]["Importe_Num"].sum())
        bal = ing - gas
        
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(f'<p class="label-led">Ingresos</p><p class="green-led">+{ing:,.2f} €</p>', unsafe_allow_html=True)
        with c2: st.markdown(f'<p class="label-led">Gastos</p><p class="red-led">-{gas:,.2f} €</p>', unsafe_allow_html=True)
        with c3: st.markdown(f'<p class="label-led">Balance</p><p class="blue-led">{bal:,.2f} €</p>', unsafe_allow_html=True)

        st.divider()

        def dibujar_grafica(data, titulo, k):
            if not data.empty:
                df_g = data.groupby(["Mes", "Tipo"])["Importe_Num"].sum().abs().reset_index()
                fig = px.bar(df_g, x="Mes", y="Importe_Num", color="Tipo", barmode="group",
                             title=titulo, template="plotly_dark", color_discrete_map={"Ingreso": "#2ecc71", "Gasto": "#e63946"})
                fig.update_layout(paper_bgcolor='#111111', plot_bgcolor='#111111')
                st.plotly_chart(fig, use_container_width=True, key=k)

        if vista_banco == "Ambos":
            col_l, col_r = st.columns(2)
            with col_l: dibujar_grafica(df_filtrado[df_filtrado["Banco"]=="Santander"], "SANTANDER", "gs")
            with col_r: dibujar_grafica(df_filtrado[df_filtrado["Banco"]=="Cajamar"], "CAJAMAR", "gc")
        else:
            dibujar_grafica(df_filtrado, f"MOVIMIENTOS {vista_banco}", "gt")

# --- TAB 2: PLANIFICADOR ---
with t2:
    st.header("📋 Suelo Mensual")
    if not df_filtrado.empty:
        fijos = df_filtrado[(df_filtrado["Es_Fijo"].str.upper() == "SÍ") & (df_filtrado["Importe_Num"] < 0)]
        presu = fijos.drop_duplicates(subset=['Descripcion', 'Banco'], keep='last')
        st.markdown(f'<p class="label-led">Suelo Estimado</p><p class="blue-led">{abs(presu["Importe_Num"].sum()):,.2f} €</p>', unsafe_allow_html=True)
        st.dataframe(presu[["Banco", "Descripcion", "Importe_Num", "Categoria"]], use_container_width=True)
    else:
        st.info("Marca gastos como fijos en el Editor para verlos aquí.")

# --- TAB 3: IA EXPERTO ---
with t3:
    st.header("🤖 Consultoría Gem IA")
    if st.button("✨ Ejecutar Análisis"):
        if not df_filtrado.empty:
            with st.spinner("Analizando..."):
                genai.configure(api_key=st.secrets["gemini_api_key"])
                model = genai.GenerativeModel('gemini-1.5-flash')
                ctx = f"Ingresos: {ing}€, Gastos: {gas}€. Balance: {bal}€."
                res = model.generate_content(f"Asesor financiero: analiza estos datos {ctx}")
                st.markdown(f"### 💡 Informe:\n{res.text}")
        else:
            st.error("No hay datos para analizar.")

# --- TAB 4: EDITOR VIVO (IMPORTES 100% EDITABLES) ---
with t4:
    st.header("📂 Editor de Datos")
    if not df_filtrado.empty:
        # Usamos el DF original para que los cambios se guarden en la fila correcta
        df_ed = df_filtrado[["Fecha", "Banco", "Categoria", "Descripcion", "Importe_Num", "Es_Fijo"]].copy()
        
        res_ed = st.data_editor(
            df_ed,
            column_config={
                "Importe_Num": st.column_config.NumberColumn("Importe (€)", format="%.2f", disabled=False),
                "Categoria": st.column_config.SelectboxColumn("Cat", options=["Varios", "Vivienda", "Ocio", "Alimentación", "Salud", "Suscripciones"], disabled=False),
                "Es_Fijo": st.column_config.SelectboxColumn("Fijo", options=["SÍ", "NO"], disabled=False),
                "Descripcion": st.column_config.TextColumn("Concepto", disabled=False)
            },
            use_container_width=True, key="cyber_editor"
        )
        
        if st.button("💾 Sincronizar Cambios"):
            with st.spinner("Guardando..."):
                for idx, row in res_ed.iterrows():
                    # idx es el índice del DataFrame original (df_raw)
                    fila_excel = idx + 2
                    sheet.update(f"C{fila_excel}:F{fila_excel}", [[row["Categoria"], row["Descripcion"], str(row["Importe_Num"]), row["Es_Fijo"]]])
                st.success("¡Sincronizado!"); st.rerun()
    else:
        st.write("Sube datos para habilitar el editor.")
