import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Mi Contabilidad Nube", layout="wide", page_icon="☁️")

# --- CONEXIÓN CON GOOGLE SHEETS ---
# Esta función conecta tu App con la Hoja de Cálculo de forma segura
def conectar_google_sheets():
    # Definimos los permisos que necesitamos
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # Aquí está el truco: En lugar de buscar un archivo, buscamos en los "Secretos" de la nube
    # (Configuraremos esto en el último paso, no te preocupes si ahora no lo entiendes)
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    # Abrimos la hoja por su nombre
    sheet = client.open("Contabilidad_App").sheet1
    return sheet

# Intentamos conectar. Si falla, mostramos un aviso amigable.
try:
    sheet = conectar_google_sheets()
except Exception as e:
    st.error("⚠️ Error de conexión: No se detectaron las credenciales (Secrets). Esto es normal si estás probando en local sin configurar secrets.toml.")
    st.stop()

# --- FUNCIONES DE CARGA Y GUARDADO ---
def load_data():
    # Descargamos todos los datos de la hoja a la App
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    # Aseguramos que las columnas existan aunque la hoja esté vacía
    expected_cols = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = ""
    return df

def save_entry(fecha, tipo, categoria, descripcion, monto, es_fijo):
    # Preparamos la fila para enviarla a Google
    fecha_str = fecha.strftime("%Y-%m-%d")
    # Convertimos 'True'/'False' a texto para que se lea bien en la hoja
    es_fijo_str = "SÍ" if es_fijo else "NO"
    
    row = [fecha_str, tipo, categoria, descripcion, monto, es_fijo_str]
    sheet.append_row(row)

# Cargar datos al inicio
df = load_data()

# --- BARRA LATERAL: INGRESO DE DATOS ---
st.sidebar.header("📝 Nuevo Movimiento")

with st.sidebar.form("entry_form", clear_on_submit=True):
    fecha = st.date_input("Fecha", datetime.today())
    tipo = st.selectbox("Tipo", ["Gasto", "Ingreso"])
    categoria = st.text_input("Categoría (ej: Supermercado, Gasolina)")
    descripcion = st.text_input("Descripción")
    monto = st.number_input("Monto (€)", min_value=0.0, format="%.2f")
    es_fijo = st.checkbox("¿Es un gasto/ingreso FIJO mensual?")
    
    submitted = st.form_submit_button("Guardar en la Nube")

    if submitted:
        if monto > 0:
            monto_final = -monto if tipo == "Gasto" else monto
            try:
                save_entry(fecha, tipo, categoria, descripcion, monto_final, es_fijo)
                st.success("✅ ¡Guardado en Google Sheets!")
                # Recargar la página para ver el nuevo dato
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar: {e}")
        else:
            st.error("El monto debe ser mayor a 0")

# --- CUERPO PRINCIPAL ---
st.title("☁️ Contabilidad en la Nube")

# Pestañas
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📅 Planificación Fija", "📂 Datos en Bruto"])

with tab1:
    if not df.empty and "Monto" in df.columns:
        # Asegurar que Monto sea numérico (a veces Google Sheets lo manda como texto)
        df["Monto"] = pd.to_numeric(df["Monto"], errors='coerce').fillna(0)
        
        total_balance = df["Monto"].sum()
        total_ingresos = df[df["Monto"] > 0]["Monto"].sum()
        total_gastos = df[df["Monto"] < 0]["Monto"].sum()

        col1, col2, col3 = st.columns(3)
        col1.metric("Balance Total", f"{total_balance:.2f} €")
        col2.metric("Ingresos", f"{total_ingresos:.2f} €")
        col3.metric("Gastos", f"{total_gastos:.2f} €")

        st.divider()

        # Gráfico simple
        if not df.empty:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors='coerce')
            df_sorted = df.sort_values("Fecha")
            # Gráfico de líneas solo si hay fechas válidas
            if not df_sorted["Fecha"].isnull().all():
                fig = px.line(df_sorted, x="Fecha", y="Monto", color="Tipo", title="Evolución de Movimientos")
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("La hoja está vacía. Añade movimientos desde la barra lateral.")

with tab2:
    st.header("Gastos Fijos Recurrentes")
    if not df.empty and "Es_Fijo" in df.columns:
        # Filtramos por texto "SÍ" que es como lo guardamos ahora
        fijos = df[(df["Es_Fijo"] == "SÍ") & (df["Monto"] < 0)]
        if not fijos.empty:
            total_fijo = fijos["Monto"].sum()
            st.metric("Gasto Fijo Total (Acumulado)", f"{total_fijo:.2f} €")
            st.dataframe(fijos, use_container_width=True)
        else:
            st.info("No hay gastos fijos registrados.")

with tab3:
    st.markdown(f"Estos datos vienen directamente de tu hoja: **Contabilidad_App**")
    st.dataframe(df, use_container_width=True)
