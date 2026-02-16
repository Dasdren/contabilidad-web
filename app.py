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

# --- BARRA LATERAL: IMPORTAR CSV ---
st.sidebar.markdown("---")
st.sidebar.header("📥 Importar CSV")
uploaded_file = st.sidebar.file_uploader("Sube tu archivo aquí", type=["csv"])

if uploaded_file is not None:
    if st.sidebar.button("Procesar e Importar"):
        try:
            # 1. INTENTO DE LECTURA (Lógica simplificada para evitar errores de sintaxis)
            uploaded_file.seek(0)
            try:
                # Intentamos leer con motor python que es más flexible
                df_upload = pd.read_csv(uploaded_file, encoding='utf-8-sig', sep=None, engine='python')
            except:
                # Si falla, probamos la codificación de Excel típica
                uploaded_file.seek(0)
                df_upload = pd.read_csv(uploaded_file, encoding='latin-1', sep=';')
            
            # 2. LIMPIEZA DE NOMBRES DE COLUMNAS
            df_upload.columns = df_upload.columns.str.strip().str.replace('ï»¿', '')
            
            columnas_necesarias = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
            
            # Verificamos columnas
            if not all(col in df_upload.columns for col in columnas_necesarias):
                st.sidebar.error(f"Error de formato. Columnas encontradas: {list(df_upload.columns)}")
            else:
                # 3. LIMPIEZA DE DATOS
                
                # A) Limpieza de Dinero (Quitar ?, €, puntos de miles y arreglar coma decimal)
                df_upload["Monto"] = df_upload["Monto"].astype(str)
                df_upload["Monto"] = df_upload["Monto"].str.replace('?', '', regex=False)
                df_upload["Monto"] = df_upload["Monto"].str.replace('€', '', regex=False)
                df_upload["Monto"] = df_upload["Monto"].str.replace('.', '', regex=False) # Quitar punto de miles
                df_upload["Monto"] = df_upload["Monto"].str.replace(',', '.', regex=False) # Coma a punto decimal
                df_upload["Monto"] = pd.to_numeric(df_upload["Monto"], errors='coerce')

                # B) Inteligencia de Signos (Gasto negativo, Ingreso positivo)
                df_upload["Monto"] = np.where(
                    df_upload["Tipo"].str.lower().str.contains("gasto", na=False), 
                    -1 * df_upload["Monto"].abs(),
                    df_upload["Monto"].abs()
                )

                # C) Arreglo de ES_FIJO (Normalizar SI/SÍ)
                df_upload["Es_Fijo"] = df_upload["Es_Fijo"].astype(str).str.upper().str.strip()
                df_upload["Es_Fijo"] = df_upload["Es_Fijo"].replace(['SI', 'YES', 'S'], 'SÍ')

                # D) Fecha
                df_upload["Fecha"] = pd.to_datetime(df_upload["Fecha"], dayfirst=True, errors='coerce').dt.strftime("%Y-%m-%d")
                
                # Filtrar errores
                df_upload = df_upload.dropna(subset=['Fecha', 'Monto'])

                # 4. SUBIR
                datos_para_subir = df_upload[columnas_necesarias].values.tolist()
                
                if len(datos_para_subir) > 0:
                    sheet.append_rows(datos_para_subir)
                    st.sidebar.success(f"✅ ¡{len(datos_para_subir)} movimientos importados!")
                    st.rerun()
                else:
                    st.sidebar.warning("Archivo vacío o datos inválidos.")
                
        except Exception as e:
            st.sidebar.error(f"Ocurrió un error técnico: {e}")

# --- CUERPO PRINCIPAL ---
df = load_data()

st.title("☁️ Contabilidad en la Nube")

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📅 Planificación Fija", "📂 Datos"])

with tab1:
    if not df.empty and "Monto" in df.columns:
        if df["Monto"].dtype == object:
             df["Monto"] = df["Monto"].astype(str).str.replace(',', '.', regex=False)
        
        df["Monto"] = pd.to_numeric(df["Monto"], errors='coerce').fillna(0)
        
        total_balance = df["Monto"].sum()
        col1, col2, col3 = st.columns(3)
        col1.metric("Balance Total", f"{total_balance:.2f} €")
        col2.metric("Ingresos", f"{df[df['Monto'] > 0]['Monto'].sum():.2f} €")
        col3.metric("Gastos", f"{df[df['Monto'] < 0]['Monto'].sum():.2f} €")
        
        st.divider()
        
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors='coerce')
        if not df["Fecha"].isnull().all():
            df_sorted = df.sort_values("Fecha")
            st.plotly_chart(px.line(df_sorted, x="Fecha", y="Monto", color="Tipo", title="Evolución Temporal"), use_container_width=True)

with tab2:
    if not df.empty and "Es_Fijo" in df.columns:
        # Buscamos "SÍ" o "SI"
        fijos = df[
            (df["Es_Fijo"].astype(str).str.upper().isin(["SÍ", "SI"])) & 
            (df["Monto"] < 0)
        ]
        
        if not fijos.empty:
            total_fijo = fijos["Monto"].sum()
            st.metric("Gasto Fijo Total Acumulado", f"{total_fijo:.2f} €")
            st.dataframe(fijos, use_container_width=True)
        else:
            st.info("No hay gastos marcados como fijos (Busco 'SÍ' o 'SI' en la columna Es_Fijo).")

with tab3:
    st.dataframe(df, use_container_width=True)
    
    plantilla = pd.DataFrame(columns=["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"])
    csv_plantilla = plantilla.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Descargar Plantilla CSV vacía", csv_plantilla, "plantilla_importacion.csv", "text/csv")
