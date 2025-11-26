import requests
import json
import os
import time
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, Column, BigInteger, String, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv, set_key, find_dotenv
load_dotenv()

# Crear base para los modelos ORM
Base = declarative_base()


# ==================== MODELO: Activity ====================
class Activity(Base):
    """
    Modelo ORM para la tabla 'activities' en PostgreSQL.
    Define el esquema explícito con tipos de datos correctos.
    """
    __tablename__ = 'activities'
    
    # Primary Key
    id = Column(BigInteger, primary_key=True)
    
    # Información básica
    name = Column(String(500), nullable=True)
    description = Column(String(5000), nullable=True)
    
    # Fecha y hora (indexada para ordenamiento rápido)
    start_date_local = Column(DateTime, index=True, nullable=True)
    
    # Distancia y tiempo
    distance_km = Column(Float, nullable=True)
    moving_time_min = Column(Float, nullable=True)
    elevation_gain_m = Column(Float, nullable=True)
    
    # Velocidad y ritmo
    average_speed_kmh = Column(Float, nullable=True)
    pace_min_km = Column(Float, nullable=True)
    
    # Datos de pulso (Heart Rate)
    average_heartrate = Column(Float, nullable=True)
    max_heartrate = Column(Float, nullable=True)
    
    # Splits por kilómetro (JSONB en PostgreSQL)
    km_splits_json = Column(JSON, nullable=True)
    
    # Métricas de coaching
    training_load = Column(Float, nullable=True)
    intensity_factor = Column(Float, nullable=True)
    training_zone = Column(String(10), nullable=True)
    calculation_method = Column(String(50), nullable=True)  # 'Heart Rate', 'Pace', 'Statistical'
    
    def __repr__(self):
        return f"<Activity(id={self.id}, name='{self.name}', date={self.start_date_local})>"


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
        
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            db_url = "postgresql+psycopg2://strava_user:strava_pass@localhost:5432/strava_db"
        self.engine = create_engine(db_url)
        
        # Crear las tablas automáticamente al inicializar el cliente
        Base.metadata.create_all(self.engine)
        
        # Crear session factory
        self.Session = sessionmaker(bind=self.engine)

        
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
        
        try:
            # En vez de pd.read_csv('activities.csv'), leemos de SQL
            df_existing = pd.read_sql("SELECT * FROM activities", self.engine)
            processed_ids = set(df_existing['id'].astype(str))
        except Exception:
            # Si la tabla no existe en Postgres, no pasa nada, empezamos de cero
            pass
        
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
        
        msg = f"\nDescargando {pending_count} nuevas actividades (Total en BD: {total_ids})..."
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
            
            # Manejo de JSON: SQLAlchemy Column(JSON) puede manejar tanto dicts como strings
            # Pero para PostgreSQL JSONB, es mejor mantener como dict
            # Solo convertir a JSON string si es necesario
            if 'km_splits_json' in df_new.columns:
                # Asegurar que es JSON (puede venir como dict o list)
                # No convertir a string: SQLAlchemy se encarga
                df_new['km_splits_json'] = df_new['km_splits_json'].apply(
                    lambda x: x if isinstance(x, (dict, list, type(None))) else json.loads(x) if isinstance(x, str) else None
                )
            
            # Guardar en PostgreSQL
            try:
                df_new.to_sql('activities', self.engine, if_exists='append', index=False, dtype={
                    'id': BigInteger,
                    'average_heartrate': Float,
                    'max_heartrate': Float,
                    'km_splits_json': JSON,
                })
                print(f"✓ {len(df_new)} actividades guardadas en PostgreSQL")
            except Exception as e:
                print(f"⚠ Error guardando en PostgreSQL: {e}. Intentando modo compatibilidad...")
                # Fallback: guardar a CSV como respaldo
                try:
                    df_new.to_csv('activities_backup.csv', index=False, mode='a', header=False)
                    print(f"✓ Datos guardados en backup CSV: activities_backup.csv")
                except Exception as csv_error:
                    print(f"✗ Error en backup: {csv_error}")
            
            df_result = pd.concat([df_existing, df_new], ignore_index=True) if not df_existing.empty else df_new
            return df_result
        
        return df_existing
    
    def coaching_metrics(self, df=None, save_path=None, save_format='csv', athlete_zones=None, hr_zones=None):
        """
        Calcula métricas con lógica de cascada (Waterfall):
        PRIORIDAD 1: HR zones (si disponibles y hr_zones definidas)
        PRIORIDAD 2: Pace zones (si disponibles y athlete_zones definidas)
        PRIORIDAD 3: Cálculo estadístico fallback
        
        Lee directamente de PostgreSQL si df no se proporciona.
        """
        if df is None:
            # Cargar directamente de PostgreSQL, ordenado por fecha
            try:
                df = pd.read_sql(
                    "SELECT * FROM activities ORDER BY start_date_local ASC",
                    self.engine
                )
                print(f"✓ Cargadas {len(df)} actividades desde PostgreSQL")
            except Exception as e:
                print(f"✗ Error cargando de PostgreSQL: {e}")
                raise
            
            # Convertir JSON si es necesario
            if 'km_splits_json' in df.columns:
                df['km_splits_json'] = df['km_splits_json'].apply(
                    lambda x: x if isinstance(x, (dict, list, type(None))) 
                    else json.loads(x) if isinstance(x, str) else None
                )

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

    def get_all_activities_sorted(self):
        """
        Obtiene todas las actividades de PostgreSQL, ordenadas por fecha.
        
        No guarda nada en disco; la BD es la fuente de verdad.
        
        Returns:
            pd.DataFrame: Actividades ordenadas por start_date_local (ASC)
        """
        try:
            df = pd.read_sql(
                "SELECT * FROM activities ORDER BY start_date_local ASC",
                self.engine
            )
            print(f"✓ Cargadas {len(df)} actividades desde PostgreSQL (ordenadas por fecha)")
            
            # Convertir JSON si es necesario
            if 'km_splits_json' in df.columns:
                df['km_splits_json'] = df['km_splits_json'].apply(
                    lambda x: x if isinstance(x, (dict, list, type(None))) 
                    else json.loads(x) if isinstance(x, str) else None
                )
            
            return df
        except Exception as e:
            print(f"✗ Error cargando actividades: {e}")
            raise


       