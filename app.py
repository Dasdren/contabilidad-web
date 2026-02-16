import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import re

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Mi Contabilidad Nube", layout="wide", page_icon="💰")

# --- CONEXIÓN CON GOOGLE SHEETS ---
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

# --- FUNCIONES DE LIMPIEZA ---
def limpiar_dinero_euro(valor):
    """Limpia formatos de moneda española a float de Python"""
    if pd.isna(valor) or str(valor).strip() == "":
        return 0.0
    texto = str(valor).strip()
    # Dejar solo números, comas, puntos y menos
    texto = re.sub(r'[^\d.,-]', '', texto)
    
    # Lógica Española: Si hay punto y coma, punto=miles, coma=decimal
    if '.' in texto and ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    elif ',' in texto:
        texto = texto.replace(',', '.')
    
    try:
        return float(texto)
    except:
        return 0.0

def limpiar_fijo(valor):
    """Normaliza SI/NO"""
    if pd.isna(valor): return "NO"
    texto = str(valor).upper()
    return "SÍ" if 'S' in texto else "NO"

# --- CARGA DE DATOS ---
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

# --- BARRA LATERAL ---
st.sidebar.header("📝 Nuevo Movimiento")
with st.sidebar.form("entry_form", clear_on_submit=True):
    fecha = st.date_input("Fecha", datetime.today())
    tipo = st.selectbox("Tipo", ["Gasto", "Ingreso"])
    categoria = st.text_input("Categoría")
    descripcion = st.text_input("Descripción")
    monto = st.number_input("Monto (€)", min_value=0.0, format="%.2f")
    es_fijo = st.checkbox("¿Es FIJO mensual?")
    
    if st.form_submit_button("Guardar"):
        if monto > 0:
            monto_final = -monto if tipo == "Gasto" else monto
            save_entry(fecha, tipo, categoria, descripcion, monto_final, es_fijo)
            st.success("✅ Guardado")
            st.rerun()

# --- IMPORTADOR CSV ---
st.sidebar.markdown("---")
st.sidebar.header("📥 Importar CSV")
uploaded_file = st.sidebar.file_uploader("Sube tu archivo", type=["csv"])

if uploaded_file is not None:
    if st.sidebar.button("Procesar e Importar"):
        try:
            uploaded_file.seek(0)
            primera_linea = uploaded_file.readline().decode('utf-8', errors='ignore')
            separador = ';' if ';' in primera_linea else ','
            uploaded_file.seek(0)
            
            df_upload = pd.read_csv(uploaded_file, sep=separador, dtype=str, encoding='utf-8-sig', on_bad_lines='skip')
            df_upload.columns = df_upload.columns.str.strip().str.replace('ï»¿', '')
            
            req_cols = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
            if not all(col in df_upload.columns for col in req_cols):
                st.error(f"Faltan columnas: {list(df_upload.columns)}")
                st.stop()

            # LIMPIEZA
            df_upload["Monto"] = df_upload["Monto"].apply(limpiar_dinero_euro)
            df_upload["Monto"] = pd.to_numeric(df_upload["Monto"])
            
            condicion_gasto = df_upload["Tipo"].str.lower().str.contains("gasto", na=False)
            df_upload["Monto"] = np.where(condicion_gasto, -1 * df_upload["Monto"].abs(), df_upload["Monto"].abs())
            
            df_upload["Es_Fijo"] = df_upload["Es_Fijo"].apply(limpiar_fijo)
            df_upload["Fecha"] = pd.to_datetime(df_upload["Fecha"], dayfirst=True, errors='coerce').dt.strftime("%Y-%m-%d")
            
            df_upload = df_upload.dropna(subset=['Fecha'])
            df_upload = df_upload[df_upload["Monto"] != 0]

            datos = df_upload[req_cols].values.tolist()
            if len(datos) > 0:
                sheet.append_rows(datos)
                st.success(f"✅ ¡{len(datos)} movimientos importados!")
                st.rerun()
            else:
                st.warning("Archivo vacío.")
        except Exception as e:
            st.error(f"Error: {e}")

# --- DASHBOARD PRINCIPAL ---
df = load_data()
st.title("💰 Mi Contabilidad")

tab1, tab2, tab3 = st.tabs(["📊 Balance Global", "📅 Planificación Mensual (Fijos)", "📂 Datos"])

# PESTAÑA 1: BALANCE (Aquí SÍ sumamos todo)
with tab1:
    if not df.empty and "Monto" in df.columns:
        df["Monto_Num"] = df["Monto"].apply(limpiar_dinero_euro)
        
        # KPI Totales Históricos
        total = df["Monto_Num"].sum()
        ingresos = df[df["Monto_Num"] > 0]["Monto_Num"].sum()
        gastos = df[df["Monto_Num"] < 0]["Monto_Num"].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Balance Actual (Cuenta)", f"{total:,.2f} €")
        c2.metric("Total Ingresado (Histórico)", f"{ingresos:,.2f} €")
        c3.metric("Total Gastado (Histórico)", f"{gastos:,.2f} €")
        
        st.divider()
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], errors='coerce')
        if not df["Fecha_DT"].isnull().all():
            st.plotly_chart(px.line(df.sort_values("Fecha_DT"), x="Fecha", y="Monto_Num", color="Tipo", title="Evolución de tu dinero"), use_container_width=True)

# PESTAÑA 2: PLANIFICACIÓN (Aquí NO duplicamos)
with tab2:
    st.header("🔮 Tu Coste de Vida Mensual")
    st.info("Esta pantalla te muestra tus gastos fijos ÚNICOS. Si pagas el alquiler todos los meses, aquí solo aparecerá una vez para que sepas cuánto necesitas al mes.")

    if not df.empty:
        # 1. Preparamos los datos
        df["Es_Fijo_Clean"] = df["Es_Fijo"].apply(limpiar_fijo)
        df["Monto_Num"] = df["Monto"].apply(limpiar_dinero_euro)
        
        # 2. Filtramos solo lo que sea Gasto y sea Fijo
        fijos = df[(df["Es_Fijo_Clean"] == "SÍ") & (df["Monto_Num"] < 0)].copy()
        
        if not fijos.empty:
            # 3. ELIMINAR DUPLICADOS (La Magia)
            # Nos quedamos con los fijos únicos basándonos en Descripción e Importe.
            # (Keep='last' se queda con el más reciente)
            fijos_unicos = fijos.drop_duplicates(subset=['Descripcion', 'Monto_Num'], keep='last')
            
            # Calculamos lo que te cuesta el mes
            coste_mensual = fijos_unicos["Monto_Num"].sum()
            
            # Mostrar KPIs
            st.metric("Gasto Fijo Mensual Estimado", f"{coste_mensual:,.2f} €", delta="Dinero que sale sí o sí cada mes")
            
            st.subheader("Desglose de tus recibos únicos:")
            st.dataframe(fijos_unicos[["Categoria", "Descripcion", "Monto"]], use_container_width=True)
            
            st.markdown("---")
            st.caption(f"*Nota: En tu historial total tienes {len(fijos)} pagos fijos registrados, pero aquí te mostramos los {len(fijos_unicos)} únicos que forman tu 'suelo' mensual.*")
            
        else:
            st.warning("No tienes gastos marcados como 'SÍ' en la columna Es_Fijo.")

with tab3:
    st.dataframe(df)
