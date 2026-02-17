import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import google.generativeai as genai

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Santander IA Planner", layout="wide", page_icon="📅")

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

# --- LIMPIEZA DE IMPORTES (ELIMINA EL ERROR -3495) ---
def limpiar_importe(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('−', '-')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    s = "".join(c for c in s if c.isdigit() or c in '.-')
    try: return float(s)
    except: return 0.0

# --- CARGA DE DATOS ---
def load_data():
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    # Columnas: Fecha, Tipo, Categoria, Descripcion, Importe, Es_Fijo
    for col in ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]:
        if col not in df.columns: df[col] = ""
    df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
    df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
    df["Año"] = df["Fecha_DT"].dt.year
    return df

# --- INTERFAZ ---
df = load_data()
st.title("🏦 Planificador de Gastos Fijos")

# Selector de año en la barra lateral
años = sorted([int(a) for a in df["Año"].dropna().unique() if a >= 2025], reverse=True)
if not años: años = [2026]
año_sel = st.sidebar.selectbox("📅 Seleccionar Año", años)
df_year = df[df["Año"] == año_sel].copy()

# PESTAÑAS
t1, t2, t3, t4 = st.tabs(["🏠 Resumen Anual", "📅 Planificación de Fijos", "🤖 Experto IA", "📂 Editor Vivo"])

with t2:
    st.header("📋 Presupuesto Mensual de Gastos Fijos")
    st.write("Este es tu 'suelo' de gastos. Cada concepto recurrente solo cuenta una vez para calcular tu necesidad mensual de efectivo.")
    
    if not df_year.empty:
        # 1. FILTRAR: Solo gastos (negativos) marcados como fijos ("SÍ")
        df_fijos = df_year[
            (df_year["Es_Fijo"].str.upper() == "SÍ") & 
            (df_year["Importe_Num"] < 0)
        ].copy()
        
        if not df_fijos.empty:
            # 2. DEDUPLICAR: Si hay 12 facturas de "Luz", solo mostramos la última para el presupuesto mensual
            # Agrupamos por descripción para tener el gasto mensual único
            presupuesto = df_fijos.sort_values("Fecha_DT").drop_duplicates(subset=['Descripcion'], keep='last')
            
            # 3. MÉTRICAS DE PLANIFICACIÓN
            total_fijos_mes = presupuesto["Importe_Num"].sum()
            
            c1, c2 = st.columns(2)
            c1.metric("💰 Total Fijos al Mes", f"{abs(total_fijos_mes):,.2f} €")
            c2.metric("📦 Cantidad de Servicios", f"{len(presupuesto)} recibos")
            
            st.divider()
            
            # 4. TABLA DETALLADA
            st.subheader("Lista de Gastos Recurrentes")
            # Añadimos columna de valor absoluto para que sea más legible
            presupuesto["Mensualidad"] = presupuesto["Importe_Num"].abs()
            st.dataframe(
                presupuesto[["Descripcion", "Categoria", "Mensualidad"]].sort_values("Mensualidad", ascending=False),
                use_container_width=True,
                hide_index=True
            )
            
            # 5. GRÁFICO DE PESO DE FIJOS
            st.subheader("Distribución del Suelo Mensual")
            fig_fijos = px.pie(presupuesto, values="Mensualidad", names="Descripcion", hole=0.4)
            st.plotly_chart(fig_fijos, use_container_width=True)
            
        else:
            st.info("No hay gastos marcados como 'SÍ' en la columna de fijos para este año.")
            st.write("Ve a la pestaña **Editor Vivo** para marcar tus facturas recurrentes.")
    else:
        st.warning("No hay datos cargados para este año.")

# --- EL RESTO DE PESTAÑAS (Resumen rápido para que el código funcione) ---
with t1:
    if not df_year.empty:
        ing = df_year[df_year["Importe_Num"] > 0]["Importe_Num"].sum()
        gas = abs(df_year[df_year["Importe_Num"] < 0]["Importe_Num"].sum())
        st.columns(3)[0].metric("Balance Anual", f"{(ing-gas):,.2f} €")
        
        # Gráfica de tarta (CORREGIDA para evitar ShapeError)
        df_pie = df_year[df_year["Importe_Num"] < 0].copy()
        if not df_pie.empty:
            df_pie["Abs_Val"] = df_pie["Importe_Num"].abs()
            st.plotly_chart(px.pie(df_pie, values="Abs_Val", names="Categoria", hole=0.4), use_container_width=True)

with t4:
    st.header("📂 Editor Vivo")
    st.write("Selecciona 'SÍ' en la columna Fijo y dale a Guardar.")
    df_ed = df_year[["Fecha", "Descripcion", "Importe", "Es_Fijo"]].copy()
    res = st.data_editor(df_ed, column_config={
        "Es_Fijo": st.column_config.SelectboxColumn("Fijo", options=["SÍ", "NO"])
    }, use_container_width=True, key="editor_fijos")

    if st.button("💾 Guardar Cambios en Google Sheets"):
        # Actualizamos la columna F (Es_Fijo)
        sheet.update(f"F2:F{len(res)+1}", [[x] for x in res["Es_Fijo"].values.tolist()])
        st.success("¡Base de datos actualizada!")
        st.rerun()
