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
import json
import folium
from streamlit_folium import folium_static
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# CONFIGURACIÓN EARTH ENGINE
# =============================================================================

# Configurar página
st.set_page_config(
    page_title="🌱 Analizador Forrajero - Sentinel-2",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🌱 ANALIZADOR FORRAJERO - SENTINEL-2 HARMONIZED")
st.markdown("---")

# Configuración para shapefiles
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Inicializar session state
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'analisis_completado' not in st.session_state:
    st.session_state.analisis_completado = False
if 'ee_initialized' not in st.session_state:
    st.session_state.ee_initialized = False

# Manejo de Earth Engine
try:
    import ee
    import geemap
    from geemap import foliumap
    EE_AVAILABLE = True
except ImportError:
    EE_AVAILABLE = False
    st.sidebar.error("❌ Earth Engine no instalado")

def initialize_earth_engine():
    """Inicializa Earth Engine con manejo de errores"""
    if not EE_AVAILABLE:
        return False
        
    try:
        ee.Initialize()
        st.session_state.ee_initialized = True
        return True
    except ee.EEException as e:
        if "Please authenticate" in str(e):
            show_authentication_instructions()
        else:
            st.sidebar.error(f"❌ Error Earth Engine: {str(e)}")
        return False
    except Exception as e:
        st.sidebar.warning(f"⚠️ Earth Engine: {str(e)}")
        return False

def show_authentication_instructions():
    """Muestra instrucciones de autenticación"""
    with st.sidebar.expander("🔐 CONFIGURAR EARTH ENGINE", expanded=True):
        st.markdown("""
        ### Para usar Sentinel-2 real:
        
        1. **Ejecuta en terminal:**
        ```bash
        earthengine authenticate
        ```
        
        2. **Sigue las instrucciones en el navegador**
        
        3. **Reinicia la aplicación**
        
        📍 **Requiere:** Cuenta de Google Earth Engine aprobada
        """)
        
        if st.button("🔄 Reiniciar App"):
            st.rerun()

# Inicializar Earth Engine
ee_initialized = initialize_earth_engine() if EE_AVAILABLE else False

# =============================================================================
# CLASE PARA SENTINEL-2 REAL
# =============================================================================

class Sentinel2Processor:
    """Procesador de imágenes Sentinel-2 harmonizadas reales"""
    
    def __init__(self):
        self.scale = 10  # Resolución 10m
        self.bands = ['B2', 'B3', 'B4', 'B8', 'B11', 'B12']
        
    def get_sentinel2_collection(self, geometry, start_date, end_date, cloud_filter=20):
        """Obtiene colección Sentinel-2 harmonizada"""
        try:
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
        """Calcula índices de vegetación para imagen Sentinel-2"""
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
            
            image_with_indices = image.addBands([ndvi, evi, savi, msavi2, bsi])
            return image_with_indices
            
        except Exception as e:
            st.error(f"Error calculando índices: {e}")
            return image
    
    def get_best_image(self, geometry, target_date, days_buffer=15, cloud_filter=20):
        """Obtiene la mejor imagen Sentinel-2 alrededor de la fecha objetivo"""
        try:
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
        """Extrae valores de píxeles para una geometría"""
        try:
            if image is None:
                return None
                
            # Reducir región para obtener estadísticas
            stats = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=scale,
                maxPixels=1e9
            )
            
            values = stats.getInfo()
            return values
            
        except Exception as e:
            st.error(f"Error extrayendo valores: {e}")
            return None

# =============================================================================
# PARÁMETROS FORRAJEROS
# =============================================================================

PARAMETROS_FORRAJEROS_BASE = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 4000,
        'CRECIMIENTO_DIARIO': 80,
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'DIGESTIBILIDAD': 0.65,
        'PROTEINA_CRUDA': 0.18,
        'TASA_UTILIZACION_RECOMENDADA': 0.65,
        'FACTOR_BIOMASA_NDVI': 2800,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.45
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'DIGESTIBILIDAD': 0.70,
        'PROTEINA_CRUDA': 0.15,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
        'FACTOR_BIOMASA_NDVI': 2500,
        'UMBRAL_NDVI_SUELO': 0.18,
        'UMBRAL_NDVI_PASTURA': 0.50
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 50,
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'DIGESTIBILIDAD': 0.60,
        'PROTEINA_CRUDA': 0.12,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
        'FACTOR_BIOMASA_NDVI': 2200,
        'UMBRAL_NDVI_SUELO': 0.20,
        'UMBRAL_NDVI_PASTURA': 0.55
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 2800,
        'CRECIMIENTO_DIARIO': 45,
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'DIGESTIBILIDAD': 0.55,
        'PROTEINA_CRUDA': 0.10,
        'TASA_UTILIZACION_RECOMENDADA': 0.50,
        'FACTOR_BIOMASA_NDVI': 2000,
        'UMBRAL_NDVI_SUELO': 0.25,
        'UMBRAL_NDVI_PASTURA': 0.60
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 2500,
        'CRECIMIENTO_DIARIO': 20,
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'DIGESTIBILIDAD': 0.50,
        'PROTEINA_CRUDA': 0.08,
        'TASA_UTILIZACION_RECOMENDADA': 0.45,
        'FACTOR_BIOMASA_NDVI': 1800,
        'UMBRAL_NDVI_SUELO': 0.30,
        'UMBRAL_NDVI_PASTURA': 0.65
    }
}

def obtener_parametros_forrajeros(tipo_pastura):
    """Obtiene parámetros según tipo de pastura"""
    return PARAMETROS_FORRAJEROS_BASE.get(tipo_pastura, PARAMETROS_FORRAJEROS_BASE['FESTUCA'])

# =============================================================================
# FUNCIONES BÁSICAS
# =============================================================================

def calcular_superficie(gdf):
    """Calcula superficie en hectáreas"""
    try:
        if gdf.crs and gdf.crs.is_geographic:
            gdf_proj = gdf.to_crs('EPSG:3857')
            area_m2 = gdf_proj.geometry.area
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000
    except:
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
# CÁLCULOS FORRAJEROS
# =============================================================================

def clasificar_vegetacion_sentinel(ndvi, evi, savi, bsi):
    """Clasifica vegetación basada en índices Sentinel-2"""
    if ndvi is None:
        return "DATOS_NO_DISPONIBLES"
    
    if ndvi < 0.2:
        return "SUELO_DESNUDO"
    elif ndvi < 0.4:
        return "VEGETACION_ESCASA"
    elif ndvi < 0.6:
        return "VEGETACION_MODERADA"
    else:
        return "VEGETACION_DENSA"

def calcular_biomasa_sentinel(ndvi, tipo_pastura):
    """Calcula biomasa basada en NDVI real de Sentinel-2"""
    if ndvi is None:
        return 0
        
    params = obtener_parametros_forrajeros(tipo_pastura)
    
    if ndvi < params['UMBRAL_NDVI_SUELO']:
        return 0
    
    biomasa_base = params['FACTOR_BIOMASA_NDVI'] * ndvi
    
    if ndvi < params['UMBRAL_NDVI_PASTURA']:
        factor_ajuste = (ndvi - params['UMBRAL_NDVI_SUELO']) / (params['UMBRAL_NDVI_PASTURA'] - params['UMBRAL_NDVI_SUELO'])
        biomasa_ajustada = biomasa_base * factor_ajuste * 0.7
    else:
        factor_ajuste = min(1.0, (ndvi - params['UMBRAL_NDVI_PASTURA']) / (0.8 - params['UMBRAL_NDVI_PASTURA']))
        biomasa_ajustada = biomasa_base * (0.7 + 0.3 * factor_ajuste)
    
    return max(0, min(params['MS_POR_HA_OPTIMO'], biomasa_ajustada))

def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal):
    """Calcula métricas ganaderas"""
    params = obtener_parametros_forrajeros(tipo_pastura)
    metricas = []
    
    for idx, row in gdf_analizado.iterrows():
        biomasa_disponible = row['biomasa_disponible_kg_ms_ha']
        area_ha = row['area_ha']
        
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        biomasa_total = biomasa_disponible * area_ha
        
        if biomasa_total > 0 and consumo_individual_kg > 0:
            ev_soportable = (biomasa_total * params['TASA_UTILIZACION_RECOMENDADA']) / (consumo_individual_kg * 100)
            ev_soportable = max(0.1, ev_soportable)
        else:
            ev_soportable = 0.1
        
        if carga_animal > 0 and consumo_individual_kg > 0:
            consumo_total_diario = carga_animal * consumo_individual_kg
            if consumo_total_diario > 0:
                dias_permanencia = biomasa_total / consumo_total_diario
                dias_permanencia = max(0.1, min(30, dias_permanencia))
            else:
                dias_permanencia = 0.1
        else:
            dias_permanencia = 0.1
        
        ev_ha = ev_soportable / area_ha if area_ha > 0 else 0
        
        metricas.append({
            'ev_soportable': round(ev_soportable, 2),
            'dias_permanencia': round(dias_permanencia, 1),
            'biomasa_total_kg': round(biomasa_total, 1),
            'consumo_individual_kg': round(consumo_individual_kg, 1),
            'ev_ha': round(ev_ha, 3)
        })
    
    return metricas

# =============================================================================
# VISUALIZACIÓN CON SENTINEL-2
# =============================================================================

class SentinelMapVisualizer:
    """Visualizador con datos reales de Sentinel-2"""
    
    def __init__(self):
        self.sentinel_processor = Sentinel2Processor()
    
    def create_sentinel_map(self, gdf, target_date, cloud_filter=20, index_type='NDVI'):
        """Crea mapa con datos Sentinel-2 reales"""
        try:
            if not ee_initialized:
                return self.create_base_map(gdf)
            
            # Convertir a geometría Earth Engine
            geojson_dict = json.loads(gdf.to_json())
            geometry = ee.Geometry(geojson_dict['features'][0]['geometry'])
            
            # Obtener mejor imagen
            with st.spinner("🛰️ Descargando imagen Sentinel-2..."):
                image = self.sentinel_processor.get_best_image(geometry, target_date, cloud_filter)
            
            if image is None:
                st.warning("No se pudo obtener imagen Sentinel-2")
                return self.create_base_map(gdf)
            
            # Configuración de visualización
            vis_params = {
                'NDVI': {'min': -1, 'max': 1, 'palette': ['red', 'yellow', 'green']},
                'EVI': {'min': -1, 'max': 1, 'palette': ['red', 'yellow', 'green']},
                'SAVI': {'min': -1, 'max': 1, 'palette': ['red', 'yellow', 'green']},
                'BSI': {'min': -1, 'max': 1, 'palette': ['blue', 'white', 'brown']}
            }.get(index_type, {'min': -1, 'max': 1, 'palette': ['red', 'yellow', 'green']})
            
            # Crear mapa con geemap
            Map = geemap.Map(
                center=[gdf.geometry.centroid.iloc[0].y, gdf.geometry.centroid.iloc[0].x], 
                zoom=13
            )
            
            # Añadir capas
            Map.add_basemap('SATELLITE')
            Map.addLayer(image.select(index_type), vis_params, f'Sentinel-2 {index_type}')
            Map.add_gdf(gdf, layer_name="Sub-Lotes", style={'color': 'red', 'weight': 3, 'fillOpacity': 0})
            Map.add_layer_control()
            
            return Map
            
        except Exception as e:
            st.error(f"Error creando mapa Sentinel: {e}")
            return self.create_base_map(gdf)
    
    def create_base_map(self, gdf, map_type="google_satellite"):
        """Crea mapa base"""
        try:
            centroid = gdf.geometry.centroid.iloc[0]
            bounds = gdf.total_bounds
            
            m = folium.Map(
                location=[centroid.y, centroid.x],
                zoom_start=13,
                control_scale=True
            )
            
            if map_type == "google_satellite":
                folium.TileLayer(
                    tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                    attr='Google Satellite',
                    name='Google Satellite',
                    overlay=False
                ).add_to(m)
            
            folium.TileLayer(
                tiles='OpenStreetMap',
                name='OpenStreetMap',
                overlay=False
            ).add_to(m)
            
            self._add_polygons_to_map(m, gdf)
            m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
            folium.LayerControl().add_to(m)
            
            return m
            
        except Exception as e:
            st.error(f"Error creando mapa base: {e}")
            return None
    
    def _add_polygons_to_map(self, m, gdf):
        """Añade polígonos al mapa"""
        try:
            for idx, row in gdf.iterrows():
                if 'ndvi' in gdf.columns and pd.notna(row['ndvi']):
                    ndvi = row['ndvi']
                    if ndvi < 0.2:
                        color = '#d73027'
                    elif ndvi < 0.4:
                        color = '#fdae61'
                    elif ndvi < 0.6:
                        color = '#a6d96a'
                    else:
                        color = '#1a9850'
                else:
                    color = '#3388ff'
                
                tooltip_text = f"Sub-lote: {row.get('id_subLote', idx+1)}"
                if 'area_ha' in gdf.columns:
                    tooltip_text += f"<br>Área: {row['area_ha']:.2f} ha"
                if 'ndvi' in gdf.columns and pd.notna(row['ndvi']):
                    tooltip_text += f"<br>NDVI: {row['ndvi']:.3f}"
                
                folium.GeoJson(
                    row.geometry.__geo_interface__,
                    style_function=lambda x, color=color: {
                        'fillColor': color,
                        'color': '#000000',
                        'weight': 2,
                        'fillOpacity': 0.6
                    },
                    tooltip=folium.Tooltip(tooltip_text)
                ).add_to(m)
                
        except Exception as e:
            st.error(f"Error añadiendo polígonos: {e}")
    
    def create_ndvi_map(self, gdf_analizado, tipo_pastura):
        """Crea mapa temático de NDVI"""
        try:
            fig, ax = plt.subplots(1, 1, figsize=(15, 10))
            cmap = LinearSegmentedColormap.from_list('ndvi_cmap', ['#d73027', '#fee08b', '#a6d96a', '#1a9850'])
            
            for idx, row in gdf_analizado.iterrows():
                ndvi = row['ndvi']
                if pd.isna(ndvi):
                    color = 'lightgray'
                else:
                    color = cmap(ndvi)
                
                gdf_analizado.iloc[[idx]].plot(
                    ax=ax,
                    color=color,
                    edgecolor='black',
                    linewidth=1
                )
                
                centroid = row.geometry.centroid
                label_text = f"S{row['id_subLote']}"
                if not pd.isna(ndvi):
                    label_text += f"\n{ndvi:.2f}"
                
                ax.annotate(
                    label_text,
                    (centroid.x, centroid.y),
                    xytext=(5, 5),
                    textcoords="offset points",
                    fontsize=8,
                    color='black',
                    weight='bold',
                    bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8)
                )
            
            ax.set_title(f'🌿 MAPA DE NDVI - {tipo_pastura} (Sentinel-2)', fontsize=16, fontweight='bold', pad=20)
            ax.set_xlabel('Longitud')
            ax.set_ylabel('Latitud')
            ax.grid(True, alpha=0.3)
            
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=0, vmax=1))
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
            cbar.set_label('NDVI', fontsize=12, fontweight='bold')
            
            plt.tight_layout()
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            buf.seek(0)
            plt.close()
            
            return buf
            
        except Exception as e:
            st.error(f"Error creando mapa NDVI: {e}")
            return None

# =============================================================================
# ANÁLISIS CON SENTINEL-2 REAL
# =============================================================================

def analisis_forrajero_sentinel(gdf, config):
    """Función principal de análisis con Sentinel-2 real"""
    try:
        st.header("🌱 ANÁLISIS FORRAJERO - SENTINEL-2 REAL")
        
        # Verificar Earth Engine
        if not ee_initialized:
            st.error("""
            ❌ Earth Engine no configurado
            
            **Para usar Sentinel-2 real:**
            1. Ejecuta: `earthengine authenticate`
            2. Sigue las instrucciones en el navegador
            3. Reinicia la aplicación
            """)
            return False
        
        area_total = calcular_superficie(gdf).sum()
        st.success(f"✅ Potrero cargado: {area_total:.1f} ha, {len(gdf)} polígonos")
        
        # PASO 1: Mostrar mapa Sentinel-2
        st.subheader("🛰️ MAPA SENTINEL-2 - NDVI")
        visualizador = SentinelMapVisualizer()
        
        with st.spinner("Cargando imagen Sentinel-2..."):
            mapa_sentinel = visualizador.create_sentinel_map(
                gdf, 
                config['fecha_imagen'], 
                config['nubes_max'],
                'NDVI'
            )
        
        if isinstance(mapa_sentinel, geemap.Map):
            mapa_sentinel.to_streamlit(height=500)
        else:
            folium_static(mapa_sentinel, width=1000, height=500)
        
        # PASO 2: Dividir potrero
        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES")
        with st.spinner("Dividiendo potrero..."):
            gdf_dividido = dividir_potrero_en_subLotes(gdf, config['n_divisiones'])
        
        if gdf_dividido is None or len(gdf_dividido) == 0:
            st.error("❌ Error: No se pudieron crear sub-lotes")
            return False
            
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # PASO 3: Obtener datos Sentinel-2 para cada sub-lote
        st.subheader("📊 PROCESANDO DATOS SENTINEL-2")
        
        processor = Sentinel2Processor()
        resultados = []
        
        # Convertir geometría principal a EE
        geojson_dict = json.loads(gdf.to_json())
        geometry_principal = ee.Geometry(geojson_dict['features'][0]['geometry'])
        
        # Obtener imagen una sola vez para toda el área
        with st.spinner("Obteniendo datos Sentinel-2 para toda el área..."):
            imagen_completa = processor.get_best_image(
                geometry_principal, 
                config['fecha_imagen'], 
                config['nubes_max']
            )
        
        if imagen_completa is None:
            st.error("❌ No se pudo obtener imagen Sentinel-2 para el área")
            return False
        
        # Procesar cada sub-lote
        progress_bar = st.progress(0)
        for idx, row in gdf_dividido.iterrows():
            progress = (idx + 1) / len(gdf_dividido)
            progress_bar.progress(progress)
            
            # Convertir sub-geometría a EE
            sub_geojson = json.loads(gpd.GeoSeries([row.geometry]).to_json())
            sub_geometry = ee.Geometry(sub_geojson['features'][0]['geometry'])
            
            # Extraer valores para el sub-lote
            valores = processor.extract_values_for_geometry(imagen_completa, sub_geometry)
            
            if valores:
                ndvi = valores.get('NDVI')
                evi = valores.get('EVI')
                savi = valores.get('SAVI')
                bsi = valores.get('BSI')
            else:
                ndvi = evi = savi = bsi = None
            
            # Calcular métricas
            biomasa_total = calcular_biomasa_sentinel(ndvi, config['tipo_pastura'])
            biomasa_disponible = biomasa_total * 0.6  # 60% de aprovechamiento
            tipo_vegetacion = clasificar_vegetacion_sentinel(ndvi, evi, savi, bsi)
            
            # Calcular área
            area_ha = calcular_superficie(gpd.GeoDataFrame([row], crs=gdf_dividido.crs))
            if hasattr(area_ha, 'iloc'):
                area_ha = area_ha.iloc[0]
            elif hasattr(area_ha, '__getitem__'):
                area_ha = area_ha[0]
            
            resultados.append({
                'id_subLote': row['id_subLote'],
                'area_ha': area_ha,
                'ndvi': ndvi,
                'evi': evi,
                'savi': savi,
                'bsi': bsi,
                'tipo_superficie': tipo_vegetacion,
                'biomasa_total_kg_ms_ha': biomasa_total,
                'biomasa_disponible_kg_ms_ha': biomasa_disponible,
                'crecimiento_diario': obtener_parametros_forrajeros(config['tipo_pastura'])['CRECIMIENTO_DIARIO'],
                'fuente_datos': 'SENTINEL-2'
            })
        
        progress_bar.empty()
        
        # Crear GeoDataFrame con resultados
        gdf_analizado = gdf_dividido.copy()
        for col in ['area_ha', 'ndvi', 'evi', 'savi', 'bsi', 'tipo_superficie', 
                   'biomasa_total_kg_ms_ha', 'biomasa_disponible_kg_ms_ha', 'crecimiento_diario', 'fuente_datos']:
            gdf_analizado[col] = [r[col] for r in resultados]
        
        # PASO 4: Calcular métricas ganaderas
        st.subheader("🐄 CALCULANDO MÉTRICAS GANADERAS")
        with st.spinner("Calculando equivalentes vaca..."):
            metricas = calcular_metricas_ganaderas(
                gdf_analizado, 
                config['tipo_pastura'], 
                config['peso_promedio'], 
                config['carga_animal']
            )
        
        for col in ['ev_soportable', 'dias_permanencia', 'biomasa_total_kg', 'consumo_individual_kg', 'ev_ha']:
            gdf_analizado[col] = [m[col] for m in metricas]
        
        # PASO 5: Mostrar resultados
        mostrar_resultados_sentinel(gdf_analizado, config)
        
        st.session_state.analisis_completado = True
        return True
        
    except Exception as e:
        st.error(f"❌ Error en análisis: {str(e)}")
        import traceback
        st.error(f"Detalle: {traceback.format_exc()}")
        return False

def mostrar_resultados_sentinel(gdf_analizado, config):
    """Muestra resultados con datos Sentinel-2"""
    st.header("📊 RESULTADOS - SENTINEL-2 REAL")
    
    # Información de la imagen
    st.subheader("🛰️ INFORMACIÓN DE LA IMAGEN")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # Contar sub-lotes con datos válidos
        ndvi_validos = gdf_analizado['ndvi'].notna().sum()
        total_sub_lotes = len(gdf_analizado)
        st.metric("Sub-lotes con datos", f"{ndvi_validos}/{total_sub_lotes}")
    
    with col2:
        ndvi_prom = gdf_analizado['ndvi'].mean()
        st.metric("NDVI Promedio", f"{ndvi_prom:.3f}" if not pd.isna(ndvi_prom) else "N/A")
    
    with col3:
        biomasa_prom = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
        st.metric("Biomasa Disponible", f"{biomasa_prom:.0f} kg MS/ha")
    
    with col4:
        area_total = gdf_analizado['area_ha'].sum()
        st.metric("Área Total", f"{area_total:.1f} ha")
    
    # Mapa de NDVI
    st.subheader("🟢 MAPA DE NDVI - SENTINEL-2")
    visualizador = SentinelMapVisualizer()
    mapa_ndvi = visualizador.create_ndvi_map(gdf_analizado, config['tipo_pastura'])
    if mapa_ndvi:
        st.image(mapa_ndvi, use_container_width=True)
        
        st.download_button(
            "📥 Descargar Mapa NDVI",
            mapa_ndvi.getvalue(),
            f"mapa_ndvi_sentinel2_{config['tipo_pastura']}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
            "image/png"
        )
    
    # Tabla de resultados
    st.subheader("📋 DETALLES POR SUB-LOTE")
    
    columnas_detalle = [
        'id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 
        'biomasa_disponible_kg_ms_ha', 'ev_soportable', 'dias_permanencia', 'fuente_datos'
    ]
    
    columnas_existentes = [col for col in columnas_detalle if col in gdf_analizado.columns]
    tabla_detalle = gdf_analizado[columnas_existentes].copy()
    
    nombres_amigables = {
        'id_subLote': 'Sub-Lote',
        'area_ha': 'Área (ha)',
        'tipo_superficie': 'Tipo Superficie',
        'ndvi': 'NDVI',
        'biomasa_disponible_kg_ms_ha': 'Biomasa Disp (kg MS/ha)',
        'ev_soportable': 'EV',
        'dias_permanencia': 'Días Permanencia',
        'fuente_datos': 'Fuente'
    }
    
    tabla_detalle.columns = [nombres_amigables.get(col, col) for col in columnas_existentes]
    
    st.dataframe(tabla_detalle, use_container_width=True)
    
    # Estadísticas
    with st.expander("📊 ESTADÍSTICAS DETALLADAS"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Distribución de vegetación:**")
            distribucion = gdf_analizado['tipo_superficie'].value_counts()
            for tipo, count in distribucion.items():
                porcentaje = (count / len(gdf_analizado)) * 100
                st.write(f"- {tipo}: {count} sub-lotes ({porcentaje:.1f}%)")
        
        with col2:
            st.write("**Rangos de NDVI:**")
            ndvi_vals = gdf_analizado['ndvi'].dropna()
            if len(ndvi_vals) > 0:
                st.write(f"- Mínimo: {ndvi_vals.min():.3f}")
                st.write(f"- Máximo: {ndvi_vals.max():.3f}")
                st.write(f"- Promedio: {ndvi_vals.mean():.3f}")
            else:
                st.write("- No hay datos NDVI disponibles")
    
    # Descarga de resultados
    st.subheader("💾 EXPORTAR RESULTADOS")
    
    csv = tabla_detalle.to_csv(index=False)
    st.download_button(
        "📥 Descargar CSV",
        csv,
        f"resultados_sentinel2_{config['tipo_pastura']}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        "text/csv"
    )

# =============================================================================
# SIDEBAR
# =============================================================================

with st.sidebar:
    st.header("⚙️ Configuración Sentinel-2")
    
    # Estado de Earth Engine
    if EE_AVAILABLE:
        if ee_initialized:
            st.success("✅ Earth Engine: CONECTADO")
            st.success("🛰️ Sentinel-2: DISPONIBLE")
        else:
            st.error("❌ Earth Engine: NO CONECTADO")
            show_authentication_instructions()
    else:
        st.error("❌ Earth Engine: NO INSTALADO")
    
    st.subheader("🛰️ Parámetros Sentinel-2")
    fuente_satelital = st.selectbox(
        "Fuente de datos:",
        ["SENTINEL-2", "SIMULADO"],
        disabled=not ee_initialized
    )
    
    fecha_imagen = st.date_input(
        "Fecha de imagen:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now()
    )
    
    nubes_max = st.slider("Máximo % de nubes:", 0, 100, 20)
    
    st.subheader("🌿 Tipo de Pastura")
    tipo_pastura = st.selectbox(
        "Seleccionar tipo:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL"]
    )
    
    st.subheader("🐄 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal:", 50, 1000, 100)
    
    st.subheader("📐 División del Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", 8, 32, 16)
    
    st.subheader("📤 Cargar Datos")
    uploaded_zip = st.file_uploader(
        "Subir ZIP con shapefile:",
        type=['zip']
    )

# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================

def main():
    """Función principal"""
    
    # Procesar archivo subido
    if uploaded_zip is not None and st.session_state.gdf_cargado is None:
        with st.spinner("Cargando shapefile..."):
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                        zip_ref.extractall(tmp_dir)
                    
                    shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
                    if shp_files:
                        shp_path = os.path.join(tmp_dir, shp_files[0])
                        gdf_cargado = gpd.read_file(shp_path)
                        
                        if gdf_cargado.crs is None:
                            gdf_cargado = gdf_cargado.set_crs('EPSG:4326')
                            st.warning("⚠️ CRS no definido. Asumiendo WGS84")
                        
                        st.session_state.gdf_cargado = gdf_cargado
                        st.success("✅ Shapefile cargado correctamente")
                    else:
                        st.error("❌ No se encontró archivo .shp")
            except Exception as e:
                st.error(f"❌ Error cargando shapefile: {str(e)}")
    
    # Contenido principal
    if st.session_state.gdf_cargado is not None:
        gdf = st.session_state.gdf_cargado
        area_total = calcular_superficie(gdf).sum()
        
        st.header("📁 DATOS CARGADOS")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Polígonos", len(gdf))
        with col2:
            st.metric("Área Total", f"{area_total:.1f} ha")
        with col3:
            st.metric("Pastura", tipo_pastura)
        with col4:
            st.metric("Fuente", fuente_satelital)
        
        # Botón de análisis
        st.markdown("---")
        st.header("🚀 ANÁLISIS FORRAJERO")
        
        if st.button("🎯 EJECUTAR ANÁLISIS CON SENTINEL-2", type="primary", use_container_width=True):
            config = {
                'fecha_imagen': fecha_imagen,
                'nubes_max': nubes_max,
                'tipo_pastura': tipo_pastura,
                'peso_promedio': peso_promedio,
                'carga_animal': carga_animal,
                'n_divisiones': n_divisiones
            }
            
            if fuente_satelital == "SENTINEL-2" and ee_initialized:
                with st.spinner("Analizando con Sentinel-2 real..."):
                    resultado = analisis_forrajero_sentinel(gdf, config)
            else:
                st.warning("⚠️ Usando datos simulados (Earth Engine no disponible)")
                # Aquí iría la función de análisis simulado si la quisieras mantener
            
            if resultado:
                st.balloons()
                st.success("🎉 ¡Análisis completado con Sentinel-2!")
    
    else:
        # Pantalla de bienvenida
        st.header("🌱 ANALIZADOR FORRAJERO - SENTINEL-2")
        
        st.markdown("""
        ### 🛰️ CARACTERÍSTICAS:
        
        ✅ **Datos reales** de Sentinel-2 Harmonized (10m)  
        ✅ **Índices de vegetación** en tiempo real  
        ✅ **Mapas interactivos** con Google Satellite  
        ✅ **Análisis forrajero** preciso  
        ✅ **Equivalentes vaca** y días de permanencia  
        
        ### 📋 REQUISITOS:
        
        1. **Cuenta de Google Earth Engine** aprobada
        2. **Autenticación** con `earthengine authenticate`
        3. **Shapefile** del potrero en formato ZIP
        
        ### 🚀 INSTRUCCIONES:
        
        1. Configura Earth Engine (ver sidebar ←)
        2. Sube tu shapefile
        3. Configura los parámetros
        4. Ejecuta el análisis con Sentinel-2 real
        """)
        
        if not ee_initialized:
            st.error("""
            **❌ EARTH ENGINE NO CONFIGURADO**
            
            Para usar Sentinel-2 real necesitas:
            
            1. **Ejecutar en terminal:**
            ```bash
            earthengine authenticate
            ```
            
            2. **Seguir las instrucciones en el navegador**
            
            3. **Reiniciar esta aplicación**
            """)

if __name__ == "__main__":
    main()
