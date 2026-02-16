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

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Finanzas Personales con IA", layout="wide", page_icon="🧠")

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

# --- CONEXIÓN GEMINI AI (SOLUCIÓN DEFINITIVA V1) ---
def consultar_gemini(resumen_texto):
    try:
        api_key = st.secrets["gemini_api_key"]
        
        # Configuramos la versión v1 de la API explícitamente
        genai.configure(api_key=api_key)
        
        # Usamos el nombre del modelo sin el prefijo 'models/' 
        # y especificamos la versión estable mediante un parámetro de transporte
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            generation_config={"replacement_model_name": "gemini-1.5-flash"}
        )
        
        prompt = f"""
        Actúa como un asesor financiero experto. Analiza estos datos:
        {resumen_texto}
        
        Dame 3 consejos breves y directos sobre ahorro e inversión en español. Habla de tú.
        """
        
        # Forzamos la llamada a la API v1
        response = model.generate_content(prompt)
        return response.text
        
    except Exception as e:
        # Si el error 404 persiste, intentamos una última ruta técnica
        try:
            import google.ai.generativelanguage as pd_api
            client = genai.Client(api_key=api_key, http_options={'api_version': 'v1'})
            response = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
            return response.text
        except:
            return f"Error de comunicación. Asegúrate de que tu API Key es válida en AI Studio. Detalles: {e}"

# --- FUNCIONES DE LIMPIEZA MAESTRAS ---
def limpiar_dinero_euro(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    texto = str(valor).strip()
    # Dejar solo números, comas, puntos y signo menos
    texto = re.sub(r'[^\d.,-]', '', texto)
    # Lógica España: 1.200,50 -> 1200.50
    if '.' in texto and ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    elif ',' in texto:
        texto = texto.replace(',', '.')
    try:
        return float(texto)
    except:
        return 0.0

def limpiar_fijo(valor):
    if pd.isna(valor): return "NO"
    return "SÍ" if 'S' in str(valor).upper() else "NO"

# --- PROCESAMIENTO DE DATOS ---
def load_data():
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    expected_cols = ["Fecha", "Tipo", "Categoria", "Descripcion", "Monto", "Es_Fijo"]
    for col in expected_cols:
        if col not in df.columns: df[col] = ""
    
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

# --- BARRA LATERAL (INGRESOS Y CSV) ---
st.sidebar.header("📝 Nuevo Movimiento")
with st.sidebar.form("entry_form", clear_on_submit=True):
    fecha = st.date_input("Fecha", datetime.today())
    tipo = st.selectbox("Tipo", ["Gasto", "Ingreso"])
    categoria = st.text_input("Categoría")
    descripcion = st.text_input("Descripción")
    monto = st.number_input("Monto (€)", min_value=0.0, format="%.2f")
    es_fijo = st.checkbox("¿Es FIJO mensual?")
    if st.form_submit_button("Guardar Manual"):
        if monto > 0:
            monto_final = -monto if tipo == "Gasto" else monto
            save_entry(fecha, tipo, categoria, descripcion, monto_final, es_fijo)
            st.success("✅ ¡Guardado!")
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
            # Limpieza de datos en la importación
            df_up["Monto"] = df_up["Monto"].apply(limpiar_dinero_euro)
            df_up["Monto"] = pd.to_numeric(df_up["Monto"])
            # Asegurar signo negativo en gastos
            cond_gasto = df_up["Tipo"].str.lower().str.contains("gasto", na=False)
            df_up["Monto"] = np.where(cond_gasto, -1 * df_up["Monto"].abs(), df_up["Monto"].abs())
            # Normalizar Fijo y Fechas
            df_up["Es_Fijo"] = df_up["Es_Fijo"].apply(limpiar_fijo)
            df_up["Fecha"] = pd.to_datetime(df_up["Fecha"], dayfirst=True, errors='coerce').dt.strftime("%Y-%m-%d")
            
            df_up = df_up.dropna(subset=['Fecha'])
            datos = df_up[req_cols].values.tolist()
            if len(datos) > 0:
                sheet.append_rows(datos)
                st.success(f"✅ ¡{len(datos)} movimientos importados!")
                st.rerun()
    except Exception as e:
        st.error(f"Error en importación: {e}")

# --- CUERPO PRINCIPAL ---
df = load_data()
st.title("🧠 Inteligencia Financiera")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard Pro", "🤖 Consultor IA", "🔮 Previsiones", "📅 Planificador"])

# --- TAB 1: DASHBOARD ---
with tab1:
    if not df.empty and "Monto_Num" in df.columns:
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

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.subheader("Ingresos vs Gastos Mensuales")
            df["Mes_Año"] = df["Fecha_DT"].dt.strftime('%Y-%m')
            mensual = df.groupby(["Mes_Año", "Tipo"])["Monto_Num"].sum().reset_index()
            mensual["Monto_Abs"] = mensual["Monto_Num"].abs()
            st.plotly_chart(px.bar(mensual, x="Mes_Año", y="Monto_Abs", color="Tipo", barmode="group", 
                             color_discrete_map={"Ingreso": "#00CC96", "Gasto": "#EF553B"}), use_container_width=True)
            
        with col_g2:
            st.subheader("¿A dónde va el dinero?")
            gastos_df = df[df["Monto_Num"] < 0].copy()
            gastos_df["Monto_Abs"] = gastos_df["Monto_Num"].abs()
            st.plotly_chart(px.sunburst(gastos_df, path=['Categoria', 'Descripcion'], values='Monto_Abs'), use_container_width=True)

# --- TAB 2: CONSULTOR GEMINI ---
with tab2:
    st.header("🤖 Gemini AI: Tu Asesor Personal")
    if st.button("✨ Analizar mis Finanzas con IA"):
        with st.spinner("Gemini 1.5 está analizando tus datos..."):
            if df.empty:
                st.warning("No hay datos suficientes.")
            else:
                top_gastos = df[df["Monto_Num"] < 0].groupby("Categoria")["Monto_Num"].sum().sort_values().head(3)
                resumen = f"Balance: {total:.2f}€. Ingresos: {ingresos:.2f}€. Gastos: {gastos:.2f}€. Top Categorías: {top_gastos.to_dict()}."
                st.markdown(consultar_gemini(resumen))

# --- TAB 3: PREVISIONES ---
with tab3:
    st.header("🔮 Predicción a 90 días")
    if not df.empty and len(df) > 5:
        df_sort = df.sort_values("Fecha_DT").dropna(subset=["Fecha_DT"])
        df_sort["Balance_Acumulado"] = df_sort["Monto_Num"].cumsum()
        df_sort['Fecha_Ordinal'] = df_sort['Fecha_DT'].map(datetime.toordinal)
        
        model = LinearRegression()
        model.fit(df_sort[['Fecha_Ordinal']].values, df_sort['Balance_Acumulado'].values)
        
        fechas_futuras = [df_sort['Fecha_DT'].max() + timedelta(days=x) for x in range(1, 91)]
        X_futuro = np.array([d.toordinal() for d in fechas_futuras]).reshape(-1, 1)
        y_futuro = model.predict(X_futuro)
        
        df_final_chart = pd.concat([
            pd.DataFrame({'Fecha': df_sort['Fecha_DT'], 'Saldo': df_sort['Balance_Acumulado'], 'Tipo': 'Realidad'}),
            pd.DataFrame({'Fecha': fechas_futuras, 'Saldo': y_futuro, 'Tipo': 'Estimado'})
        ])
        
        fig_pred = px.line(df_final_chart, x="Fecha", y="Saldo", color="Tipo")
        fig_pred.add_vline(x=pd.Timestamp.now(), line_dash="dash")
        st.plotly_chart(fig_pred, use_container_width=True)
        st.metric("Saldo estimado en 3 meses", f"{y_futuro[-1]:,.2f} €")
    else:
        st.warning("Se requiere un historial mayor para predecir.")

# --- TAB 4: PLANIFICADOR (FIJOS ÚNICOS) ---
with tab4:
    st.header("📅 Costes Fijos Mensuales")
    if not df.empty:
        fijos = df[(df["Es_Fijo_Clean"] == "SÍ") & (df["Monto_Num"] < 0)].copy()
        if not fijos.empty:
            # Eliminamos duplicados históricos para ver solo el 'suelo' mensual
            fijos_unicos = fijos.drop_duplicates(subset=['Descripcion', 'Monto_Num'], keep='last')
            st.metric("Gasto Fijo Mensual", f"{fijos_unicos['Monto_Num'].sum():,.2f} €")
            st.dataframe(fijos_unicos[["Categoria", "Descripcion", "Monto"]], use_container_width=True)



