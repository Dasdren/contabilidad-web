import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import numpy as np
import google.generativeai as genai

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Santander IA Pro", layout="wide", page_icon="🧠")

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
        st.error("⚠️ Error de conexión con Google Sheets.")
        st.stop()

sheet = conectar_google_sheets()

# --- IA: CONSULTA MEJORADA ---
def consultar_gemini(prompt_personalizado, datos_contexto):
    try:
        api_key = st.secrets["gemini_api_key"]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        full_prompt = f"""
        Actúa como un experto asesor financiero personal. 
        Contexto de mis finanzas: {datos_contexto}
        Pregunta del usuario: {prompt_personalizado}
        Respuesta: (Se breve, directo y habla de tú)
        """
        response = model.generate_content(full_prompt)
        return response.text
    except:
        return "La IA está descansando. Revisa tu API Key."

# --- LIMPIEZA DE IMPORTES ---
def limpiar_importe(valor):
    if pd.isna(valor) or str(valor).strip() == "": return 0.0
    s = str(valor).strip().replace('"', '').replace(' EUR', '').replace('−', '-')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    s = "".join(c for c in s if c.isdigit() or c in '.-')
    try: return float(s)
    except: return 0.0

# --- CARGA DE DATOS ---
@st.cache_data(ttl=60) # Cache de 1 minuto para no saturar Google
def load_data():
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    # Asegurar columnas
    for col in ["Fecha", "Tipo", "Categoria", "Descripcion", "Importe", "Es_Fijo"]:
        if col not in df.columns: df[col] = ""
    df["Importe_Num"] = df["Importe"].apply(limpiar_importe)
    df["Fecha_DT"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors='coerce')
    return df

# --- INTERFAZ ---
st.title("🧠 Inteligencia Financiera Santander")
df = load_data()

t1, t2, t3, t4 = st.tabs(["📊 Dashboard", "📅 Planificador", "🤖 Asesor IA", "📂 Editor de Datos"])

# --- TAB 3: ASISTENTE DE IA (RELLENADO) ---
with t3:
    st.header("🤖 Tu Consultor Personal")
    
    col_ia1, col_ia2 = st.columns([1, 2])
    
    with col_ia1:
        st.subheader("Opciones de Análisis")
        opcion = st.radio("¿En qué puedo ayudarte hoy?", [
            "Resumen de salud financiera",
            "¿Cómo puedo ahorrar 200€ más al mes?",
            "Detectar gastos innecesarios (hormiga)",
            "Analizar mis gastos fijos vs variables",
            "Pregunta personalizada..."
        ])
        
        pregunta_custom = ""
        if opcion == "Pregunta personalizada...":
            pregunta_custom = st.text_input("Escribe tu duda:")
        
        btn_ia = st.button("✨ Ejecutar Análisis con IA")

    with col_ia2:
        if btn_ia:
            with st.spinner("Analizando tus movimientos..."):
                # Crear un resumen de datos para la IA
                resumen_gastos = df[df['Importe_Num'] < 0].groupby('Descripcion')['Importe_Num'].sum().sort_values().head(10).to_string()
                total_gastos = df[df['Importe_Num'] < 0]['Importe_Num'].sum()
                contexto = f"Total gastos: {total_gastos}€. Top 10 gastos: {resumen_gastos}"
                
                query = pregunta_custom if pregunta_custom else opcion
                respuesta = consultar_gemini(query, contexto)
                st.markdown(f"### 💡 Sugerencia de la IA\n{respuesta}")
        else:
            st.info("Selecciona una opción a la izquierda para que la IA analice tus datos.")

# --- TAB 4: EDITOR EN VIVO (MODIFICAR ES_FIJO) ---
with t4:
    st.header("📂 Editor de Movimientos")
    st.write("Puedes modificar la columna **Es_Fijo** (escribe SÍ o NO) y pulsar el botón de abajo para guardar.")
    
    # Configuramos el editor de datos
    df_para_editar = df[["Fecha", "Tipo", "Descripcion", "Importe", "Es_Fijo"]].copy()
    
    df_editado = st.data_editor(
        df_para_editar,
        column_config={
            "Es_Fijo": st.column_config.SelectboxColumn(
                "¿Es Gasto Fijo?",
                options=["SÍ", "NO"],
                required=True,
            )
        },
        disabled=["Fecha", "Tipo", "Importe", "Descripcion"], # Solo dejamos editar Es_Fijo
        use_container_width=True,
        num_rows="fixed"
    )

    if st.button("💾 Guardar cambios en Google Sheets"):
        with st.spinner("Sincronizando con la nube..."):
            # Actualizar la columna en la hoja de cálculo
            # Nota: Empezamos en la fila 2 porque la 1 son cabeceras
            nuevos_valores_fijos = df_editado["Es_Fijo"].values.tolist()
            
            # Preparamos el rango de actualización (Columna F de la fila 2 en adelante)
            rango = f"F2:F{len(nuevos_valores_fijos) + 1}"
            celdas_a_actualizar = [[val] for val in nuevos_valores_fijos]
            
            sheet.update(rango, celdas_a_actualizar)
            st.success("✅ Cambios guardados correctamente.")
            st.cache_data.clear() # Limpiar cache para recargar datos frescos
            st.rerun()

# --- LÓGICA DE LAS OTRAS PESTAÑAS (Resumida) ---
with t1:
    if not df.empty:
        c1, c2 = st.columns(2)
        c1.metric("Gastos Totales", f"{df[df['Importe_Num']<0]['Importe_Num'].sum():,.2f} €")
        c2.metric("Balance", f"{df['Importe_Num'].sum():,.2f} €")
        st.plotly_chart(px.line(df.sort_values("Fecha_DT"), x="Fecha_DT", y="Importe_Num", title="Evolución"), use_container_width=True)

with t2:
    st.header("Planificador Mensual")
    fijos = df[(df["Es_Fijo"].str.upper() == "SÍ") & (df["Importe_Num"] < 0)]
    presupuesto = fijos.drop_duplicates(subset=['Descripcion', 'Importe_Num'], keep='last')
    st.metric("Suelo Mensual de Gastos", f"{presupuesto['Importe_Num'].sum():,.2f} €")
    st.table(presupuesto[["Descripcion", "Importe"]])
