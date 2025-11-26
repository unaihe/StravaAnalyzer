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

    def get_info(self, progress_placeholder=None, status_placeholder=None):
        """
        Obtener la información de los ids que has recogido.
        Implementa sincronización incremental con manejo robusto del Rate Limiting (429).
        - Carga Target IDs de 'ids_runs.txt'
        - Carga Processed IDs desde 'activities.csv'
        - Descarga solo los pendientes
        - Si Rate Limit (429): Pausa 15 minutos y reintentar el mismo ID
        - Concatena nuevas actividades y sobrescribe CSV
        
        Args:
            progress_placeholder: Placeholder de Streamlit para mostrar progreso en tiempo real
            status_placeholder: Placeholder de Streamlit para mostrar estado actual
        """
        import time
        
        headers = self.get_headers()
        input_file = "ids_runs.txt"  # Target IDs
        output_file = "activities.csv"
        
        # === PASO 1: Cargar Target IDs ===
        try:
            with open(input_file, "r") as f:
                all_activity_ids = {line.strip() for line in f if line.strip()}
        except FileNotFoundError:
            raise FileNotFoundError(f"No se encontró el archivo de IDs: {input_file}. Ejecuta get_activities primero.")
        
        total_ids = len(all_activity_ids)
        
        # === PASO 2: Cargar Processed IDs ===
        processed_ids = set()
        df_existing = pd.DataFrame()
        
        if os.path.exists(output_file):
            try:
                df_existing = pd.read_csv(output_file)
                processed_ids = set(df_existing['id'].astype(str))
                msg = f"✓ Encontrados {len(processed_ids)} IDs ya descargados en {output_file}."
                print(msg)
                if status_placeholder:
                    status_placeholder.write(msg)
            except Exception as e:
                msg = f"⚠ Error cargando CSV existente: {e}. Continuando..."
                print(msg)
                if status_placeholder:
                    status_placeholder.write(msg)
        
        # === PASO 3: Calcular Pending IDs ===
        pending_ids = list(all_activity_ids - processed_ids)
        pending_count = len(pending_ids)
        
        # === PASO 4: Chequeo de salida anticipada ===
        if pending_count == 0 and total_ids > 0:
            msg = f"✓ Todas las {total_ids} actividades ya están descargadas. Sin cambios."
            print(msg)
            if status_placeholder:
                status_placeholder.write(msg)
            return df_existing
        
        if pending_count == 0 and total_ids == 0:
            msg = "⚠ No hay actividades en ids_runs.txt. Ejecuta get_activities primero."
            print(msg)
            if status_placeholder:
                status_placeholder.write(msg)
            return df_existing
        
        msg = f"\n📥 Descargando {pending_count} nuevas actividades (Total en BD: {total_ids})..."
        print(msg)
        if status_placeholder:
            status_placeholder.write(msg)
        
        all_activities_data = []
        
        # === PASO 5: Iterar sobre Pending IDs con reintentos para Rate Limit ===
        for i, activity_id in enumerate(pending_ids):
            current_index = len(processed_ids) + i + 1
            api_url = f"{ACTIVITIES_URL}/{activity_id}"
            
            # Retry loop para manejar 429
            while True:
                # Retraso obligatorio entre requests
                time.sleep(1.0)
                
                status_msg = f"[{current_index}/{total_ids}] Procesando ID {activity_id}..."
                print(status_msg, end=" ", flush=True)
                if status_placeholder:
                    status_placeholder.write(status_msg)
                if progress_placeholder:
                    progress_placeholder.progress(current_index / total_ids, text=f"{current_index}/{total_ids}")
                
                try:
                    response = requests.get(api_url, headers=headers)
                    
                    # SI STATUS 200: Extraer datos y romper loop
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
                            'average_heartrate': detail_json.get('average_heartrate', None),
                            'max_heartrate': detail_json.get('max_heartrate', None),
                        }
                        
                        all_activities_data.append(data_row)
                        print("✓")
                        break  # Romper while para ir al siguiente ID
                    
                    # SI STATUS 429: Rate Limit - Esperar 15 min y reintentar
                    elif response.status_code == 429:
                        rate_limit_msg = f"\n⚠ RATE LIMIT (429) - Pausando 15 minutos..."
                        print(rate_limit_msg)
                        if status_placeholder:
                            status_placeholder.write(rate_limit_msg)
                        
                        wait_seconds = 15 * 60  # 900 segundos
                        
                        # Countdown visual
                        for remaining in range(wait_seconds, 0, -1):
                            mins, secs = divmod(remaining, 60)
                            countdown_msg = f"⏳ Esperando: {mins:02d}:{secs:02d}"
                            print(f"\r{countdown_msg}", end="", flush=True)
                            if status_placeholder:
                                status_placeholder.write(countdown_msg)
                            time.sleep(1)
                        
                        retry_msg = "\n✓ Reintentando...\n"
                        print(retry_msg)
                        if status_placeholder:
                            status_placeholder.write(retry_msg)
                        continue  # Reintentar el mismo ID
                    
                    # SI OTRO ERROR: Imprimir y saltar
                    else:
                        try:
                            error_message = response.json().get('message', response.text)
                        except Exception:
                            error_message = response.text
                        error_msg = f"✗ Error {response.status_code}: {error_message}"
                        print(error_msg)
                        if status_placeholder:
                            status_placeholder.write(error_msg)
                        break  # Salir del while, ir al siguiente ID
                
                except requests.exceptions.RequestException as e:
                    error_msg = f"✗ Error de red: {e}"
                    print(error_msg)
                    if status_placeholder:
                        status_placeholder.write(error_msg)
                    break  # Salir del while, ir al siguiente ID
        
        # === PASO 6: Concatenar y guardar ===
        if all_activities_data:
            df_new = pd.DataFrame(all_activities_data)
            
            if not df_existing.empty:
                df_final = pd.concat([df_existing, df_new], ignore_index=True)
                # Remover duplicados por 'id' si existen
                df_final = df_final.drop_duplicates(subset=['id'], keep='last')
            else:
                df_final = df_new
            
            # Guardar en CSV
            try:
                df_final.to_csv(output_file, index=False)
                complete_msg = (
                    f"\n✓ Proceso completado.\n"
                    f"  • Se descargaron: {len(all_activities_data)} nuevas actividades\n"
                    f"  • Total en CSV: {len(df_final)} actividades"
                )
                print(complete_msg)
                if status_placeholder:
                    status_placeholder.write(complete_msg)
                if progress_placeholder:
                    progress_placeholder.progress(1.0, text=f"{total_ids}/{total_ids}")
            except Exception as e:
                error_msg = f"✗ Error guardando {output_file}: {e}"
                print(error_msg)
                if status_placeholder:
                    status_placeholder.write(error_msg)
            
            return df_final
        else:
            no_new_msg = f"\n⚠ No se pudieron descargar nuevas actividades en este intento."
            print(no_new_msg)
            if status_placeholder:
                status_placeholder.write(no_new_msg)
            return df_existing
    
    def coaching_metrics(self, df=None, input_csv=None, save_path=None, save_format='csv', athlete_zones=None, hr_zones=None):
        """
        Calcula métricas con lógica de cascada (Waterfall):
        PRIORIDAD 1: HR zones (si disponibles y hr_zones definidas)
        PRIORIDAD 2: Pace zones (si disponibles y athlete_zones definidas)
        PRIORIDAD 3: Cálculo estadístico fallback
        """
        if df is None:
            if input_csv is None:
                input_csv = "activities_date.csv"
            df = pd.read_csv(input_csv)

        # Limpieza básica
        df.loc[df["pace_min_km"] == 0, "pace_min_km"] = np.nan
        df["pace_min_km"] = df["pace_min_km"].fillna(df["pace_min_km"].median())

        # --- PRIORIDAD 1: CÁLCULO POR FRECUENCIA CARDÍACA (HR) ---
        if 'average_heartrate' in df.columns and hr_zones is not None:
            print("Usando PRIORIDAD 1: Cálculo por Frecuencia Cardíaca (HR)...")
            
            # Rellenar NaN en HR con la media
            df['average_heartrate'] = df['average_heartrate'].fillna(df['average_heartrate'].median())
            
            def get_zone_from_hr(hr):
                """Clasifica zona según HR. Límites superiores: Z5>z5_limit, Z4>z4_limit, etc."""
                if pd.isna(hr):
                    return "Unknown", 1.0
                if hr > hr_zones["Z5"]: return "Z5_MaxVO2", 1.5
                if hr > hr_zones["Z4"]: return "Z4_Threshold", 1.2
                if hr > hr_zones["Z3"]: return "Z3_Tempo", 1.0
                if hr > hr_zones["Z2"]: return "Z2_Aerobic", 0.8
                return "Z1_Recovery", 0.6
            
            # Aplicamos clasificación
            zone_data = df['average_heartrate'].apply(lambda x: get_zone_from_hr(x))
            df['Training_Zone'] = zone_data.apply(lambda x: x[0])
            df['Intensity_Factor'] = zone_data.apply(lambda x: x[1])
            df['Calculation_Method'] = 'Heart Rate'
            
            # Carga = Tiempo * Intensity Factor * 10
            df["training_load"] = (df['moving_time_min'] * df['Intensity_Factor'] * 10).round(2)

        # --- PRIORIDAD 2: CÁLCULO POR RITMO (PACE) ---
        elif athlete_zones is not None:
            print("Usando PRIORIDAD 2: Cálculo por Zonas de Ritmo...")
            
            def get_zone_and_load(pace):
                # Asignamos peso (rTSS) según la zona de ritmo
                if pace < athlete_zones["Z5_Sprint"]: return "Z5_Sprint", 1.4  
                if pace < athlete_zones["Z4_Umbral"]: return "Z4_Umbral", 1.1 
                if pace < athlete_zones["Z3_Tempo"]: return "Z3_Tempo", 0.9  
                if pace < athlete_zones["Z2_Aerobico"]: return "Z2_Aerobico", 0.7  
                return "Z1_Recuperacion", 0.5 

            # Aplicamos lógica
            zone_data = df['pace_min_km'].apply(lambda x: get_zone_and_load(x))
            df['Training_Zone'] = zone_data.apply(lambda x: x[0])
            df['Intensity_Factor'] = zone_data.apply(lambda x: x[1])
            df['Calculation_Method'] = 'Pace (Manual)'
            
            # Carga = Tiempo * Intensidad
            df["training_load"] = (df['moving_time_min'] * df['Intensity_Factor'] * 10).round(2)

        # --- PRIORIDAD 3: CÁLCULO ESTADÍSTICO (FALLBACK) ---
        else:
            print("Usando PRIORIDAD 3: Cálculo Estadístico (Estimado)...")
            
            # Carga basada en velocidad pura
            df["training_load"] = (df['moving_time_min'] * (df['average_speed_kmh'] / 10)).round(2)
            df['Calculation_Method'] = 'Statistical (Estimated)'
            
            # Cálculo de zonas estadístico (desviación sobre la media)
            df['CTL_Pace'] = df["pace_min_km"].ewm(span=42, adjust=False).mean().round(2)
            df['Pace_Diff_vs_CTL'] = (df["pace_min_km"] - df['CTL_Pace']).round(2)
            
            def classify_zone_statistical(diff):
                if diff <= -0.15: return "Z4_Alta_Probable"
                elif diff <= 0.05: return "Z3_Normal"
                elif diff <= 0.30: return "Z2_Lenta_Probable"
                else: return "Z1_Muy_Lenta"
            
            df['Training_Zone'] = df['Pace_Diff_vs_CTL'].apply(classify_zone_statistical)
            df['Intensity_Factor'] = 1.0  # Placeholder


        # --- CÁLCULOS COMUNES (ATL, CTL, TSB) ---
        # Una vez tenemos la "training_load" (calculada bien o mal), el resto es matemáticas
        df['ATL_7_dias'] = df['training_load'].ewm(span=7, adjust=False).mean().round(2)
        df['CTL_42_dias'] = df['training_load'].ewm(span=42, adjust=False).mean().round(2)
        df['TSB'] = (df['CTL_42_dias'] - df['ATL_7_dias']).round(2)

        # Cálculo de Mejora (Simplificado)
        total_actividades = len(df)
        if total_actividades > 5:
            punto_medio = total_actividades // 2
            ritmo_antiguo = df.head(punto_medio)['pace_min_km'].mean()
            ritmo_reciente = df.tail(total_actividades - punto_medio)['pace_min_km'].mean()
            mejora_pct = ((ritmo_antiguo - ritmo_reciente) / ritmo_antiguo * 100).round(2)
        else:
            mejora_pct = 0

        # Guardado (Tu código original)
        if save_path:
            # ... (Mismo código de guardado que tenías) ...
            try:
                if save_format == 'csv': df.to_csv(save_path, index=False)
                # ... etc ...
            except Exception as e:
                print(f"Error guardando: {e}")

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


       