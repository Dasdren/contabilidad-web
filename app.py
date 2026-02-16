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

# --- FUNCIONES DE LIMPIEZA AVANZADA (LOS ROBOTS) ---

def limpiar_monto(valor):
    """Convierte formatos españoles (1.000,50) a formato Python (1000.50)"""
    if pd.isna(valor) or str(valor).strip() == "":
        return 0.0
    
    # Convertimos a texto puro
    s = str(valor).strip()
    
    # Quitamos símbolos de moneda y espacios
    s = s.replace('€', '').replace('?', '').replace('EUR', '').strip()
    
    # CASO CRÍTICO: Detectar si es formato español (punto para miles, coma para decimales)
    # Ejemplo: 1.200,50 o 50,20
    if ',' in s:
        # Si tiene puntos (miles), los quitamos primero
        s = s.replace('.', '') 
        # Luego cambiamos la coma por punto (para que Python entienda el decimal)
        s = s.replace(',', '.')
    
    try:
        return float(s)
    except:
        return 0.0

def normalizar_fijo(valor):
    """Entiende cualquier variante de SI/NO"""
    if pd.isna(valor):
        return "NO"
    
    texto = str(valor).upper().strip() # Convertir a mayúsculas y quitar espacios
    
    # Lista de palabras que significan "SÍ"
    if texto in ['SI', 'SÍ', 'S', 'YES', 'Y', 'TRUE', '1']:
        return "SÍ"
    return "NO"

# --- FUNCIONES PRINCIPALES ---
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
            # 1. CARGA FLEXIBLE (Intenta detectar punto y coma o coma automáticamente)
            uploaded_file.seek(0)
            try:
                # Engine python detecta separadores automáticamente mejor
                df_upload = pd.read_csv(uploaded_file, encoding='utf-8-sig', sep=None, engine='python')
            except:
                uploaded_file.seek(0)
                df_upload = pd.read_csv(uploaded_file, encoding='latin-1', sep=';')
            
            # Limpieza cabeceras
            df_upload.columns = df_upload.columns.str.strip().str.replace('ï»¿', '')
            
            columnas_necesarias = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
            
            if not all(col in df_upload.columns for col in columnas_necesarias):
                st.sidebar.error(f"Error de formato. Columnas encontradas: {list(df_upload.columns)}")
            else:
                # 2. APLICAMOS LOS ROBOTS DE LIMPIEZA
                
                # A) Limpiar dinero usando la función inteligente
                df_upload["Monto"] = df_upload["Monto"].apply(limpiar_monto)

                # B) Inteligencia de Signos (Gastos negativos)
                df_upload["Monto"] = np.where(
                    df_upload["Tipo"].str.lower().str.contains("gasto", na=False), 
                    -1 * df_upload["Monto"].abs(),
                    df_upload["Monto"].abs()
                )

                # C) Normalizar columna FIJO usando la función inteligente
                df_upload["Es_Fijo"] = df_upload["Es_Fijo"].apply(normalizar_fijo)

                # D) Fecha
                df_upload["Fecha"] = pd.to_datetime(df_upload["Fecha"], dayfirst=True, errors='coerce').dt.strftime("%Y-%m-%d")
                
                # Filtrar errores
                df_upload = df_upload.dropna(subset=['Fecha', 'Monto'])
                df_upload = df_upload[df_upload["Monto"] != 0] # Quitamos valores 0

                # 3. SUBIR A LA NUBE
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
        # Aseguramos que lo que viene de Google Sheets se entienda como número
        # Google Sheets a veces devuelve "1,000.50" como texto
        df["Monto"] = df["Monto"].apply(limpiar_monto)
        
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
        # Volvemos a aplicar la limpieza por si acaso
        df["Es_Fijo"] = df["Es_Fijo"].apply(normalizar_fijo)
        
        fijos = df[
            (df["Es_Fijo"] == "SÍ") & 
            (df["Monto"] < 0)
        ]
        
        if not fijos.empty:
            total_fijo = fijos["Monto"].sum()
            st.metric("Gasto Fijo Total Acumulado", f"{total_fijo:.2f} €")
            st.dataframe(fijos, use_container_width=True)
        else:
            st.info("No hay gastos marcados como fijos.")

with tab3:
    st.dataframe(df, use_container_width=True)
    
    plantilla = pd.DataFrame(columns=["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"])
    csv_plantilla = plantilla.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Descargar Plantilla CSV vacía", csv_plantilla, "plantilla_importacion.csv", "text/csv")
