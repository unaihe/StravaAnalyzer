import shutil
import streamlit as st
import pandas as pd
import os
from strava_func import StravaClient
from dotenv import set_key, load_dotenv

st.set_page_config(page_title='Strava UI', layout='wide')
st.title('Strava - Interfaz paso a paso')

# Ruta al .env del proyecto
DOTENV_PATH = os.path.join(os.path.dirname(__file__), '.env')

if not os.path.exists(DOTENV_PATH) and os.path.exists('.env.example'):
    shutil.copy('.env.example', DOTENV_PATH)
    st.warning('Se ha creado un archivo `.env` nuevo a partir de `.env.example`. Por favor, ábrelo y rellena tus credenciales (Client ID y Secret) antes de continuar, luego pulsa "Recargar configuración".')

# Cargar variables de entorno (si existen)
load_dotenv(DOTENV_PATH)

# Instanciar cliente (se hace después de cargar .env)
client = StravaClient()

# Botón para recargar configuración manualmente si el usuario edita .env durante la sesión
if st.button('Recargar configuración (.env)'):
    load_dotenv(DOTENV_PATH, override=True)
    client = StravaClient()
    st.success('Cliente recargado. Ahora puedes continuar con la autorización.')
    
st.sidebar.header('Paso 1: Autorización')
with st.sidebar.expander('Obtener URL de autorización'):
    auth_url = client.get_authorization_url()
    if auth_url:
        st.write('Abre esta URL en tu navegador y autoriza la app:')
        st.markdown(f"[{auth_url}]({auth_url})")
        st.write('Después de autorizar, copia el código (param `code`) de la URL de redirección.')

# Ruta al .env del proyecto
DOTENV_PATH = os.path.join(os.path.dirname(__file__), '.env')

# Inputs para credenciales STRAVA (permite rellenar .env desde la UI)
st.sidebar.subheader('Credenciales Strava')
cid_default = os.environ.get('STRAVA_CLIENT_ID', '')
csecret_default = os.environ.get('STRAVA_CLIENT_SECRET', '')
cid = st.sidebar.text_input('STRAVA_CLIENT_ID', value=cid_default)
csecret = st.sidebar.text_input('STRAVA_CLIENT_SECRET', value=csecret_default,type="password")
if st.sidebar.button('Guardar credenciales en .env'):
    try:
        # asegurar que existe el fichero .env
        open(DOTENV_PATH, 'a').close()
        set_key(DOTENV_PATH, 'STRAVA_CLIENT_ID', cid)
        set_key(DOTENV_PATH, 'STRAVA_CLIENT_SECRET', csecret)
        st.success('Credenciales guardadas en .env. Pulsa "Recargar configuración" para aplicarlas.')
    except Exception as e:
        st.error(f'Error guardando credenciales en .env: {e}')

code_input = st.sidebar.text_input('Introduce el código de autorización (si lo tienes)')
if st.sidebar.button('Intercambiar código por tokens'):
    if not code_input:
        st.error('Introduce primero el código de autorización.')
    else:
        ok = client.exchange_authorization_code(code_input.strip())
        if ok:
            st.success('Tokens guardados correctamente en .env')
        else:
            st.error('Error intercambiando el código. Revisa la consola.')

st.sidebar.header('Token')
if st.sidebar.button('Forzar refresco de token'):
    try:
        client.refresh_token()
        st.success('Token renovado (ver consola para detalles).')
    except Exception as e:
        st.error(f'Error renovando token: {e}')

st.sidebar.header('Sincronización Inteligente')
if st.sidebar.button('🔄 SINCRONIZAR TODO (Smart Sync)', key='smart_sync_btn'):
    """
    Smart Sync: 
    1. Actualiza la lista de IDs (get_activities)
    2. Descarga solo actividades nuevas (get_info con reintentos + Rate Limit)
    3. Calcula métricas de coaching (HR zones -> Pace zones -> Stats)
    4. Muestra resultado
    """
    with st.spinner('Sincronizando...'):
        try:
            # Crear contenedores para mostrar progreso en tiempo real
            progress_container = st.container()
            status_container = st.container()
            
            # Paso 1: Obtener lista actualizada de IDs
            st.sidebar.info("📥 Paso 1/4: Actualizando lista de IDs...")
            ids = client.get_activities()
            st.sidebar.success(f"✓ {len(ids)} IDs obtenidas")
            
            # Paso 2: Descargar detalles (solo nuevas, con reintentos)
            st.sidebar.info("📥 Paso 2/4: Descargando detalles de actividades...")
            
            # Crear placeholders para progreso en tiempo real
            with progress_container:
                st.write("📊 Progreso de descarga:")
                progress_placeholder = st.empty()
            
            with status_container:
                st.write("📝 Estado actual:")
                status_placeholder = st.empty()
            
            # Llamar get_info con placeholders
            df = client.get_info(
                progress_placeholder=progress_placeholder,
                status_placeholder=status_placeholder
            )
            
            st.sidebar.success(f"✓ Actividades sincronizadas")
            
            # Paso 3: Calcular métricas
            st.sidebar.info("📊 Paso 3/4: Calculando métricas de coaching...")
            
            # Preparar zonas del usuario (desde sesión o defaults)
            user_zones = None
            user_hr_zones = None
            
            # Intentar obtener de sesión si existen
            if 'user_zones' in st.session_state:
                user_zones = st.session_state.user_zones
            if 'user_hr_zones' in st.session_state:
                user_hr_zones = st.session_state.user_hr_zones
            
            # Calcular métricas
            df_metrics, mejora = client.coaching_metrics(
                df=df,
                athlete_zones=user_zones,
                hr_zones=user_hr_zones
            )
            
            st.sidebar.success(f"✓ Métricas calculadas (Mejora: {mejora}%)")
            
            # Paso 4: Mostrar resultados
            st.sidebar.info("📄 Paso 4/4: Mostrando resultados...")
            
            st.success('✓ Sincronización completada exitosamente')
            st.dataframe(df_metrics.head(20), use_container_width=True)
            
            # Información resumida
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric('Total Actividades', len(df_metrics))
            with col2:
                st.metric('Mejora %', f"{mejora}%")
            with col3:
                methods = df_metrics['Calculation_Method'].value_counts().to_dict()
                st.metric('Métodos Usados', len(methods))
            
            # Detalle de métodos de cálculo
            st.subheader('Desglose de Métodos de Cálculo')
            if 'Calculation_Method' in df_metrics.columns:
                method_counts = df_metrics['Calculation_Method'].value_counts()
                st.bar_chart(method_counts)
                st.write(method_counts)
            
        except FileNotFoundError as e:
            st.sidebar.error(f"✗ Error: {str(e)}")
            st.error(f"No se encontraron archivos necesarios: {str(e)}")
        except Exception as e:
            st.sidebar.error(f"✗ Error en sincronización: {str(e)}")
            st.error(f"Error durante la sincronización: {str(e)}")

st.header('Paso 2: Obtener IDs de actividades')
if st.button('Descargar IDs de actividades (get_activities)'):
    try:
        ids = client.get_activities()
        st.success(f'IDs descargadas: {len(ids)} (guardadas en ids_runs.txt)')
        if ids:
            st.write(pd.DataFrame({'id': ids}))
    except Exception as e:
        st.error(f'Error obteniendo IDs: {e}')

st.header('Paso 3: Obtener detalles de actividades')
if st.button('Descargar detalles (get_info)'):
    try:
        df = client.get_info()
        if df is not None and not df.empty:
            st.success(f'Descargadas {len(df)} actividades. Guardadas en activities.csv (raw)')
            st.dataframe(df)
        else:
            st.info('No hay nuevas actividades descargadas.')
    except FileNotFoundError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f'Error descargando detalles: {e}')

st.header('Paso 4: Ver/Filtrar actividades')

try:
    df_all = client.get_all_activities_sorted()
    if not df_all.empty:
        st.success(f'✓ Cargadas {len(df_all)} actividades desde PostgreSQL (ordenadas por fecha)')
        st.dataframe(df_all.head(200), use_container_width=True)
    else:
        st.info('No hay actividades en la base de datos. Ejecuta "Descargar detalles" primero.')
except Exception as e:
    st.error(f'✗ Error cargando actividades de PostgreSQL: {e}')

st.header('Paso 5: Métricas de coaching')
st.header('Configuración de Pulsaciones (Prioridad Alta)')

use_hr_zones = st.checkbox("Usar mis zonas de pulso (HR)", value=False)

user_hr_zones = None  # Por defecto None (sin HR)

if use_hr_zones:
    st.info("Introduce los límites SUPERIORES de pulso (bpm) para cada zona. Rango típico: Z5=190, Z4=175, Z3=160, Z2=145, Z1=130.")
    col1, col2 = st.columns(2)
    with col1:
        z5_hr = st.number_input("Límite Z5 (MaxVO2) - bpm", value=190, min_value=150, max_value=220)
        z4_hr = st.number_input("Límite Z4 (Threshold) - bpm", value=175, min_value=140, max_value=210)
        z3_hr = st.number_input("Límite Z3 (Tempo) - bpm", value=160, min_value=130, max_value=200)
    with col2:
        z2_hr = st.number_input("Límite Z2 (Aerobic) - bpm", value=145, min_value=120, max_value=190)
        z1_hr = st.number_input("Límite Z1 (Recovery) - bpm", value=130, min_value=100, max_value=180)
    
    user_hr_zones = {
        "Z5": z5_hr,
        "Z4": z4_hr,
        "Z3": z3_hr,
        "Z2": z2_hr,
        "Z1": z1_hr
    }
    st.success("Zonas de pulso configuradas. Tendrán PRIORIDAD sobre el ritmo.")

st.header('Configuración de Zonas de Ritmo (Opcional pero Recomendado)')

use_custom_zones = st.checkbox("Quiero definir mis zonas de ritmo manualmente (Más preciso)")

user_zones = None  # Por defecto es None

if use_custom_zones:
    st.info("Introduce el límite SUPERIOR de cada zona (el ritmo más rápido de esa zona).")
    col1, col2, col3 = st.columns(3)
    with col1:
        z5 = st.text_input("Límite Z5 (Sprint) - min/km", value="4.00")
        z4 = st.text_input("Límite Z4 (Umbral) - min/km", value="5.15")
    with col2:
        z3 = st.text_input("Límite Z3 (Tempo) - min/km", value="6.00")
        z2 = st.text_input("Límite Z2 (Aeróbico) - min/km", value="7.45")
    with col3:
        z1 = st.text_input("Límite Z1 (Recup.) - min/km", value="9.00")
    
    try:
        user_zones = {
            "Z5_Sprint": float(z5),
            "Z4_Umbral": float(z4),
            "Z3_Tempo": float(z3),
            "Z2_Aerobico": float(z2),
            "Z1_Recuperacion": float(z1)
        }
        st.success("Zonas de ritmo configuradas. Se usarán si no hay datos de pulso.")
    except ValueError:
        st.error("Formato incorrecto. Usa punto para decimales (ej: 5.30)")
        user_zones = None
else:
    st.warning("Usando configuración automática (menos precisa). Se basará en promedios estadísticos.")

with st.form('metrics_form'):
    save = st.text_input('Ruta para guardar resultados (opcional)', value='')
    save_format = st.selectbox('Formato de guardado', ['csv', 'json', 'parquet', 'pickle'])
    run = st.form_submit_button('Calcular métricas y guardar')

if run:
    try:
        # Priorizar dataframe cargado
        if 'df_all' in locals():
            df_source = df_all
        else:
            df_source = None

        df_metrics, mejora = client.coaching_metrics(df=df_source if df_source is not None else None,
                                                     save_path=save if save else None,
                                                     save_format=save_format,
                                                     athlete_zones=user_zones,
                                                     hr_zones=user_hr_zones)
        st.success(f'Métricas calculadas. Mejora: {mejora}%')
        st.dataframe(df_metrics.head(200))
        if save:
            st.info(f'Resultados guardados en {save}')
    except Exception as e:
        st.error(f'Error calculando métricas: {e}')

st.markdown('---')
st.caption('App mínima para usar las funciones de `StravaClient`. Requiere variables de entorno STRAVA_CLIENT_ID/SECRET y (después) STRAVA_REFRESH_TOKEN/ACCESS_TOKEN.')
