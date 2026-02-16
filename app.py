import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Mi Contabilidad Nube", layout="wide", page_icon="☁️")

# --- CONEXIÓN CON GOOGLE SHEETS ---
def conectar_google_sheets():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("Contabilidad_App").sheet1
    return sheet

try:
    sheet = conectar_google_sheets()
except Exception as e:
    st.error("⚠️ Error de conexión. Revisa tus Secrets en la configuración de Streamlit.")
    st.stop()

# --- FUNCIONES ---
def load_data():
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    expected_cols = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = ""
    return df

def save_entry(fecha, tipo, categoria, descripcion, monto, es_fijo):
    fecha_str = fecha.strftime("%Y-%m-%d")
    es_fijo_str = "SÍ" if es_fijo else "NO"
    row = [fecha_str, tipo, categoria, descripcion, monto, es_fijo_str]
    sheet.append_row(row)

# --- BARRA LATERAL: INGRESO MANUAL ---
st.sidebar.header("📝 Nuevo Movimiento")

with st.sidebar.form("entry_form", clear_on_submit=True):
    fecha = st.date_input("Fecha", datetime.today())
    tipo = st.selectbox("Tipo", ["Gasto", "Ingreso"])
    categoria = st.text_input("Categoría (ej: Supermercado)")
    descripcion = st.text_input("Descripción")
    monto = st.number_input("Monto (€)", min_value=0.0, format="%.2f")
    es_fijo = st.checkbox("¿Es FIJO mensual?")
    
    submitted = st.form_submit_button("Guardar Manual")

    if submitted:
        if monto > 0:
            monto_final = -monto if tipo == "Gasto" else monto
            save_entry(fecha, tipo, categoria, descripcion, monto_final, es_fijo)
            st.success("✅ Guardado")
            st.rerun()

# --- BARRA LATERAL: IMPORTAR CSV (VERSIÓN INTELIGENTE) ---
st.sidebar.markdown("---")
st.sidebar.header("📥 Importar CSV")
uploaded_file = st.sidebar.file_uploader("Sube tu archivo aquí", type=["csv"])

if uploaded_file is not None:
    if st.sidebar.button("Procesar e Importar"):
        try:
            # 1. INTENTO DE LECTURA (UTF-8 con BOM o Latin-1)
            uploaded_file.seek(0)
            try:
                df_upload = pd.read_csv(uploaded_file, encoding='utf-8-sig', sep=None, engine='python')
            except:
                uploaded_file.seek(0)
                df_upload = pd.read_csv(uploaded_file, encoding='latin-1', sep=';')
            
            # 2. LIMPIEZA DE NOMBRES DE COLUMNAS
            df_upload.columns = df_upload.columns.str.strip().str.replace('ï»¿', '')
            
            columnas_necesarias = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
            
            # Verificamos si están las columnas (ignorando mayúsculas/minúsculas si fuera necesario)
            if not all(col in df_upload.columns for col in columnas_necesarias):
                st.sidebar.error(f"Error de formato. Columnas encontradas: {list(df_upload.columns)}")
            else:
                # 3. LIMPIEZA INTELIGENTE DE DATOS
                
                # A) Limpiar columna MONTO (quitar ?, €, y arreglar comas)
                df_upload["Monto"] = df_upload["Monto"].astype(str)
                # Quitamos símbolos raros
                df_upload["Monto"] = df_upload["Monto"].str.replace('?', '', regex=False)
                df_upload["Monto"] = df_upload["Monto"].str.replace('€', '', regex=False)
                # Quitamos punto de miles (ej: 1.800 -> 1800)
                df_upload["Monto"] = df_upload["Monto"].str.replace('.', '', regex=False)
                # Cambiamos coma decimal por punto (ej: 30,79 -> 30.79)
                df_upload["Monto"] = df_upload["Monto"].str.replace(',', '.', regex=False)
                # Convertimos a número
                df_upload["Monto"] = pd.to_numeric(df_upload["Monto"], errors='coerce')

                # B) INTELIGENCIA DE SIGNOS (Gasto = Negativo, Ingreso = Positivo)
                # Esto arregla si el Excel venía sin el signo menos
                df_upload["Monto"] = np.where(
                    df_upload["Tipo"].str.lower().str.contains("gasto", na=False), 
                    -1 * df_upload["Monto"].abs(),  # Forzar negativo
                    df_upload["Monto"].abs()        # Forzar positivo
                )

                # C) Formatear FECHA
                df_upload["Fecha"] = pd.to_datetime(df_upload["Fecha"], dayfirst=True, errors='coerce').dt.strftime("%Y-%m-%d")
                
                # D) Limpiar filas vacías o corruptas
                df_upload = df_upload.dropna(subset=['Fecha', 'Monto'])

                # 4. SUBIR A GOOGLE SHEETS
                datos_para_subir = df_upload[columnas_necesarias].values.tolist()
                
                if len(datos_para_subir) > 0:
                    sheet.append_rows(datos_para_subir)
                    st.sidebar.success(f"✅ ¡{len(datos_para_subir)} movimientos importados correctamente!")
                    st.rerun()
                else:
                    st.sidebar.warning("El archivo parece vacío o los datos no son válidos.")
                
        except Exception as e:
            st.sidebar.error(f"Ocurrió un error técnico: {e}")

# --- CUERPO PRINCIPAL ---
df = load_data()

st.title("☁️ Contabilidad en la Nube")

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📅 Planificación Fija", "📂 Datos"])

with tab1:
    if not df.empty and "Monto" in df.columns:
        # Asegurar tipos numéricos para cálculos
        df["Monto"] = pd.to_numeric(df["Monto"], errors='coerce').fillna(0)
        
        total_balance = df["Monto"].sum()
        col1, col2, col3 = st.columns(3)
        col1.metric("Balance Total", f"{total_balance:.2f} €")
        col2.metric("Ingresos", f"{df[df['Monto'] > 0]['Monto'].sum():.2f} €")
        col3.metric("Gastos", f"{df[df['Monto'] < 0]['Monto'].sum():.2f} €")
        
        st.divider()
        
        # Gráficos
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors='coerce')
        if not df["Fecha"].isnull().all():
            df_sorted = df.sort_values("Fecha")
            st.plotly_chart(px.line(df_sorted, x="Fecha", y="Monto", color="Tipo", title="Evolución Temporal"), use_container_width=True)

with tab2:
    if not df.empty and "Es_Fijo" in df.columns:
        # Filtramos por texto "SÍ" (o variaciones por si acaso)
        fijos = df[(df["Es_Fijo"].astype(str).str.upper() == "SÍ") & (df["Monto"] < 0)]
        
        if not fijos.empty:
            total_fijo = fijos["Monto"].sum()
            st.metric("Gasto Fijo Total Acumulado", f"{total_fijo:.2f} €")
            st.dataframe(fijos, use_container_width=True)
        else:
            st.info("No hay gastos marcados como fijos.")

with tab3:
    st.dataframe(df, use_container_width=True)
    
    # Botón plantilla
    plantilla = pd.DataFrame(columns=["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"])
    csv_plantilla = plantilla.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Descargar Plantilla CSV vacía", csv_plantilla, "plantilla_importacion.csv", "text/csv")
