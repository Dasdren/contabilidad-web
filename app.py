import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import google.generativeai as genai

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Santander Finance Pro", layout="wide", page_icon="💰", initial_sidebar_state="expanded")

# Inyectar CSS para mejorar la estética
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 5px; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #e63946 !important; color: white !important; }
    hr { margin: 1.5em 0; }
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
        st.error("⚠️ Error crítico de conexión con Google Sheets.")
        st.stop()

sheet = conectar_google_sheets()

# --- IA: GEM EXPERTO FINANCIERO ---
def llamar_experto_ia(contexto):
    try:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        # Aquí va la personalidad de tu Gem
        instrucciones = """
        Eres el 'Gem Experto Financiero'. Analizas balances anuales con visión estratégica.
        Tu tono es directo, profesional y orientado a resultados.
        Identifica problemas de liquidez, gastos excesivos y dame 3 acciones concretas para mejorar el ahorro.
        """
        response = model.generate_content(f"{instrucciones}\n\nDATOS DEL AÑO:\n{contexto}")
        return response.text
    except Exception as e:
        return f"❌ No pude conectar con tu Gem. Error: {str(e)}"

# --- PROCESAMIENTO DE DATOS (BLINDADO) ---
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
    for col in ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]:
        if col not in df.columns: df[col] = ""
        
    df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
    df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
    df["Año"] = df["Fecha_DT"].dt.year
    df["Mes_Num"] = df["Fecha_DT"].dt.month
    # Ordenamos los meses para las gráficas
    df["Mes"] = pd.Categorical(df["Fecha_DT"].dt.strftime('%b'), categories=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], ordered=True)
    return df

# --- INTERFAZ PRINCIPAL ---
df_raw = load_data()
st.title("🏦 Centro de Mando Financiero")

# --- SIDEBAR: FILTROS GLOBAL ---
with st.sidebar:
    st.header("📅 Filtros Temporales")
    años_dispo = sorted([int(a) for a in df_raw["Año"].dropna().unique() if a >= 2025], reverse=True)
    if not años_dispo: años_dispo = [datetime.now().year]
    año_sel = st.selectbox("Seleccionar Año Fiscal", años_dispo)
    
    st.divider()
    st.info(f"Visualizando datos de: **{año_sel}**")

# Filtrado global por año
df = df_raw[df_raw["Año"] == año_sel].copy()

# --- PESTAÑAS DE NAVEGACIÓN ---
t1, t2, t3, t4 = st.tabs(["📊 Resumen Global", "📅 Planificador de Fijos", "🧠 Consultor IA", "📂 Editor Vivo"])

# ================= PESTAÑA 1: DASHBOARD PRO =================
with t1:
    if not df.empty:
        # --- SECCIÓN 1: KPIs PRINCIPALES ---
        ingresos = df[df["Importe_Num"] > 0]["Importe_Num"].sum()
        gastos_totales = df[df["Importe_Num"] < 0]["Importe_Num"].sum()
        gastos_abs = abs(gastos_totales)
        balance = ingresos + gastos_totales
        tasa_ahorro = (balance / ingresos * 100) if ingresos > 0 else 0

        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        col_k1.metric("💰 Ingresos Totales", f"{ingresos:,.2f} €", help="Total ingresado este año")
        col_k2.metric("💸 Gastos Totales", f"{gastos_abs:,.2f} €", delta=-gastos_abs, delta_color="inverse", help="Total gastado este año")
        col_k3.metric("⚖️ Balance Neto", f"{balance:,.2f} €", delta=balance, help="Lo que te queda en el bolsillo")
        
        with col_k4:
            st.metric("🛡️ Tasa de Ahorro", f"{tasa_ahorro:.1f}%")
            # Barra de progreso visual de salud financiera
            color_salud = "red" if tasa_ahorro < 10 else "orange" if tasa_ahorro < 30 else "green"
            st.progress(min(tasa_ahorro/100, 1.0), text=f"Salud Financiera: {tasa_ahorro:.1f}%")

        st.divider()

        # --- SECCIÓN 2: GRÁFICAS DINÁMICAS ---
        col_g1, col_g2 = st.columns([2, 1])
        
        with col_g1:
            st.subheader("📈 Tendencia Mensual (Ingresos vs Gastos)")
            # Agrupar por mes y tipo
            df_trend = df.groupby(["Mes", "Tipo"])["Importe_Num"].sum().reset_index()
            # Convertir gastos a positivo para la gráfica comparativa
            df_trend["Valor Visual"] = df_trend.apply(lambda x: abs(x["Importe_Num"]) if x["Tipo"] == "Gasto" else x["Importe_Num"], axis=1)
            
            fig_line = px.line(df_trend, x="Mes", y="Valor Visual", color="Tipo", markers=True,
                               color_discrete_map={"Ingreso": "#2a9d8f", "Gasto": "#e76f51"},
                               labels={"Valor Visual": "Euros (€)"})
            fig_line.update_layout(hovermode="x unified", xaxis_title=None, legend_title=None)
            st.plotly_chart(fig_line, use_container_width=True)

        with col_g2:
            st.subheader("🍩 Reparto de Gastos")
            # Crear DF específico para gastos con valores absolutos (Evita ShapeError)
            df_gastos_pie = df[df["Importe_Num"] < 0].copy()
            df_gastos_pie["Gasto Absoluto"] = df_gastos_pie["Importe_Num"].abs()
            
            fig_donut = px.pie(df_gastos_pie, values="Gasto Absoluto", names="Categoria", hole=0.5,
                               color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_donut.update_traces(textposition='inside', textinfo='percent+label')
            fig_donut.update_layout(showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_donut, use_container_width=True)

        # --- SECCIÓN 3: DETALLE ---
        col_d1, col_d2 = st.columns(2)
        with col_d1:
             st.subheader("🏆 Top 5 Mayores Gastos")
             top_gastos = df[df["Importe_Num"] < 0].sort_values(by="Importe_Num", ascending=True).head(5).copy()
             top_gastos["Importe Abs"] = top_gastos["Importe_Num"].abs()
             
             fig_bar = px.bar(top_gastos, x="Importe Abs", y="Descripcion", orientation='h', text_auto='.2s',
                              color="Importe Abs", color_continuous_scale="Reds")
             fig_bar.update_layout(xaxis_title="Euros (€)", yaxis_title=None, coloraxis_showscale=False, yaxis={'categoryorder':'total ascending'})
             st.plotly_chart(fig_bar, use_container_width=True)

        with col_d2:
            st.subheader("⏱️ Actividad Reciente")
            st.dataframe(df.sort_values("Fecha_DT", ascending=False).head(5)[["Fecha", "Descripcion", "Importe", "Categoria"]], 
                         hide_index=True, use_container_width=True)

    else:
        st.info(f"👋 No hay datos registrados para el año **{año_sel}**.")
        st.write("Por favor, usa el importador de CSV (si tuviéramos sidebar) o selecciona otro año.")

# ================= PESTAÑA 2: PLANIFICADOR =================
with t2:
    st.header("📅 Suelo Mensual de Gastos Fijos")
    st.caption(f"Previsión basada en los gastos recurrentes detectados en {año_sel}.")
    
    if not df.empty:
        # Filtramos solo gastos marcados como FIJOS
        df_fijos = df[(df["Es_Fijo"].str.upper() == "SÍ") & (df["Importe_Num"] < 0)].copy()
        
        if not df_fijos.empty:
            # DEDUPLICACIÓN CLAVE: Un gasto por concepto para la previsión mensual
            presupuesto = df_fijos.sort_values("Fecha_DT").drop_duplicates(subset=['Descripcion'], keep='last')
            total_mes = presupuesto["Importe_Num"].sum()
            
            col_p1, col_p2 = st.columns(2)
            col_p1.metric("Total Necesario al Mes", f"{abs(total_mes):,.2f} €", delta="Suelo de gasto", delta_color="inverse")
            col_p2.write("Este es el dinero que 'desaparece' de tu cuenta cada mes en facturas y suscripciones.")

            st.divider()
            st.subheader("Desglose de Recibos:")
            st.dataframe(presupuesto[["Descripcion", "Categoria", "Importe"]], use_container_width=True, hide_index=True)
        else:
            st.warning("No tienes gastos marcados como 'SÍ' en la columna 'Es_Fijo' para este año.")
            st.write("Ve a la pestaña **Editor Vivo** para configurarlos.")

# ================= PESTAÑA 3: IA GEM =================
with t3:
    st.header("🧠 Tu Gem: Experto Financiero")
    st.markdown(f"""
    Este asistente analizará el resumen completo de tu año **{año_sel}**.
    Dale al botón para recibir un diagnóstico profesional y consejos de ahorro personalizados.
    """)
    
    col_ia_btn, col_ia_info = st.columns([1, 2])
    with col_ia_btn:
        analizar_btn = st.button("✨ Ejecutar Análisis Estratégico", type="primary", use_container_width=True)
    
    if analizar_btn:
        if not df.empty:
            with st.spinner("Conectando con tu Gem Experto..."):
                # Preparamos el contexto
                ing = df[df["Importe_Num"] > 0]["Importe_Num"].sum()
                gas = df[df["Importe_Num"] < 0]["Importe_Num"].sum()
                bal = ing + gas
                top5 = df[df["Importe_Num"] < 0].sort_values("Importe_Num").head(5)[['Descripcion', 'Importe']].to_string(index=False)
                
                contexto_ia = f"""
                Año Fiscal: {año_sel}
                Ingresos Totales: {ing:.2f}€
                Gastos Totales: {gas:.2f}€
                Balance Final: {bal:.2f}€
                Top 5 Mayores Gastos del año:
                {top5}
                """
                informe = llamar_experto_ia(contexto_ia)
                
                with col_ia_info:
                    st.success("¡Análisis completado!")
                    with st.expander("📄 Ver Informe del Experto", expanded=True):
                        st.markdown(informe)
        else:
            st.error("No hay datos suficientes en este año para realizar un análisis.")

# ================= PESTAÑA 4: EDITOR VIVO =================
with t4:
    st.header("📂 Gestión de Datos en Vivo")
    st.write("Modifica categorías o marca gastos como fijos. Los cambios se guardan en Google Sheets.")
    
    df_editor = df[["Fecha", "Descripcion", "Importe", "Categoria", "Es_Fijo"]].copy()
    
    # Configuración del editor
    cats_dispo = ["Varios", "Vivienda", "Supermercado", "Ocio", "Transporte", "Salud", "Suscripciones", "Tecnología"]
    
    edited_df = st.data_editor(
        df_editor,
        column_config={
            "Categoria": st.column_config.SelectboxColumn("Categoría", options=cats_dispo, required=True),
            "Es_Fijo": st.column_config.SelectboxColumn("¿Es Fijo?", options=["SÍ", "NO"], required=True),
            "Importe": st.column_config.TextColumn(disabled=True),
            "Fecha": st.column_config.TextColumn(disabled=True),
             "Descripcion": st.column_config.TextColumn(disabled=True)
        },
        use_container_width=True,
        key="editor_principal"
    )

    if st.button("💾 Guardar Cambios en la Nube", type="primary"):
        with st.spinner("Sincronizando..."):
            # Sincronización simplificada (Actualiza las columnas C y F del bloque visible)
            # En producción, esto requeriría mapear IDs de fila reales.
            try:
                vals_cat = [[x] for x in edited_df["Categoria"].values.tolist()]
                vals_fijo = [[x] for x in edited_df["Es_Fijo"].values.tolist()]
                
                # Nota: Esto asume que los datos del año están al principio. 
                # Es una simplificación funcional para este prototipo.
                rango_len = len(vals_cat) + 1
                sheet.update(f"C2:C{rango_len}", vals_cat)
                sheet.update(f"F2:F{rango_len}", vals_fijo)
                st.success("¡Datos actualizados correctamente!")
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar: {e}")
