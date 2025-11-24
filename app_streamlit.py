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

# Si no existe .env, crear a partir de .env.example (plantilla)
if not os.path.exists(DOTENV_PATH) and os.path.exists('.env.example'):
    shutil.copy('.env.example', DOTENV_PATH)
    st.warning('Se ha creado un archivo `.env` nuevo a partir de `.env.example`. Por favor, ábrelo y rellena tus credenciales (Client ID y Secret) antes de continuar, luego pulsa "Recargar configuración".')

# Cargar variables de entorno (si existen)
load_dotenv(DOTENV_PATH)

# Instanciar cliente
client = StravaClient()

# Botón para recargar configuración manualmente si el usuario edita .env durante la sesión
if st.button('Recargar configuración (.env)'):
    load_dotenv(DOTENV_PATH, override=True)
    client = StravaClient()
    st.success('Cliente recargado. Ahora puedes continuar con la autorización.')

# Comprobar si las credenciales STRAVA están configuradas
has_creds = bool(os.environ.get('STRAVA_CLIENT_ID') and os.environ.get('STRAVA_CLIENT_SECRET'))

st.sidebar.header('Paso 1: Autorización')
with st.sidebar.expander('Obtener URL de autorización'):
    if has_creds:
        auth_url = client.get_authorization_url()
        if auth_url:
            st.write('Abre esta URL en tu navegador y autoriza la app:')
            st.markdown(f"[{auth_url}]({auth_url})")
            st.write('Después de autorizar, copia el código (param `code`) de la URL de redirección.')
        else:
            st.info('No se ha podido construir la URL de autorización. Revisa las credenciales.')
    else:
        st.info('Introduce `STRAVA_CLIENT_ID` y `STRAVA_CLIENT_SECRET` en la sección "Credenciales Strava" y pulsa "Guardar credenciales en .env" y después "Recargar configuración".')

# Inputs para credenciales STRAVA (permite rellenar .env desde la UI)
st.sidebar.subheader('Credenciales Strava')
cid_default = os.environ.get('STRAVA_CLIENT_ID', '')
csecret_default = os.environ.get('STRAVA_CLIENT_SECRET', '')
cid = st.sidebar.text_input('STRAVA_CLIENT_ID', value=cid_default)
csecret = st.sidebar.text_input('STRAVA_CLIENT_SECRET', value=csecret_default)
if st.sidebar.button('Guardar credenciales en .env'):
    try:
        # asegurar que existe el fichero .env
        open(DOTENV_PATH, 'a').close()
        set_key(DOTENV_PATH, 'STRAVA_CLIENT_ID', cid)
        set_key(DOTENV_PATH, 'STRAVA_CLIENT_SECRET', csecret)
        # recargar variables y cliente
        load_dotenv(DOTENV_PATH, override=True)
        client = StravaClient()
        st.success('Credenciales guardadas en .env. La configuración se ha recargado.')
        st.experimental_rerun()
    except Exception as e:
        st.error(f'Error guardando credenciales en .env: {e}')

code_input = st.sidebar.text_input('Introduce el código de autorización (si lo tienes)')
if st.sidebar.button('Intercambiar código por tokens', disabled=not has_creds):
    if not code_input:
        st.error('Introduce primero el código de autorización.')
    else:
        ok = client.exchange_authorization_code(code_input.strip())
        if ok:
            st.success('Tokens guardados correctamente en .env')
            load_dotenv(DOTENV_PATH, override=True)
            client = StravaClient()
            st.experimental_rerun()
        else:
            st.error('Error intercambiando el código. Revisa la consola.')

st.sidebar.header('Token')
if st.sidebar.button('Forzar refresco de token', disabled=not has_creds):
    try:
        client.refresh_token()
        st.success('Token renovado (ver consola para detalles).')
        load_dotenv(DOTENV_PATH, override=True)
        client = StravaClient()
    except Exception as e:
        st.error(f'Error renovando token: {e}')

st.header('Paso 2: Obtener IDs de actividades')
if st.button('Descargar IDs de actividades (get_activities)', disabled=not has_creds):
    try:
        ids = client.get_activities()
        st.success(f'IDs descargadas: {len(ids)} (guardadas en ids_runs.txt)')
        if ids:
            st.write(pd.DataFrame({'id': ids}))
    except Exception as e:
        st.error(f'Error obteniendo IDs: {e}')

st.header('Paso 3: Obtener detalles de actividades')
if st.button('Descargar detalles (get_info)', disabled=not has_creds):
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
if os.path.exists('activities_date.csv'):
    df_all = pd.read_csv('activities_date.csv')
    st.write('Vista previa de `activities_date.csv` (ordenado por fecha)')
    st.dataframe(df_all.head(200))
else:
    st.info('No se ha encontrado `activities_date.csv`. Puedes crearla a partir de `activities.csv` con el botón de abajo.')

if os.path.exists('activities.csv'):
    if st.button('Ordenar `activities.csv` por fecha (crear `activities_date.csv`)', disabled=not has_creds):
        try:
            df_sorted = client.sort_activities_by_date(input_path='activities.csv', output_path='activities_date.csv')
            st.success(f'Creado `activities_date.csv` con {len(df_sorted)} filas.')
            st.dataframe(df_sorted.head(200))
        except Exception as e:
            st.error(f'Error ordenando CSV: {e}')

st.header('Paso 5: Métricas de coaching')
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
                                                     input_csv=None if df_source is not None else 'activities.csv',
                                                     save_path=save if save else None,
                                                     save_format=save_format)
        st.success(f'Métricas calculadas. Mejora: {mejora}%')
        st.dataframe(df_metrics.head(200))
        if save:
            st.info(f'Resultados guardados en {save}')
    except Exception as e:
        st.error(f'Error calculando métricas: {e}')

st.markdown('---')
st.caption('App mínima para usar las funciones de `StravaClient`. Requiere variables de entorno STRAVA_CLIENT_ID/SECRET y (después) STRAVA_REFRESH_TOKEN/ACCESS_TOKEN.')
