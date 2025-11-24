import streamlit as st
import pandas as pd
import os
from strava_func import StravaClient

st.set_page_config(page_title='Strava UI', layout='wide')
st.title('Strava - Interfaz paso a paso')

# Instanciar cliente
client = StravaClient()

st.sidebar.header('Paso 1: Autorización')
with st.sidebar.expander('Obtener URL de autorización'):
    auth_url = client.get_authorization_url()
    if auth_url:
        st.write('Abre esta URL en tu navegador y autoriza la app:')
        st.markdown(f"[{auth_url}]({auth_url})")
        st.write('Después de autorizar, copia el código (param `code`) de la URL de redirección.')

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
if os.path.exists('activities_date.csv'):
    df_all = pd.read_csv('activities_date.csv')
    st.write('Vista previa de `activities_date.csv` (ordenado por fecha)')
    st.dataframe(df_all.head(200))
else:
    st.info('No se ha encontrado `activities_date.csv`. Puedes crearla a partir de `activities.csv` con el botón de abajo.')

if os.path.exists('activities.csv'):
    if st.button('Ordenar `activities.csv` por fecha (crear `activities_date.csv`)'):
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
