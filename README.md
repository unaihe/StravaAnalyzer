# Strava Coaching Metrics & Data Extractor

Una aplicación interactiva desarrollada en Python y Streamlit diseñada para la extracción automatizada de datos desde la API de Strava. El sistema procesa el historial de actividades de carrera, calcula métricas fisiológicas avanzadas (ATL, CTL, TSB) y genera datasets estructurados y limpios, optimizados para su análisis posterior mediante modelos de Inteligencia Artificial.

## Funcionalidades Principales

* **Gestión de Autenticación OAuth2:** Manejo completo del flujo de autorización con Strava, incluyendo el intercambio de códigos y la renovación automática de tokens de acceso y refresco.
* **Extracción Masiva de Datos:** Script optimizado para iterar sobre la paginación de la API, descargando identificadores de actividades y sus detalles técnicos (ritmos, elevación, tiempos en movimiento).
* **Cálculo de Métricas de Rendimiento:** Implementación de algoritmos para evaluar el estado de forma:
    * **Training Load (Carga):** Basada en volumen e intensidad.
    * **ATL (Acute Training Load):** Fatiga a corto plazo (media exponencial de 7 días).
    * **CTL (Chronic Training Load):** Aptitud física a largo plazo (media exponencial de 42 días).
    * **TSB (Training Stress Balance):** Indicador de frescura o fatiga acumulada.
    * **Clasificación de Zonas:** Segmentación automática de zonas de entrenamiento basada en la desviación del ritmo histórico.
* **Preparación de Datos para IA:** Limpieza y normalización de datos (manejo de valores nulos y outliers) con exportación a formatos estándar (CSV, JSON, Parquet) listos para ser consumidos por LLMs o herramientas de análisis de datos.

## Tecnologías Utilizadas

* **Python 3.x**
* **Streamlit:** Interfaz de usuario para la orquestación del flujo de datos.
* **Pandas & NumPy:** Manipulación de DataFrames y cálculo vectorial de métricas.
* **Requests:** Comunicación HTTP con la API REST de Strava.
* **Python-Dotenv:** Gestión de variables de entorno y seguridad de credenciales.

## Requisitos Previos

Para ejecutar este proyecto, es necesario registrar una aplicación en la configuración de desarrolladores de Strava:

1. Acceder a la configuración de API de Strava.
2. Obtener el `Client ID` y el `Client Secret`.
3. Configurar el "Authorization Callback Domain" como `localhost`.

## Instalación

1. Clonar el repositorio:
   ```bash
   git clone [https://github.com/tu-usuario/nombre-repo.git](https://github.com/tu-usuario/nombre-repo.git)
   cd nombre-repo
