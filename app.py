import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
import io
from shapely.geometry import Polygon, Point
import math
import requests
import rasterio
from rasterio.mask import mask
import json
import folium
from streamlit_folium import folium_static, st_folium
import ee
import geemap
from geemap import foliumap
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# CONFIGURACIÓN INICIAL Y AUTENTICACIÓN
# =============================================================================

# Configurar página de Streamlit
st.set_page_config(
    page_title="🌱 Analizador Forrajero GEE",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("🌱 ANALIZADOR FORRAJERO - SENTINEL-2 & GOOGLE SATELLITE")
st.markdown("---")

# Configuración para shapefiles
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Intentar inicializar Earth Engine
def initialize_earth_engine():
    """Inicializa Earth Engine con manejo de errores"""
    try:
        # Para uso local, necesitarás autenticarte
        # ee.Authenticate()  # Descomenta la primera vez
        ee.Initialize(project='ee-forrajes')
        return True
    except Exception as e:
        st.warning(f"""
        ⚠️ Earth Engine no está inicializado. Algunas funciones estarán limitadas.
        
        **Para habilitar todas las funciones:**
        1. Ejecuta `ee.Authenticate()` en tu entorno
        2. Asegúrate de tener una cuenta de Google Earth Engine
        3. Solicita acceso a https://earthengine.google.com/
        
        Error: {str(e)}
        """)
        return False

# Inicializar Earth Engine
ee_initialized = initialize_earth_engine()

# =============================================================================
# CLASES PARA PROCESAMIENTO SATELITAL
# =============================================================================

class Sentinel2Processor:
    """Procesador de imágenes Sentinel-2 harmonizadas"""
    
    def __init__(self):
        self.scale = 10  # Resolución 10m
        self.bands = ['B2', 'B3', 'B4', 'B8', 'B11', 'B12']  # Bandas principales
        
    def get_sentinel2_collection(self, geometry, start_date, end_date, cloud_filter=20):
        """Obtiene colección Sentinel-2 harmonizada filtrada"""
        try:
            if not ee_initialized:
                return None
                
            # Colección Sentinel-2 harmonizada
            collection = (ee.ImageCollection('COPERNICUS/S2_HARMONIZED')
                         .filterBounds(geometry)
                         .filterDate(start_date, end_date)
                         .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloud_filter))
                         .select(self.bands))
            
            return collection
        except Exception as e:
            st.error(f"Error obteniendo colección Sentinel-2: {e}")
            return None
    
    def calculate_vegetation_indices(self, image):
        """Calcula todos los índices de vegetación para una imagen"""
        try:
            # NDVI
            ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
            
            # EVI
            evi = image.expression(
                '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))',
                {
                    'NIR': image.select('B8'),
                    'RED': image.select('B4'),
                    'BLUE': image.select('B2')
                }
            ).rename('EVI')
            
            # SAVI
            savi = image.expression(
                '1.5 * ((NIR - RED) / (NIR + RED + 0.5))',
                {
                    'NIR': image.select('B8'),
                    'RED': image.select('B4')
                }
            ).rename('SAVI')
            
            # MSAVI2
            msavi2 = image.expression(
                '(2 * NIR + 1 - sqrt(pow((2 * NIR + 1), 2) - 8 * (NIR - RED))) / 2',
                {
                    'NIR': image.select('B8'),
                    'RED': image.select('B4')
                }
            ).rename('MSAVI2')
            
            # BSI - Bare Soil Index
            bsi = image.expression(
                '((RED + SWIR1) - (NIR + BLUE)) / ((RED + SWIR1) + (NIR + BLUE))',
                {
                    'BLUE': image.select('B2'),
                    'RED': image.select('B4'),
                    'NIR': image.select('B8'),
                    'SWIR1': image.select('B11')
                }
            ).rename('BSI')
            
            # NDBI - Built-Up Index
            ndbi = image.normalizedDifference(['B11', 'B8']).rename('NDBI')
            
            # Añadir todas las bandas a la imagen
            image_with_indices = image.addBands([ndvi, evi, savi, msavi2, bsi, ndbi])
            
            return image_with_indices
            
        except Exception as e:
            st.error(f"Error calculando índices: {e}")
            return image
    
    def get_best_image(self, geometry, target_date, days_buffer=30, cloud_filter=20):
        """Obtiene la mejor imagen alrededor de la fecha objetivo"""
        try:
            if not ee_initialized:
                return None
                
            start_date = ee.Date(target_date).advance(-days_buffer, 'day')
            end_date = ee.Date(target_date).advance(days_buffer, 'day')
            
            collection = self.get_sentinel2_collection(geometry, start_date, end_date, cloud_filter)
            
            if collection is None:
                return None
                
            # Ordenar por nubosidad y proximidad a fecha objetivo
            def add_date_difference(img):
                date_diff = ee.Number(img.date().difference(ee.Date(target_date), 'day')).abs()
                return img.set('date_difference', date_diff)
            
            collection = collection.map(add_date_difference)
            collection = collection.sort('date_difference').sort('CLOUDY_PIXEL_PERCENTAGE')
            
            best_image = collection.first()
            
            # Calcular índices de vegetación
            best_image = self.calculate_vegetation_indices(best_image)
            
            return best_image
            
        except Exception as e:
            st.error(f"Error obteniendo mejor imagen: {e}")
            return None
    
    def extract_values_for_geometry(self, image, geometry, scale=10):
        """Extrae valores de píxeles para una geometría dada"""
        try:
            if not ee_initialized or image is None:
                return None
                
            # Reducir región para obtener estadísticas
            stats = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=scale,
                maxPixels=1e9
            )
            
            # Obtener valores
            values = stats.getInfo()
            
            return values
            
        except Exception as e:
            st.error(f"Error extrayendo valores: {e}")
            return None

class MapVisualizer:
    """Clase para visualización de mapas interactivos"""
    
    def __init__(self):
        self.sentinel_processor = Sentinel2Processor()
        
    def create_base_map(self, gdf, map_type="google_satellite", zoom_start=13):
        """Crea mapa base con diferentes opciones"""
        try:
            # Calcular centro y bounds
            centroid = gdf.geometry.centroid.iloc[0]
            bounds = gdf.total_bounds
            
            # Crear mapa centrado
            m = folium.Map(
                location=[centroid.y, centroid.x],
                zoom_start=zoom_start,
                control_scale=True
            )
            
            # Añadir capas base según selección
            if map_type == "google_satellite":
                folium.TileLayer(
                    tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                    attr='Google Satellite',
                    name='Google Satellite',
                    overlay=False,
                    control=True
                ).add_to(m)
                
                # Añadir capa de etiquetas
                folium.TileLayer(
                    tiles='https://mt1.google.com/vt/lyrs=h&x={x}&y={y}&z={z}',
                    attr='Google Labels',
                    name='Google Labels',
                    overlay=True,
                    control=True
                ).add_to(m)
                
            elif map_type == "world_imagery":
                folium.TileLayer(
                    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                    attr='Esri World Imagery',
                    name='World Imagery',
                    overlay=False,
                    control=True
                ).add_to(m)
                
            elif map_type == "topographic":
                folium.TileLayer(
                    tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
                    attr='OpenTopoMap',
                    name='Topographic',
                    overlay=False,
                    control=True
                ).add_to(m)
            
            # Añadir capa por defecto
            folium.TileLayer(
                tiles='OpenStreetMap',
                name='OpenStreetMap',
                overlay=False,
                control=True
            ).add_to(m)
            
            # Añadir polígonos al mapa
            self._add_polygons_to_map(m, gdf)
            
            # Ajustar vista al bounds
            m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
            
            # Añadir control de capas
            folium.LayerControl().add_to(m)
            
            return m
            
        except Exception as e:
            st.error(f"Error creando mapa base: {e}")
            return None
    
    def _add_polygons_to_map(self, m, gdf):
        """Añade polígonos al mapa con estilo y tooltips"""
        try:
            # Definir colores según tipo de dato disponible
            if 'tipo_superficie' in gdf.columns:
                color_map = {
                    'SUELO_DESNUDO': '#d73027',
                    'SUELO_PARCIAL': '#fdae61', 
                    'VEGETACION_ESCASA': '#fee08b',
                    'VEGETACION_MODERADA': '#a6d96a',
                    'VEGETACION_DENSA': '#1a9850'
                }
            else:
                color_map = {'default': '#3388ff'}
            
            # Función de estilo
            def style_function(feature):
                if 'tipo_superficie' in feature['properties']:
                    color = color_map.get(feature['properties']['tipo_superficie'], '#3388ff')
                else:
                    color = '#3388ff'
                    
                return {
                    'fillColor': color,
                    'color': '#000000',
                    'weight': 2,
                    'fillOpacity': 0.6
                }
            
            # Función de tooltip
            def highlight_function(feature):
                return {
                    'fillColor': '#ffff00',
                    'color': '#000000',
                    'weight': 3,
                    'fillOpacity': 0.7
                }
            
            # Añadir GeoJSON
            geojson = folium.GeoJson(
                gdf.__geo_interface__,
                style_function=style_function,
                highlight_function=highlight_function,
                tooltip=folium.GeoJsonTooltip(
                    fields=[col for col in gdf.columns if col != 'geometry'],
                    aliases=[col.upper() for col in gdf.columns if col != 'geometry'],
                    localize=True,
                    sticky=False
                )
            ).add_to(m)
            
        except Exception as e:
            st.error(f"Error añadiendo polígonos al mapa: {e}")
    
    def create_sentinel_map(self, gdf, target_date, cloud_filter=20, index_type='NDVI'):
        """Crea mapa con datos Sentinel-2 superpuestos"""
        try:
            if not ee_initialized:
                st.warning("Earth Engine no disponible. Usando mapa base.")
                return self.create_base_map(gdf, "google_satellite")
            
            # Convertir a geometría Earth Engine
            geojson_dict = json.loads(gdf.to_json())
            geometry = ee.Geometry(geojson_dict['features'][0]['geometry'])
            
            # Obtener mejor imagen
            with st.spinner("🛰️ Obteniendo imagen Sentinel-2..."):
                image = self.sentinel_processor.get_best_image(geometry, target_date, cloud_filter)
            
            if image is None:
                st.warning("No se pudo obtener imagen Sentinel-2. Usando mapa base.")
                return self.create_base_map(gdf, "google_satellite")
            
            # Configuración de visualización según índice
            vis_params = self._get_visualization_params(index_type)
            
            # Crear mapa con geemap
            Map = geemap.Map(center=[gdf.geometry.centroid.iloc[0].y, gdf.geometry.centroid.iloc[0].x], zoom=13)
            
            # Añadir capa base
            Map.add_basemap('SATELLITE')
            
            # Añadir capa Sentinel-2
            Map.addLayer(image.select(index_type), vis_params, f'Sentinel-2 {index_type}')
            
            # Añadir polígonos
            Map.add_gdf(gdf, layer_name="Sub-Lotes", style={'color': 'red', 'weight': 3, 'fillOpacity': 0})
            
            # Añadir control de capas
            Map.add_layer_control()
            
            return Map
            
        except Exception as e:
            st.error(f"Error creando mapa Sentinel: {e}")
            return self.create_base_map(gdf, "google_satellite")
    
    def _get_visualization_params(self, index_type):
        """Obtiene parámetros de visualización para cada índice"""
        vis_params = {
            'NDVI': {'min': -1, 'max': 1, 'palette': ['red', 'yellow', 'green']},
            'EVI': {'min': -1, 'max': 1, 'palette': ['red', 'yellow', 'green']},
            'SAVI': {'min': -1, 'max': 1, 'palette': ['red', 'yellow', 'green']},
            'MSAVI2': {'min': -1, 'max': 1, 'palette': ['red', 'yellow', 'green']},
            'BSI': {'min': -1, 'max': 1, 'palette': ['blue', 'white', 'brown']},
            'NDBI': {'min': -1, 'max': 1, 'palette': ['blue', 'cyan', 'purple']}
        }
        return vis_params.get(index_type, {'min': -1, 'max': 1, 'palette': ['red', 'yellow', 'green']})

# =============================================================================
# CONFIGURACIÓN DE PARÁMETROS FORRAJEROS
# =============================================================================

# Parámetros forrajeros (mantener tu código existente)
PARAMETROS_FORRAJEROS_BASE = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 4000,
        'CRECIMIENTO_DIARIO': 80,
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'DIGESTIBILIDAD': 0.65,
        'PROTEINA_CRUDA': 0.18,
        'TASA_UTILIZACION_RECOMENDADA': 0.65,
        'FACTOR_BIOMASA_NDVI': 2800,
        'FACTOR_BIOMASA_EVI': 3000,
        'FACTOR_BIOMASA_SAVI': 2900,
        'OFFSET_BIOMASA': -600,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.45,
        'UMBRAL_BSI_SUELO': 0.4,
        'UMBRAL_NDBI_SUELO': 0.15,
        'FACTOR_COBERTURA': 0.8
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'DIGESTIBILIDAD': 0.70,
        'PROTEINA_CRUDA': 0.15,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
        'FACTOR_BIOMASA_NDVI': 2500,
        'FACTOR_BIOMASA_EVI': 2700,
        'FACTOR_BIOMASA_SAVI': 2600,
        'OFFSET_BIOMASA': -500,
        'UMBRAL_NDVI_SUELO': 0.18,
        'UMBRAL_NDVI_PASTURA': 0.50,
        'UMBRAL_BSI_SUELO': 0.35,
        'UMBRAL_NDBI_SUELO': 0.12,
        'FACTOR_COBERTURA': 0.85
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 50,
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'DIGESTIBILIDAD': 0.60,
        'PROTEINA_CRUDA': 0.12,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
        'FACTOR_BIOMASA_NDVI': 2200,
        'FACTOR_BIOMASA_EVI': 2400,
        'FACTOR_BIOMASA_SAVI': 2300,
        'OFFSET_BIOMASA': -400,
        'UMBRAL_NDVI_SUELO': 0.20,
        'UMBRAL_NDVI_PASTURA': 0.55,
        'UMBRAL_BSI_SUELO': 0.30,
        'UMBRAL_NDBI_SUELO': 0.10,
        'FACTOR_COBERTURA': 0.75
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 2800,
        'CRECIMIENTO_DIARIO': 45,
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'DIGESTIBILIDAD': 0.55,
        'PROTEINA_CRUDA': 0.10,
        'TASA_UTILIZACION_RECOMENDADA': 0.50,
        'FACTOR_BIOMASA_NDVI': 2000,
        'FACTOR_BIOMASA_EVI': 2200,
        'FACTOR_BIOMASA_SAVI': 2100,
        'OFFSET_BIOMASA': -300,
        'UMBRAL_NDVI_SUELO': 0.25,
        'UMBRAL_NDVI_PASTURA': 0.60,
        'UMBRAL_BSI_SUELO': 0.25,
        'UMBRAL_NDBI_SUELO': 0.08,
        'FACTOR_COBERTURA': 0.70
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 2500,
        'CRECIMIENTO_DIARIO': 20,
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'DIGESTIBILIDAD': 0.50,
        'PROTEINA_CRUDA': 0.08,
        'TASA_UTILIZACION_RECOMENDADA': 0.45,
        'FACTOR_BIOMASA_NDVI': 1800,
        'FACTOR_BIOMASA_EVI': 2000,
        'FACTOR_BIOMASA_SAVI': 1900,
        'OFFSET_BIOMASA': -200,
        'UMBRAL_NDVI_SUELO': 0.30,
        'UMBRAL_NDVI_PASTURA': 0.65,
        'UMBRAL_BSI_SUELO': 0.20,
        'UMBRAL_NDBI_SUELO': 0.05,
        'FACTOR_COBERTURA': 0.60
    }
}

def obtener_parametros_forrajeros(tipo_pastura, custom_params=None):
    """Obtiene parámetros según tipo de pastura"""
    if tipo_pastura == "PERSONALIZADO" and custom_params:
        return custom_params
    else:
        return PARAMETROS_FORRAJEROS_BASE.get(tipo_pastura, PARAMETROS_FORRAJEROS_BASE['FESTUCA'])

# =============================================================================
# FUNCIONES DE ANÁLISIS ESPACIAL
# =============================================================================

def calcular_superficie(gdf):
    """Calcula superficie en hectáreas"""
    try:
        if gdf.crs and gdf.crs.is_geographic:
            # Reproyectar a un CRS proyectado para cálculo de área
            gdf_proj = gdf.to_crs('EPSG:3857')
            area_m2 = gdf_proj.geometry.area
        else:
            area_m2 = gdf.geometry.area
        
        return area_m2 / 10000  # Convertir a hectáreas
    except Exception as e:
        st.error(f"Error calculando superficie: {e}")
        return gdf.geometry.area / 10000

def dividir_potrero_en_subLotes(gdf, n_zonas):
    """Divide el potrero en sub-lotes rectangulares"""
    if len(gdf) == 0:
        return gdf
    
    try:
        potrero_principal = gdf.iloc[0].geometry
        bounds = potrero_principal.bounds
        minx, miny, maxx, maxy = bounds
        
        sub_poligonos = []
        
        n_cols = math.ceil(math.sqrt(n_zonas))
        n_rows = math.ceil(n_zonas / n_cols)
        
        width = (maxx - minx) / n_cols
        height = (maxy - miny) / n_rows
        
        for i in range(n_rows):
            for j in range(n_cols):
                if len(sub_poligonos) >= n_zonas:
                    break
                    
                cell_minx = minx + (j * width)
                cell_maxx = minx + ((j + 1) * width)
                cell_miny = miny + (i * height)
                cell_maxy = miny + ((i + 1) * height)
                
                cell_poly = Polygon([
                    (cell_minx, cell_miny),
                    (cell_maxx, cell_miny),
                    (cell_maxx, cell_maxy),
                    (cell_minx, cell_maxy)
                ])
                
                intersection = potrero_principal.intersection(cell_poly)
                if not intersection.is_empty and intersection.area > 0:
                    sub_poligonos.append(intersection)
        
        if sub_poligonos:
            nuevo_gdf = gpd.GeoDataFrame({
                'id_subLote': range(1, len(sub_poligonos) + 1),
                'geometry': sub_poligonos
            }, crs=gdf.crs)
            return nuevo_gdf
        else:
            return gdf
            
    except Exception as e:
        st.error(f"Error dividiendo potrero: {e}")
        return gdf

# =============================================================================
# SIDEBAR - CONFIGURACIÓN
# =============================================================================

# Inicializar session state
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'analisis_completo' not in st.session_state:
    st.session_state.analisis_completo = False
if 'mapa_actual' not in st.session_state:
    st.session_state.mapa_actual = None

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración Principal")
    
    # Selección de fuente satelital
    st.subheader("🛰️ Fuente de Datos")
    fuente_satelital = st.selectbox(
        "Seleccionar satélite:",
        ["SENTINEL-2", "LANDSAT-8", "LANDSAT-9", "SIMULADO"],
        help="Sentinel-2: Mayor resolución (10m)"
    )
    
    # Selección de mapa base
    st.subheader("🗺️ Mapa Base")
    mapa_base = st.selectbox(
        "Tipo de mapa base:",
        ["google_satellite", "world_imagery", "topographic", "openstreetmap"],
        format_func=lambda x: x.replace('_', ' ').title(),
        help="Selecciona la base cartográfica"
    )
    
    # Configuración de fechas
    st.subheader("📅 Configuración Temporal")
    fecha_imagen = st.date_input(
        "Fecha de imagen satelital:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now(),
        help="Selecciona la fecha para la imagen satelital"
    )
    
    nubes_max = st.slider("Máximo % de nubes:", 0, 100, 20)
    
    # Tipo de pastura
    st.subheader("🌿 Tipo de Pastura")
    tipo_pastura = st.selectbox(
        "Seleccionar tipo:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"]
    )
    
    # Parámetros de detección
    st.subheader("🔍 Parámetros de Detección")
    umbral_ndvi_minimo = st.slider("Umbral NDVI mínimo:", 0.1, 0.5, 0.3, 0.01)
    umbral_ndvi_optimo = st.slider("Umbral NDVI óptimo:", 0.5, 0.9, 0.7, 0.01)
    sensibilidad_suelo = st.slider("Sensibilidad suelo:", 0.1, 1.0, 0.7, 0.1)
    
    # Parámetros ganaderos
    st.subheader("🐄 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal:", 50, 1000, 100)
    
    # División del potrero
    st.subheader("📐 División del Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", 12, 32, 24)
    
    # Carga de archivos
    st.subheader("📤 Cargar Datos")
    uploaded_zip = st.file_uploader(
        "Subir ZIP con shapefile:",
        type=['zip'],
        help="Archivo ZIP que contiene el shapefile del potrero"
    )

# =============================================================================
# PROCESAMIENTO DE ARCHIVOS
# =============================================================================

def procesar_archivo_zip(uploaded_zip):
    """Procesa el archivo ZIP y carga el shapefile"""
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)
            
            # Buscar archivos shapefile
            shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
            if not shp_files:
                st.error("❌ No se encontró archivo .shp en el ZIP")
                return None
            
            shp_path = os.path.join(tmp_dir, shp_files[0])
            gdf = gpd.read_file(shp_path)
            
            # Verificar que tenga geometrías válidas
            if len(gdf) == 0:
                st.error("❌ El shapefile no contiene geometrías válidas")
                return None
            
            # Verificar CRS
            if gdf.crs is None:
                st.warning("⚠️ El shapefile no tiene CRS definido. Asumiendo WGS84 (EPSG:4326)")
                gdf = gdf.set_crs('EPSG:4326')
            
            return gdf
            
    except Exception as e:
        st.error(f"❌ Error procesando archivo: {str(e)}")
        return None

# Procesar archivo subido
if uploaded_zip is not None:
    with st.spinner("📁 Cargando y procesando shapefile..."):
        gdf_cargado = procesar_archivo_zip(uploaded_zip)
        if gdf_cargado is not None:
            st.session_state.gdf_cargado = gdf_cargado
            st.success(f"✅ Potrero cargado exitosamente!")
            
            # Mostrar información del potrero
            area_total = calcular_superficie(gdf_cargado).sum()
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Polígonos", len(gdf_cargado))
            with col2:
                st.metric("Área Total", f"{area_total:.1f} ha")
            with col3:
                st.metric("Pastura", tipo_pastura)
            with col4:
                st.metric("Satélite", fuente_satelital)

# =============================================================================
# VISUALIZACIÓN DE MAPAS
# =============================================================================

def mostrar_mapa_interactivo(gdf, mapa_tipo, fecha_imagen=None, nubes_max=20, index_type='NDVI'):
    """Muestra mapa interactivo según la configuración"""
    
    visualizador = MapVisualizer()
    
    if mapa_tipo == "sentinel_ndvi" and fecha_imagen and ee_initialized:
        with st.spinner("🛰️ Cargando imagen Sentinel-2..."):
            mapa = visualizador.create_sentinel_map(gdf, fecha_imagen, nubes_max, index_type)
    else:
        with st.spinner("🗺️ Cargando mapa base..."):
            mapa = visualizador.create_base_map(gdf, mapa_tipo)
    
    if mapa is not None:
        # Mostrar mapa
        if isinstance(mapa, geemap.Map):
            # Usar geemap para mapas de Earth Engine
            mapa.to_streamlit(height=600)
        else:
            # Usar streamlit-folium para mapas Folium normales
            folium_static(mapa, width=1000, height=600)
        
        st.session_state.mapa_actual = mapa
        return mapa
    else:
        st.error("❌ No se pudo cargar el mapa")
        return None

# =============================================================================
# ANÁLISIS FORRAJERO MEJORADO
# =============================================================================

def analisis_forrajero_completo(gdf, config):
    """Función principal de análisis forrajero"""
    try:
        st.header("🌱 ANÁLISIS FORRAJERO COMPLETO")
        
        # PASO 1: Mostrar mapa inicial
        st.subheader("🗺️ MAPA INICIAL DEL POTRERO")
        mostrar_mapa_interactivo(
            gdf, 
            config['mapa_base'],
            config['fecha_imagen'],
            config['nubes_max']
        )
        
        # PASO 2: Dividir potrero
        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES")
        with st.spinner("Dividiendo potrero..."):
            gdf_dividido = dividir_potrero_en_subLotes(gdf, config['n_divisiones'])
        
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # Mostrar mapa dividido
        st.subheader("🗺️ POTRERO DIVIDIDO")
        mostrar_mapa_interactivo(
            gdf_dividido,
            config['mapa_base'],
            config['fecha_imagen'],
            config['nubes_max']
        )
        
        # PASO 3: Análisis con Sentinel-2 si está disponible
        if ee_initialized and config['fuente_satelital'] == 'SENTINEL-2':
            st.subheader("🛰️ ANÁLISIS CON SENTINEL-2")
            with st.spinner("Analizando con Sentinel-2..."):
                # Aquí iría tu análisis detallado con Sentinel-2
                resultados = analizar_con_sentinel(gdf_dividido, config)
        else:
            st.subheader("📊 ANÁLISIS SIMULADO")
            with st.spinner("Realizando análisis..."):
                # Análisis simulado como fallback
                resultados = analisis_simulado(gdf_dividido, config)
        
        # PASO 4: Mostrar resultados
        mostrar_resultados(resultados, config)
        
        st.session_state.analisis_completo = True
        return True
        
    except Exception as e:
        st.error(f"❌ Error en análisis: {str(e)}")
        import traceback
        st.error(f"Detalle: {traceback.format_exc()}")
        return False

def analizar_con_sentinel(gdf, config):
    """Análisis usando datos reales de Sentinel-2"""
    try:
        processor = Sentinel2Processor()
        visualizador = MapVisualizer()
        
        # Convertir a geometría EE
        geojson_dict = json.loads(gdf.to_json())
        geometry = ee.Geometry(geojson_dict['features'][0]['geometry'])
        
        # Obtener imagen
        image = processor.get_best_image(
            geometry, 
            config['fecha_imagen'],
            cloud_filter=config['nubes_max']
        )
        
        if image:
            st.success("✅ Imagen Sentinel-2 obtenida exitosamente")
            
            # Mostrar mapa con NDVI
            st.subheader("🟢 MAPA DE NDVI - SENTINEL-2")
            mapa_sentinel = visualizador.create_sentinel_map(
                gdf, config['fecha_imagen'], config['nubes_max'], 'NDVI'
            )
            
            # Extraer valores para análisis
            resultados = []
            for idx, row in gdf.iterrows():
                sub_geometry = ee.Geometry(json.loads(gpd.GeoSeries([row.geometry]).to_json())['features'][0]['geometry'])
                valores = processor.extract_values_for_geometry(image, sub_geometry)
                
                if valores:
                    resultados.append({
                        'id_subLote': row['id_subLote'],
                        'ndvi': valores.get('NDVI', 0),
                        'evi': valores.get('EVI', 0),
                        'savi': valores.get('SAVI', 0),
                        'area_ha': calcular_superficie(gpd.GeoDataFrame([row], crs=gdf.crs))
                    })
            
            return resultados
        else:
            st.warning("⚠️ No se pudo obtener imagen Sentinel-2. Usando análisis simulado.")
            return analisis_simulado(gdf, config)
            
    except Exception as e:
        st.error(f"Error en análisis Sentinel: {e}")
        return analisis_simulado(gdf, config)

def analisis_simulado(gdf, config):
    """Análisis simulado cuando no hay datos reales"""
    resultados = []
    
    for idx, row in gdf.iterrows():
        # Simular valores basados en posición
        centroid = row.geometry.centroid
        x_norm = (centroid.x - gdf.total_bounds[0]) / (gdf.total_bounds[2] - gdf.total_bounds[0])
        y_norm = (centroid.y - gdf.total_bounds[1]) / (gdf.total_bounds[3] - gdf.total_bounds[1])
        
        # Simular NDVI con patrón espacial
        ndvi_base = 0.3 + (x_norm * y_norm * 0.4)
        ndvi = max(0.1, min(0.8, ndvi_base + np.random.normal(0, 0.1)))
        
        resultados.append({
            'id_subLote': row['id_subLote'],
            'ndvi': ndvi,
            'evi': ndvi * 1.1,
            'savi': ndvi * 1.05,
            'area_ha': calcular_superficie(gpd.GeoDataFrame([row], crs=gdf.crs))[0],
            'tipo_superficie': clasificar_superficie(ndvi),
            'biomasa_kg_ms_ha': calcular_biomasa_simulada(ndvi, config['tipo_pastura'])
        })
    
    return resultados

def clasificar_superficie(ndvi):
    """Clasifica el tipo de superficie basado en NDVI"""
    if ndvi < 0.2:
        return "SUELO_DESNUDO"
    elif ndvi < 0.4:
        return "VEGETACION_ESCASA"
    elif ndvi < 0.6:
        return "VEGETACION_MODERADA"
    else:
        return "VEGETACION_DENSA"

def calcular_biomasa_simulada(ndvi, tipo_pastura):
    """Calcula biomasa simulada basada en NDVI y tipo de pastura"""
    params = obtener_parametros_forrajeros(tipo_pastura)
    biomasa_base = params['MS_POR_HA_OPTIMO'] * ndvi
    return max(0, biomasa_base * (0.5 + ndvi * 0.5))

def mostrar_resultados(resultados, config):
    """Muestra los resultados del análisis"""
    st.header("📊 RESULTADOS DEL ANÁLISIS")
    
    if not resultados:
        st.warning("No hay resultados para mostrar")
        return
    
    # Convertir a DataFrame
    df_resultados = pd.DataFrame(resultados)
    
    # Métricas principales
    st.subheader("📈 MÉTRICAS PRINCIPALES")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        ndvi_prom = df_resultados['ndvi'].mean()
        st.metric("NDVI Promedio", f"{ndvi_prom:.3f}")
    
    with col2:
        area_total = df_resultados['area_ha'].sum()
        st.metric("Área Total", f"{area_total:.1f} ha")
    
    with col3:
        biomasa_prom = df_resultados.get('biomasa_kg_ms_ha', [0]).mean()
        st.metric("Biomasa Promedio", f"{biomasa_prom:.0f} kg MS/ha")
    
    with col4:
        vegetacion_densa = len([r for r in resultados if r.get('tipo_superficie') == 'VEGETACION_DENSA'])
        st.metric("Sub-lotes Óptimos", vegetacion_densa)
    
    # Gráficos
    st.subheader("📊 GRÁFICOS DE ANÁLISIS")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Histograma de NDVI
        fig_ndvi = px.histogram(df_resultados, x='ndvi', 
                               title='Distribución de NDVI',
                               labels={'ndvi': 'NDVI', 'count': 'Número de Sub-lotes'})
        st.plotly_chart(fig_ndvi, use_container_width=True)
    
    with col2:
        # Scatter plot de área vs NDVI
        if 'area_ha' in df_resultados.columns and 'ndvi' in df_resultados.columns:
            fig_scatter = px.scatter(df_resultados, x='area_ha', y='ndvi',
                                   color='tipo_superficie' if 'tipo_superficie' in df_resultados.columns else None,
                                   title='Relación Área vs NDVI',
                                   labels={'area_ha': 'Área (ha)', 'ndvi': 'NDVI'})
            st.plotly_chart(fig_scatter, use_container_width=True)
    
    # Tabla de resultados
    st.subheader("📋 DETALLES POR SUB-LOTE")
    st.dataframe(df_resultados, use_container_width=True)
    
    # Botón de descarga
    csv = df_resultados.to_csv(index=False)
    st.download_button(
        label="📥 Descargar Resultados (CSV)",
        data=csv,
        file_name=f"resultados_forrajeros_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv"
    )

# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================

# Sección de mapa interactivo
st.markdown("## 🗺️ VISUALIZACIÓN INTERACTIVA")

if st.session_state.gdf_cargado is not None:
    # Selector de tipo de visualización
    col1, col2 = st.columns([1, 4])
    
    with col1:
        tipo_visualizacion = st.selectbox(
            "Tipo de visualización:",
            ["google_satellite", "sentinel_ndvi", "world_imagery", "topographic"],
            format_func=lambda x: x.replace('_', ' ').title()
        )
        
        if tipo_visualizacion == "sentinel_ndvi":
            indice_seleccionado = st.selectbox(
                "Índice a visualizar:",
                ["NDVI", "EVI", "SAVI", "MSAVI2", "BSI", "NDBI"]
            )
        else:
            indice_seleccionado = "NDVI"
    
    # Mostrar mapa
    mostrar_mapa_interactivo(
        st.session_state.gdf_cargado,
        tipo_visualizacion,
        fecha_imagen,
        nubes_max,
        indice_seleccionado
    )
else:
    st.info("""
    ## 📋 INSTRUCCIONES DE USO
    
    1. **Configura los parámetros** en la barra lateral
    2. **Sube el archivo ZIP** con el shapefile del potrero
    3. **Visualiza el mapa** interactivo
    4. **Ejecuta el análisis** forrajero completo
    
    ### 🛰️ CARACTERÍSTICAS:
    
    **Sentinel-2 Harmonized:**
    - Resolución: 10 metros
    - Índices: NDVI, EVI, SAVI, MSAVI2, BSI, NDBI
    - Frecuencia: 5 días
    
    **Google Satellite:**
    - Imágenes de alta resolución
    - Base cartográfica actualizada
    - Perfecta para referencia visual
    
    **Análisis Forrajero:**
    - Biomasa disponible
    - Equivalentes vaca
    - Días de permanencia
    - Recomendaciones de manejo
    """)

# Botón de análisis principal
st.markdown("---")
st.markdown("## 🚀 ANÁLISIS FORRAJERO COMPLETO")

if st.session_state.gdf_cargado is not None:
    if st.button("🎯 EJECUTAR ANÁLISIS FORRAJERO COMPLETO", 
                type="primary", 
                use_container_width=True,
                key="analisis_completo"):
        
        config = {
            'fuente_satelital': fuente_satelital,
            'mapa_base': mapa_base,
            'fecha_imagen': fecha_imagen,
            'nubes_max': nubes_max,
            'tipo_pastura': tipo_pastura,
            'peso_promedio': peso_promedio,
            'carga_animal': carga_animal,
            'n_divisiones': n_divisiones,
            'umbral_ndvi_minimo': umbral_ndvi_minimo,
            'umbral_ndvi_optimo': umbral_ndvi_optimo,
            'sensibilidad_suelo': sensibilidad_suelo
        }
        
        with st.spinner("🔬 Ejecutando análisis forrajero completo..."):
            resultado = analisis_forrajero_completo(st.session_state.gdf_cargado, config)
            
        if resultado:
            st.balloons()
            st.success("🎉 ¡Análisis completado exitosamente!")
else:
    st.warning("⚠️ Por favor, carga un shapefile para ejecutar el análisis")

# =============================================================================
# PIE DE PÁGINA
# =============================================================================

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>🌱 <strong>Analizador Forrajero GEE</strong> - Desarrollado con Sentinel-2 & Google Earth Engine</p>
    <p>📧 Soporte: soporte@forrajes.com | 🐛 Reportar issues: GitHub</p>
</div>
""", unsafe_allow_html=True)
