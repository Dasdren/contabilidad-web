import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import numpy as np
import re
import google.generativeai as genai
from sklearn.linear_model import LinearRegression

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Finanzas con IA", layout="wide", page_icon="🧠")

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
        st.error(f"⚠️ Error conectando a Google Sheets: {e}")
        st.stop()

sheet = conectar_google_sheets()

# --- CONEXIÓN GEMINI AI ---
def consultar_gemini(resumen_texto):
    try:
        api_key = st.secrets["gemini_api_key"]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""
        Actúa como un asesor financiero experto e imparcial. Analiza este resumen de mis finanzas personales:
        {resumen_texto}
        
        Dame 3 consejos concretos:
        1. Sobre cómo reducir mis gastos (basado en las categorías donde más gasto).
        2. Una recomendación de ahorro.
        3. Una idea general de inversión conservadora para el excedente.
        
        Sé breve, directo y usa formato Markdown con negritas. Háblame de tú.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"No pude conectar con Gemini. Verifica tu API Key. Error: {e}"

# --- FUNCIONES DE LIMPIEZA (MANTENEMOS LAS QUE FUNCIONAN) ---
def limpiar_dinero_euro(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    texto = str(valor).strip()
    texto = re.sub(r'[^\d.,-]', '', texto)
    if '.' in texto and ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    elif ',' in texto:
        texto = texto.replace(',', '.')
    try: return float(texto)
    except: return 0.0

def limpiar_fijo(valor):
    if pd.isna(valor): return "NO"
    return "SÍ" if 'S' in str(valor).upper() else "NO"

# --- LÓGICA DE DATOS ---
def load_data():
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    expected_cols = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
    for col in expected_cols:
        if col not in df.columns: df[col] = ""
    
    # Procesamiento inicial de tipos
    if not df.empty and "Monto" in df.columns:
        df["Monto_Num"] = df["Monto"].apply(limpiar_dinero_euro)
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
        df["Es_Fijo_Clean"] = df["Es_Fijo"].apply(limpiar_fijo)
    return df

def save_entry(fecha, tipo, categoria, descripcion, monto, es_fijo):
    fecha_str = fecha.strftime("%Y-%m-%d")
    es_fijo_str = "SÍ" if es_fijo else "NO"
    row = [fecha_str, tipo, categoria, descripcion, monto, es_fijo_str]
    sheet.append_row(row)

# --- BARRA LATERAL (ENTRADA Y CSV) ---
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

st.sidebar.markdown("---")
st.sidebar.header("📥 Importar CSV")
uploaded_file = st.sidebar.file_uploader("Sube tu archivo", type=["csv"])
if uploaded_file is not None and st.sidebar.button("Procesar e Importar"):
    try:
        uploaded_file.seek(0)
        linea = uploaded_file.readline().decode('utf-8', errors='ignore')
        sep = ';' if ';' in linea else ','
        uploaded_file.seek(0)
        df_up = pd.read_csv(uploaded_file, sep=sep, dtype=str, encoding='utf-8-sig', on_bad_lines='skip')
        df_up.columns = df_up.columns.str.strip().str.replace('ï»¿', '')
        
        req_cols = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
        if all(col in df_up.columns for col in req_cols):
            df_up["Monto"] = df_up["Monto"].apply(limpiar_dinero_euro)
            df_up["Monto"] = pd.to_numeric(df_up["Monto"])
            cond_gasto = df_up["Tipo"].str.lower().str.contains("gasto", na=False)
            df_up["Monto"] = np.where(cond_gasto, -1 * df_up["Monto"].abs(), df_up["Monto"].abs())
            df_up["Es_Fijo"] = df_up["Es_Fijo"].apply(limpiar_fijo)
            df_up["Fecha"] = pd.to_datetime(df_up["Fecha"], dayfirst=True, errors='coerce').dt.strftime("%Y-%m-%d")
            df_up = df_up.dropna(subset=['Fecha'])
            df_up = df_up[df_up["Monto"] != 0]
            
            datos = df_up[req_cols].values.tolist()
            if len(datos) > 0:
                sheet.append_rows(datos)
                st.success(f"✅ ¡{len(datos)} movimientos importados!")
                st.rerun()
    except Exception as e:
        st.error(f"Error: {e}")

# --- CUERPO PRINCIPAL ---
df = load_data()
st.title("🧠 Finanzas Personales con IA")

# PESTAÑAS
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard Pro", "🧠 Consultor IA", "🔮 Previsiones", "📅 Planificador"])

# --- TAB 1: DASHBOARD AVANZADO ---
with tab1:
    if not df.empty and "Monto_Num" in df.columns:
        # KPIs
        total = df["Monto_Num"].sum()
        ingresos = df[df["Monto_Num"] > 0]["Monto_Num"].sum()
        gastos = df[df["Monto_Num"] < 0]["Monto_Num"].sum()
        ahorro_tasa = (ingresos + gastos) / ingresos * 100 if ingresos > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Balance Total", f"{total:,.2f} €")
        c2.metric("Ingresos", f"{ingresos:,.2f} €")
        c3.metric("Gastos", f"{gastos:,.2f} €", delta_color="inverse")
        c4.metric("Tasa de Ahorro", f"{ahorro_tasa:.1f}%")
        
        st.divider()

        # GRÁFICOS
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("Ingresos vs Gastos (Mensual)")
            df["Mes_Año"] = df["Fecha_DT"].dt.strftime('%Y-%m')
            mensual = df.groupby(["Mes_Año", "Tipo"])["Monto_Num"].sum().reset_index()
            mensual["Monto_Abs"] = mensual["Monto_Num"].abs()
            fig_bar = px.bar(mensual, x="Mes_Año", y="Monto_Abs", color="Tipo", barmode="group", 
                             color_discrete_map={"Ingreso": "#00CC96", "Gasto": "#EF553B"})
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with col_g2:
            st.subheader("¿En qué se va el dinero?")
            gastos_df = df[df["Monto_Num"] < 0].copy()
            gastos_df["Monto_Abs"] = gastos_df["Monto_Num"].abs()
            fig_pie = px.sunburst(gastos_df, path=['Categoria', 'Descripcion'], values='Monto_Abs',
                                  color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_pie, use_container_width=True)

# --- TAB 2: CONSULTOR GEMINI ---
with tab2:
    st.header("🤖 Gemini: Tu Asesor Financiero")
    st.markdown("Gemini analizará tus datos actuales y te dará consejos personalizados.")
    
    if st.button("✨ Analizar mis Finanzas con IA"):
        with st.spinner("Gemini está estudiando tus cuentas..."):
            if df.empty:
                st.warning("Necesito datos para analizar.")
            else:
                # Preparamos el resumen para la IA
                top_gastos = df[df["Monto_Num"] < 0].groupby("Categoria")["Monto_Num"].sum().sort_values().head(3)
                resumen = f"""
                Total Balance: {total:.2f}€.
                Ingresos Totales: {ingresos:.2f}€.
                Gastos Totales: {gastos:.2f}€.
                Top 3 Categorías de gasto: {top_gastos.to_dict()}.
                Tasa de ahorro actual: {ahorro_tasa:.1f}%.
                """
                consejo = consultar_gemini(resumen)
                st.markdown(consejo)

# --- TAB 3: PREVISIONES (REGRESIÓN LINEAL) ---
with tab3:
    st.header("🔮 El Futuro (Proyección)")
    st.info("Basado en tu histórico, así evolucionará tu dinero los próximos 90 días si sigues igual.")
    
    if not df.empty and len(df) > 5:
        df_sort = df.sort_values("Fecha_DT").dropna(subset=["Fecha_DT"])
        # Calcular balance acumulado día a día
        df_sort["Balance_Acumulado"] = df_sort["Monto_Num"].cumsum()
        
        # Preparar datos para Machine Learning
        df_sort['Fecha_Ordinal'] = df_sort['Fecha_DT'].map(datetime.toordinal)
        X = df_sort[['Fecha_Ordinal']].values
        y = df_sort['Balance_Acumulado'].values
        
        # Entrenar modelo
        model = LinearRegression()
        model.fit(X, y)
        
        # Predecir futuro (90 días)
        futuro_dias = 90
        ultima_fecha = df_sort['Fecha_DT'].max()
        fechas_futuras = [ultima_fecha + timedelta(days=x) for x in range(1, futuro_dias + 1)]
        X_futuro = np.array([d.toordinal() for d in fechas_futuras]).reshape(-1, 1)
        y_futuro = model.predict(X_futuro)
        
        # Crear DataFrame de predicción
        df_futuro = pd.DataFrame({'Fecha': fechas_futuras, 'Predicción': y_futuro})
        df_futuro['Tipo'] = 'Futuro Estimado'
        
        # Unir con histórico para gráfica
        df_historico = df_sort[['Fecha_DT', 'Balance_Acumulado']].copy()
        df_historico.columns = ['Fecha', 'Predicción']
        df_historico['Tipo'] = 'Realidad'
        
        df_final_chart = pd.concat([df_historico, df_futuro])
        
        fig_pred = px.line(df_final_chart, x="Fecha", y="Predicción", color="Tipo", 
                           color_discrete_map={"Realidad": "blue", "Futuro Estimado": "orange"})
        fig_pred.add_vline(x=datetime.today(), line_dash="dash", annotation_text="Hoy")
        st.plotly_chart(fig_pred, use_container_width=True)
        
        saldo_futuro = y_futuro[-1]
        delta = saldo_futuro - total
        color_delta = "normal" if delta > 0 else "inverse"
        st.metric(f"Saldo estimado en {futuro_dias} días", f"{saldo_futuro:,.2f} €", f"{delta:,.2f} € vs hoy", delta_color=color_delta)
    else:
        st.warning("Necesito al menos 5 movimientos para calcular una tendencia.")

# --- TAB 4: PLANIFICADOR (FIJOS) ---
with tab4:
    st.header("📅 Tus Gastos Fijos (Suelo Mensual)")
    if not df.empty:
        # Filtramos fijos y gastos
        fijos = df[(df["Es_Fijo_Clean"] == "SÍ") & (df["Monto_Num"] < 0)].copy()
        if not fijos.empty:
            # Eliminar duplicados por descripción y monto (quedarse con el último)
            fijos_unicos = fijos.drop_duplicates(subset=['Descripcion', 'Monto_Num'], keep='last')
            coste_mensual = fijos_unicos["Monto_Num"].sum()
            
            st.metric("Coste Fijo Mensual", f"{coste_mensual:,.2f} €")
            st.dataframe(fijos_unicos[["Categoria", "Descripcion", "Monto"]], use_container_width=True)
        else:
            st.info("No hay gastos fijos registrados.")
