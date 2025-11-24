import requests
import json
import os
import time
import pandas as pd
import numpy as np
from dotenv import load_dotenv, set_key, find_dotenv
load_dotenv()

ACTIVITIES_URL="https://www.strava.com/api/v3/athlete/activities"
TOKEN_URL = "https://www.strava.com/oauth/token"
DOTENV_PATH = os.path.join(os.path.dirname(__file__), '.env')

class StravaClient:
    def __init__(self):
        load_dotenv(find_dotenv()) 
        self.CLIENT_ID=os.environ.get('STRAVA_CLIENT_ID')
        self.CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET')
        self.REFRESH_TOKEN = os.environ.get('STRAVA_REFRESH_TOKEN')
        self.ACCESS_TOKEN = None

        
    def get_authorization_url(self):
        """Construye y devuelve la URL para que el usuario dé permiso a Strava."""
        # No interactivo: devuelve la URL para autorizar
        redirect_uri = "http://localhost"
        scope = "activity:read_all"

        if not self.CLIENT_ID:
            print("ERROR: STRAVA_CLIENT_ID no configurado.")
            return None

        url = (
            f"https://www.strava.com/oauth/authorize?"
            f"client_id={self.CLIENT_ID}&"
            f"redirect_uri={redirect_uri}&"
            f"response_type=code&"
            f"scope={scope}"
        )

        return url

    def exchange_authorization_code(self, code):
        """Intercambia el código de autorización por access/refresh tokens."""
        urlToken = TOKEN_URL
        payload = {
            'client_id': self.CLIENT_ID,
            'client_secret': self.CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code'
        }

        r = requests.post(urlToken, data=payload)
        if r.status_code == 200:
            data = r.json()
            self.ACCESS_TOKEN = data.get('access_token')
            self.REFRESH_TOKEN = data.get('refresh_token')
            # Guardar en .env
            set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', self.REFRESH_TOKEN)
            set_key(DOTENV_PATH, 'STRAVA_ACCESS_TOKEN', self.ACCESS_TOKEN)
            return True
        else:
            print(f"Error al intercambiar código. HTTP {r.status_code}: {r.text}")
            return False

    def refresh_token(self):
        """
        Renovar el token de acceso
        """
        # Datos que se enviarán en el cuerpo de la solicitud POST
        payload = {
            'client_id': self.CLIENT_ID,
            'client_secret': self.CLIENT_SECRET,
            'refresh_token': self.REFRESH_TOKEN, 
            'grant_type': 'refresh_token' 
        }
        try:
            # Realizar la solicitud POST
            response = requests.post(TOKEN_URL, data=payload, timeout=10)

            if response.status_code == 200:
                data = response.json()
                
                # Recibir el nuevo par de tokens
                self.ACCESS_TOKEN = data.get('access_token')
                self.REFRESH_TOKEN = data.get('refresh_token')
                
                print("Token renovado.")
                print("-" * 40)
                print(f"NUEVO Access Token: {self.ACCESS_TOKEN}")
                print(f"NUEVO Refresh Token: {self.REFRESH_TOKEN}")
                print("-" * 40)
            
                #Guardamos en el .env los tokens
                DOTENV_PATH = os.path.join(os.path.dirname(__file__), '.env')
                set_key(DOTENV_PATH, "STRAVA_REFRESH_TOKEN", self.REFRESH_TOKEN)
                set_key(DOTENV_PATH, "STRAVA_ACCESS_TOKEN", self.ACCESS_TOKEN)
            else:
                print(f"Error al renovar el token. Código HTTP: {response.status_code}")
                print(response.json())

        except requests.exceptions.RequestException as e:
            print(f"Error de conexión o de red: {e}")

    def ensure_access_token(self):
        """Asegura que haya un access token válido o intenta renovarlo."""
        if not self.ACCESS_TOKEN:
            # intentar cargar el access token desde env si existe
            self.ACCESS_TOKEN = os.environ.get('STRAVA_ACCESS_TOKEN')
        if not self.ACCESS_TOKEN and self.REFRESH_TOKEN:
            self.refresh_token()
        return bool(self.ACCESS_TOKEN)

    def get_headers(self):
        if not self.ensure_access_token():
            raise RuntimeError('No access token disponible. Autoriza la app primero.')
        return {"Authorization": f"Bearer {self.ACCESS_TOKEN}"}


    def get_activities(self):
        """
        Devuelve las ids de todas las actividades pedidas.
        Se guardarán en un txt, que se usara para conseguir los datos de cada una de las actividades
        """
        headers = self.get_headers()
        output_file = "ids_runs.txt"

        run_ids_count = 0
        page_number = 1

        ids = []
        with open(output_file, "w") as f:
            while True:
                params = {
                    "per_page": 200, # Máximo para minimizar solicitudes
                    "page": page_number
                }

                print(f"Solicitando página {page_number}...")

                try:
                    response = requests.get(ACTIVITIES_URL, headers=headers, params=params)

                    if response.status_code == 200:
                        activities = response.json()

                        if not activities:
                            print("Paginación completada. No hay más actividades.")
                            break

                        for activity in activities:
                            if activity.get('type') == 'Run':
                                activity_id = str(activity.get('id'))
                                f.write(activity_id + "\n")
                                ids.append(activity_id)
                                run_ids_count += 1

                        page_number += 1
                        time.sleep(1.5)
                    else:
                        print(f"Error al obtener los datos en página {page_number}. Código: {response.status_code}")
                        print(response.text)
                        break

                except requests.exceptions.RequestException as e:
                    print(f"Error de conexión o de red: {e}")
                    break

        return ids

    def get_info(self):
        """
        Obtener la información de los ids que has recogido 
        Siguiente paso pasar la funcion get_info aqui e implementar todo
        """
        headers = self.get_headers()
        input_file="ids_runs.txt" #Obtenido en la función anterior
        output_file="activities.csv"
        try:
            with open(input_file, "r") as f:
                all_activity_ids = {line.strip() for line in f if line.strip()}
        except FileNotFoundError:
            raise FileNotFoundError(f"No se encontró el archivo de IDs: {input_file}. Ejecuta get_activities primero.")
        total_ids=len(all_activity_ids)
        processed_ids = set()
        df_existing = pd.DataFrame()
        
        if os.path.exists(output_file):
            try:
                df_existing = pd.read_csv(output_file)
                processed_ids = set(df_existing['id'].astype(str))
                print(f"Encontrados {len(processed_ids)} IDs ya descargados en {output_file}.")
            except Exception:
                pass # Si el CSV es inválido, no hacemos nada y descargamos todo
        
        pending_ids = list(all_activity_ids - processed_ids)
        pending_count = len(pending_ids)

        if pending_count == 0 and total_ids > 0:
            print("Todas las actividades ya están descargadas.")
            return df_existing

        print(f"IDs pendientes a descargar: {pending_count}. Total: {total_ids}")
        all_activities_data = []

        for i, activity_id in enumerate(pending_ids):
            api_url = f"{ACTIVITIES_URL}/{activity_id}"
            # RETRASO OBLIGATORIO
            time.sleep(1.0)

            current_index = len(processed_ids) + i + 1
            print(f"Procesando {current_index}/{total_ids}: ID {activity_id}...")

            try:
                response = requests.get(api_url, headers=headers)

                if response.status_code == 200:
                    detail_json = response.json()
                    average_speed = detail_json.get('average_speed', 0)
                    pace = 60 / (average_speed * 3.6) if average_speed > 0 else 0

                    data_row = {
                        'id': detail_json.get('id'),
                        'name': detail_json.get('name'),
                        'description': detail_json.get('description'),
                        'start_date_local': detail_json.get('start_date_local'),
                        'distance_km': detail_json.get('distance', 0) / 1000,
                        'moving_time_min': detail_json.get('moving_time', 0) / 60,
                        'elevation_gain_m': detail_json.get('total_elevation_gain', 0),
                        'average_speed_kmh': average_speed * 3.6,
                        'pace_min_km': pace,
                        'km_splits_json': detail_json.get('splits_metric'),
                    }

                    all_activities_data.append(data_row)

                elif response.status_code == 429:
                    print("Límite de tarifa excedido (429). Detén y reintenta más tarde.")
                    break
                else:
                    # tratar otros errores
                    try:
                        error_message = response.json().get('message', response.text)
                    except Exception:
                        error_message = response.text
                    print(f"Error al obtener detalles del ID {activity_id}. Código: {response.status_code}. Mensaje: {error_message}")

            except requests.exceptions.RequestException as e:
                print(f"Error de red al procesar ID {activity_id}: {e}")

        if all_activities_data:
            df_new = pd.DataFrame(all_activities_data)
            if not df_existing.empty:
                df_final = pd.concat([df_existing, df_new], ignore_index=True)
            else:
                df_final = df_new

            # Sobrescribimos/guardamos el archivo para tener la lista completa y actualizada
            try:
                df_final.to_csv(output_file, index=False)
            except Exception as e:
                print(f"Error guardando {output_file}: {e}")

            print("Proceso finalizado/actualizado.")
            print(f"Se descargaron {len(all_activities_data)} nuevas actividades en este intento.")
            print(f"Total de actividades en CSV: {len(df_final)}")
            return df_final
        else:
            print("No se pudieron descargar nuevas actividades en este intento.")
            return df_existing
    
    def coaching_metrics(self, df=None, input_csv=None, save_path=None, save_format='csv'):
        """
        Se calcularán los parámetros esenciales para que la ia valore tu forma fisica
        """
        # Cargar DataFrame (priorizar df pasado como argumento)
        if df is None:
            if input_csv is None:
                input_csv = "activities_date.csv"
            df = pd.read_csv(input_csv)
        #Eliminamos los ritmos 0 para que no fastidien las medias ni nada
        df.loc[df["pace_min_km"] == 0, "pace_min_km"] = np.nan
        df["pace_min_km"] = df["pace_min_km"].fillna(df["pace_min_km"].median())

        #Cálculo de carga
        df["training_load"]=(df['moving_time_min'] * (df['average_speed_kmh'] / 10)).round(2)
        #Cálculo de fatiga se hace a través de ewm el cual da mas peso a los valores más recientes en comparación con los mas antiguos
        df['ATL_7_dias'] = df['training_load'].ewm(span=7, adjust=False).mean().round(2)
        # Cálculo de Aptitud (CTL - span=42) Forma física de proceso más largo de unas 6 semanas
        df['CTL_42_dias'] = df['training_load'].ewm(span=42, adjust=False).mean().round(2)
        # Cálculo de Balance (TSB) Es decir si estas sobrecargado por la semana o descansado
        df['TSB'] = (df['CTL_42_dias'] - df['ATL_7_dias']).round(2)
        #Calculo de las zonas simulado
        df['CTL_Pace'] = df["pace_min_km"].ewm(span=42, adjust=False).mean().round(2)
        df['Pace_Diff_vs_CTL'] = (df["pace_min_km"] - df['CTL_Pace']).round(2)
        #Decidimos a que zona se corresponde 
        def classify_zone(diff):
            if diff <= -0.15: return "Z4_Intensidad_Alta"
            elif diff <= 0.05: return "Z3_Umbral_Normal"
            elif diff <= 0.30: return "Z2_Base_Lenta"
            else: return "Z1_Recuperacion_o_Error"
                
        df['Training_Zone'] = df['Pace_Diff_vs_CTL'].apply(classify_zone)
        
        total_actividades = len(df)
        punto_medio = total_actividades // 2

        # Ritmo Promedio de la Primera Mitad (Antiguo)
        ritmo_antiguo = df.head(punto_medio)['pace_min_km'].mean()

        # Ritmo Promedio de la Segunda Mitad (Reciente)
        ritmo_reciente = df.tail(total_actividades - punto_medio)['pace_min_km'].mean()

        # La mejora se calcula como (Antiguo - Reciente) / Antiguo, para que un número positivo sea una mejora
        mejora_pct = ((ritmo_antiguo - ritmo_reciente) / ritmo_antiguo * 100).round(2)

        # Guardado opcional
        if save_path:
            fmt = save_format.lower()
            try:
                if fmt == 'csv':
                    df.to_csv(save_path, index=False)
                elif fmt == 'json':
                    df.to_json(save_path, orient='records', date_format='iso')
                elif fmt == 'parquet':
                    df.to_parquet(save_path, index=False)
                elif fmt == 'pickle':
                    df.to_pickle(save_path)
                else:
                    raise ValueError(f"Formato de guardado no soportado: {save_format}")
            except Exception as e:
                print(f"Error guardando resultados en {save_path}: {e}")

        return df, mejora_pct

    def sort_activities_by_date(self, input_path='activities.csv', output_path='activities_date.csv', date_col='start_date_local', ascending=True):
        """
        Lee `input_path` (CSV), ordena por la columna de fecha `date_col` y guarda en `output_path`.

        Devuelve el DataFrame ordenado.
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Archivo no encontrado: {input_path}")

        try:
            df = pd.read_csv(input_path)
        except Exception as e:
            raise RuntimeError(f"Error leyendo {input_path}: {e}")

        if date_col not in df.columns:
            raise KeyError(f"Columna de fecha '{date_col}' no encontrada en {input_path}")

        # Convertir a datetime y ordenar
        try:
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        except Exception:
            # si falla la conversión, dejar las fechas como están; filas con NaT se irán al final
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')

        df_sorted = df.sort_values(by=date_col, ascending=ascending).reset_index(drop=True)

        try:
            df_sorted.to_csv(output_path, index=False)
        except Exception as e:
            raise RuntimeError(f"Error guardando {output_path}: {e}")

        return df_sorted


       