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
    .stApp { background-color: #000000 !important; color: #FFFFFF !important; }
    h1, h2, h3, p, span, label { color: #FFFFFF !important; }
    [data-testid="metric-container"] {
        background-color: #111111;
        border: 1px solid #333333;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
    }
    .green-led { color: #2ecc71 !important; font-size: 2.5rem; font-weight: 800; text-shadow: 0 0 10px #2ecc7144; }
    .red-led { color: #e63946 !important; font-size: 2.5rem; font-weight: 800; text-shadow: 0 0 10px #e6394644; }
    .blue-led { color: #3498db !important; font-size: 2.5rem; font-weight: 800; text-shadow: 0 0 10px #3498db44; }
    .label-led { color: #AAAAAA !important; font-size: 1rem; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 1px; }
    .stTabs [data-baseweb="tab-list"] { background-color: #000000; }
    .stTabs [data-baseweb="tab"] { color: #888888 !important; }
    .stTabs [aria-selected="true"] { color: #FFFFFF !important; border-bottom-color: #3498db !important; }
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
        # Añadimos un índice real para poder actualizar filas específicas en el futuro
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
    archivos = st.file_uploader("Sube uno o varios CSV del Santander", type=["csv"], accept_multiple_files=True)
    
    if archivos:
        if st.button("🚀 Procesar e Importar Todo"):
            datos_para_subir = []
            for archivo in archivos:
                try:
                    lineas = archivo.getvalue().decode("utf-8").splitlines()
                    skip_rows = 0
                    for i, line in enumerate(lineas):
                        if "Fecha operación" in line:
                            skip_rows = i
                            break
                    archivo.seek(0)
                    sep = ';' if ';' in lineas[skip_rows] else ','
                    df_new = pd.read_csv(archivo, skiprows=skip_rows, sep=sep, dtype=str, engine='python')
                    df_new.columns = df_new.columns.str.strip()
                    df_new = df_new[['Fecha operación', 'Concepto', 'Importe']].copy()
                    df_new.columns = ["Fecha", "Descripcion", "Importe"]
                    df_new["Tipo"] = np.where(df_new["Importe"].apply(limpiar_importe) < 0, "Gasto", "Ingreso")
                    df_new["Categoria"] = "Varios"
                    df_new["Es_Fijo"] = "NO"
                    df_final = df_new[["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]]
                    datos_para_subir.extend(df_final.values.tolist())
                except Exception as e:
                    st.error(f"Error en {archivo.name}: {e}")

            if datos_para_subir:
                sheet.append_rows(datos_para_subir)
                st.success(f"✅ ¡{len(datos_para_subir)} movimientos añadidos!")
                st.rerun()

    st.divider()
    st.header("📅 Histórico")
    años = sorted([int(a) for a in df_raw["Año"].dropna().unique() if a >= 2025], reverse=True)
    año_sel = st.selectbox("Año Actual", años if años else [2026])

# Filtramos los datos para la vista actual
df = df_raw[df_raw["Año"] == año_sel].copy() if not df_raw.empty else pd.DataFrame()

t1, t2, t3, t4 = st.tabs(["📊 Resumen Ejecutivo", "📅 Planificador Fijos", "🤖 Experto IA", "📂 Editor Vivo"])

# --- TAB 1: RESUMEN ---
with t1:
    if not df.empty:
        ing = df[df["Importe_Num"] > 0]["Importe_Num"].sum()
        gas = abs(df[df["Importe_Num"] < 0]["Importe_Num"].sum())
        bal = ing - gas
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(f'<p class="label-led">Ingresos</p><p class="green-led">{ing:,.2f} €</p>', unsafe_allow_html=True)
        with c2: st.markdown(f'<p class="label-led">Gastos</p><p class="red-led">{gas:,.2f} €</p>', unsafe_allow_html=True)
        with c3: st.markdown(f'<p class="label-led">Balance</p><p class="blue-led">{bal:,.2f} €</p>', unsafe_allow_html=True)
        st.divider()
        g1, g2 = st.columns([2, 1])
        with g1:
            df_mes = df.groupby(["Mes", "Tipo"])["Importe_Num"].sum().abs().reset_index()
            fig = px.bar(df_mes, x="Mes", y="Importe_Num", color="Tipo", barmode="group",
                         template="plotly_dark", color_discrete_map={"Ingreso": "#2ecc71", "Gasto": "#e63946"})
            st.plotly_chart(fig, use_container_width=True)
        with g2:
            df_pie = df[df["Importe_Num"] < 0].copy()
            df_pie["Val"] = df_pie["Importe_Num"].abs()
            st.plotly_chart(px.pie(df_pie, values="Val", names="Categoria", hole=0.5, template="plotly_dark"), use_container_width=True)

# --- TAB 2: PLANIFICADOR ---
with t2:
    st.header("📋 Suelo de Gastos Fijos")
    if not df.empty:
        fijos = df[(df["Es_Fijo"].str.upper() == "SÍ") & (df["Importe_Num"] < 0)]
        presupuesto = fijos.drop_duplicates(subset=['Descripcion'], keep='last')
        total_f = abs(presupuesto['Importe_Num'].sum())
        st.markdown(f'<p class="label-led">Necesidad Mensual</p><p class="blue-led">{total_f:,.2f} €</p>', unsafe_allow_html=True)
        st.dataframe(presupuesto[["Descripcion", "Importe", "Categoria"]], use_container_width=True)

# --- TAB 3: IA ---
with t3:
    st.header("🤖 Consultoría Experto Gem")
    if st.button("✨ Ejecutar Análisis Estratégico"):
        with st.spinner("Analizando..."):
            if not df.empty:
                resumen = f"Ingresos: {ing}€, Gastos: {gas}€, Balance: {bal}€"
                analisis = llamar_experto_ia(resumen)
                st.markdown(f"### 💡 Informe:\n{analisis}")

# --- TAB 4: EDITOR VIVO (CORREGIDO Y TOTALMENTE EDITABLE) ---
with t4:
    st.header("📂 Editor de Datos")
    st.write("Modifica cualquier celda de **Categoría, Descripción, Importe o Fijo**. El botón de abajo guardará todo el bloque actual.")
    
    if not df.empty:
        # Definimos las categorías para el desplegable
        cats_list = ["Varios", "Vivienda", "Ocio", "Suministros", "Alimentación", "Transporte", "Suscripciones", "Salud"]
        
        # Seleccionamos las columnas para editar. 
        # IMPORTANTE: No deshabilitamos nada excepto 'Fecha' si quieres seguridad.
        df_editor = df[["Fecha", "Categoria", "Descripcion", "Importe", "Es_Fijo"]].copy()
        
        # Configuramos el editor asegurando que las columnas sean editables
        edited_df = st.data_editor(
            df_editor,
            column_config={
                "Categoria": st.column_config.SelectboxColumn("Categoría", options=cats_list, disabled=False),
                "Descripcion": st.column_config.TextColumn("Descripción", disabled=False),
                "Importe": st.column_config.TextColumn("Importe (Cant.)", disabled=False),
                "Es_Fijo": st.column_config.SelectboxColumn("Fijo", options=["SÍ", "NO"], disabled=False),
                "Fecha": st.column_config.TextColumn("Fecha", disabled=True) # Mantenemos Fecha bloqueada por seguridad de formato
            },
            use_container_width=True,
            num_rows="fixed" # Mantenemos el número de filas para no desajustar el Excel
        )

        if st.button("💾 Guardar cambios de este año en la Nube"):
            with st.spinner("Actualizando Google Sheets..."):
                try:
                    # Obtenemos los índices originales para saber dónde escribir
                    # Como df_raw es la hoja completa y 'df' es el filtro, calculamos el rango:
                    indices_originales = df.index + 2 # +2 porque Sheets empieza en 1 y la fila 1 es cabecera
                    
                    # Para simplificar y asegurar que NO QUITE NADA, actualizamos fila a fila 
                    # los cambios realizados en el bloque filtrado.
                    batch_data = []
                    for idx, row in edited_df.iterrows():
                        actual_row_in_sheet = idx + 2
                        # Definimos el rango de la fila completa de la hoja (A a F)
                        # Fecha(A), Tipo(B), Cat(C), Desc(D), Imp(E), Fijo(F)
                        # Pero solo actualizamos las columnas que hemos editado: C, D, E, F
                        rango_celdas = f"C{actual_row_in_sheet}:F{actual_row_in_sheet}"
                        
                        # Los datos deben ser una lista de listas
                        nuevos_valores = [[row["Categoria"], row["Descripcion"], row["Importe"], row["Es_Fijo"]]]
                        sheet.update(rango_celdas, nuevos_valores)
                    
                    st.success("✅ ¡Base de datos sincronizada con éxito!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
    else:
        st.info("No hay datos cargados para editar.")
