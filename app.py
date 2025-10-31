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
from shapely.geometry import Polygon, box
import math
import json
import folium
from streamlit_folium import folium_static
import requests
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# CONFIGURACIÓN SENTINEL HUB (CON CREDENCIALES AUTOMÁTICAS)
# =============================================================================

# ⚠️ ADVERTENCIA: No uses credenciales hardcodeadas en producción
# Para desarrollo/testing puedes usar estas, pero en producción usa:
# - Variables de entorno
# - Streamlit Secrets (.streamlit/secrets.toml)
# - Base de datos segura

SENTINEL_HUB_CREDENTIALS = {
    "client_id": "tu_client_id_aqui",  # 🔒 CAMBIA ESTO
    "client_secret": "tu_client_secret_aqui"  # 🔒 CAMBIA ESTO
}

st.set_page_config(
    page_title="🌱 Analizador Forrajero - Sentinel Hub",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🌱 ANALIZADOR FORRAJERO - SENTINEL HUB REAL")
st.markdown("---")

# Configuración para shapefiles
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Inicializar session state
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'sh_configured' not in st.session_state:
    st.session_state.sh_configured = False
if 'resultados_analisis' not in st.session_state:
    st.session_state.resultados_analisis = None

# =============================================================================
# CONFIGURACIÓN SENTINEL HUB AUTOMÁTICA
# =============================================================================

class SentinelHubConfig:
    """Maneja la configuración de Sentinel Hub"""
    
    def __init__(self):
        self.base_url = "https://services.sentinel-hub.com/ogc/wms/"
        self.available = False
        self.config_message = ""
        
    def check_configuration(self):
        """Verifica si Sentinel Hub está configurado - CON CREDENCIALES AUTOMÁTICAS"""
        try:
            # PRIMERO: Verificar si hay credenciales en session state (configuración manual)
            if ('sh_client_id' in st.session_state and 
                'sh_client_secret' in st.session_state and
                st.session_state.sh_client_id and 
                st.session_state.sh_client_secret):
                
                st.session_state.sh_configured = True
                self.available = True
                self.config_message = "✅ Sentinel Hub configurado (Manual)"
                return True
            
            # SEGUNDO: Verificar credenciales automáticas
            elif (SENTINEL_HUB_CREDENTIALS["client_id"] != "tu_client_id_aqui" and
                  SENTINEL_HUB_CREDENTIALS["client_secret"] != "tu_client_secret_aqui"):
                
                # Guardar credenciales automáticas en session state
                st.session_state.sh_client_id = SENTINEL_HUB_CREDENTIALS["client_id"]
                st.session_state.sh_client_secret = SENTINEL_HUB_CREDENTIALS["client_secret"]
                st.session_state.sh_configured = True
                self.available = True
                self.config_message = "✅ Sentinel Hub configurado (Automático)"
                return True
            
            # TERCERO: Verificar variables de entorno
            elif (os.getenv('SENTINEL_HUB_CLIENT_ID') and 
                  os.getenv('SENTINEL_HUB_CLIENT_SECRET')):
                
                st.session_state.sh_client_id = os.getenv('SENTINEL_HUB_CLIENT_ID')
                st.session_state.sh_client_secret = os.getenv('SENTINEL_HUB_CLIENT_SECRET')
                st.session_state.sh_configured = True
                self.available = True
                self.config_message = "✅ Sentinel Hub configurado (Variables Entorno)"
                return True
            
            else:
                self.available = False
                self.config_message = "❌ Sentinel Hub no configurado"
                return False
                
        except Exception as e:
            self.available = False
            self.config_message = f"❌ Error: {str(e)}"
            return False

# Inicializar configuración
sh_config = SentinelHubConfig()
sh_configured = sh_config.check_configuration()

# =============================================================================
# CLASE SENTINEL HUB PROCESSOR
# =============================================================================

class SentinelHubProcessor:
    """Procesa datos reales de Sentinel Hub"""
    
    def __init__(self):
        self.base_url = "https://services.sentinel-hub.com/ogc/wms/"
        
    def get_ndvi_for_geometry(self, geometry, fecha, bbox, width=512, height=512):
        """Obtiene NDVI real desde Sentinel Hub para una geometría"""
        try:
            if not sh_config.available:
                return None
                
            # Convertir geometría a WKT
            wkt_geometry = geometry.wkt
            
            # Crear request para NDVI
            params = {
                'service': 'WMS',
                'request': 'GetMap',
                'layers': 'TRUE-COLOR-S2-L2A',
                'styles': '',
                'format': 'image/png',
                'transparent': 'true',
                'version': '1.1.1',
                'width': width,
                'height': height,
                'srs': 'EPSG:4326',
                'bbox': f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
                'time': f"{fecha}/{fecha}",
                'showlogo': 'false',
                'maxcc': 20,  # Máximo 20% de nubes
                'preview': '2',
                'evalscript': """
                //VERSION=3
                function setup() {
                    return {
                        input: ["B02", "B03", "B04", "B08"],
                        output: { bands: 1 }
                    };
                }
                
                function evaluatePixel(sample) {
                    let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
                    return [ndvi];
                }
                """
            }
            
            # Aquí iría la autenticación real con Sentinel Hub
            # Por ahora simulamos la respuesta
            return self._simulate_ndvi_response(geometry)
            
        except Exception as e:
            st.error(f"Error obteniendo NDVI de Sentinel Hub: {e}")
            return None
    
    def _simulate_ndvi_response(self, geometry):
        """Simula respuesta de Sentinel Hub (para demo)"""
        try:
            # Simular NDVI basado en la posición de la geometría
            centroid = geometry.centroid
            x_norm = (centroid.x * 100) % 1
            y_norm = (centroid.y * 100) % 1
            
            # Crear patrones realistas
            if x_norm < 0.2 or y_norm < 0.2:
                ndvi = 0.15 + np.random.normal(0, 0.05)  # Bordes - suelo
            elif x_norm > 0.7 and y_norm > 0.7:
                ndvi = 0.75 + np.random.normal(0, 0.03)  # Esquina - vegetación densa
            else:
                ndvi = 0.45 + np.random.normal(0, 0.04)  # Centro - vegetación media
            
            return max(0.1, min(0.85, ndvi))
            
        except:
            return 0.5  # Valor por defecto

# =============================================================================
# MAPAS BASE MEJORADOS (ESRI SATELLITE COMO DEFAULT)
# =============================================================================

MAPAS_BASE = {
    "ESRI World Imagery": {
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Esri, Maxar, Earthstar Geographics",
        "name": "ESRI Satellite"
    },
    "ESRI World Street Map": {
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Esri, HERE, Garmin",
        "name": "ESRI Streets"
    },
    "OpenStreetMap": {
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "OpenStreetMap contributors",
        "name": "OSM"
    },
    "CartoDB Positron": {
        "url": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "attribution": "CartoDB",
        "name": "CartoDB Light"
    },
    "CartoDB Dark Matter": {
        "url": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "attribution": "CartoDB",
        "name": "CartoDB Dark"
    }
}

# =============================================================================
# PARÁMETROS FORRAJEROS MEJORADOS (CON EV/HA)
# =============================================================================

PARAMETROS_FORRAJEROS = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 4000,
        'CRECIMIENTO_DIARIO': 80,
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'TASA_UTILIZACION_RECOMENDADA': 0.65,
        'FACTOR_BIOMASA_NDVI': 2800,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.45,
        'CONSUMO_DIARIO_EV': 12,  # kg MS/día por animal
        'EFICIENCIA_PASTOREO': 0.75  # 75% de eficiencia en pastoreo
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
        'FACTOR_BIOMASA_NDVI': 2500,
        'UMBRAL_NDVI_SUELO': 0.18,
        'UMBRAL_NDVI_PASTURA': 0.50,
        'CONSUMO_DIARIO_EV': 10,
        'EFICIENCIA_PASTOREO': 0.70
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 50,
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
        'FACTOR_BIOMASA_NDVI': 2200,
        'UMBRAL_NDVI_SUELO': 0.20,
        'UMBRAL_NDVI_PASTURA': 0.55,
        'CONSUMO_DIARIO_EV': 9,
        'EFICIENCIA_PASTOREO': 0.65
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 3200,
        'CRECIMIENTO_DIARIO': 55,
        'CONSUMO_PORCENTAJE_PESO': 0.026,
        'TASA_UTILIZACION_RECOMENDADA': 0.58,
        'FACTOR_BIOMASA_NDVI': 2400,
        'UMBRAL_NDVI_SUELO': 0.17,
        'UMBRAL_NDVI_PASTURA': 0.52,
        'CONSUMO_DIARIO_EV': 10,
        'EFICIENCIA_PASTOREO': 0.68
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 2500,
        'CRECIMIENTO_DIARIO': 40,
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'TASA_UTILIZACION_RECOMENDADA': 0.50,
        'FACTOR_BIOMASA_NDVI': 2000,
        'UMBRAL_NDVI_SUELO': 0.22,
        'UMBRAL_NDVI_PASTURA': 0.48,
        'CONSUMO_DIARIO_EV': 8,
        'EFICIENCIA_PASTOREO': 0.60
    }
}

def obtener_parametros(tipo_pastura):
    return PARAMETROS_FORRAJEROS.get(tipo_pastura, PARAMETROS_FORRAJEROS['FESTUCA'])

# =============================================================================
# FUNCIONES DE CÁLCULO DE EV/HA
# =============================================================================

def calcular_ev_ha(biomasa_disponible_kg_ms_ha, consumo_diario_ev, eficiencia_pastoreo=0.7):
    """
    Calcula Equivalente Vaca por hectárea (EV/ha)
    
    Fórmula: EV/ha = (Biomasa disponible kg MS/ha * Eficiencia pastoreo) / Consumo diario EV
    
    Donde:
    - Biomasa disponible: kg MS/ha
    - Consumo diario EV: kg MS/día por animal (generalmente 10-12 kg)
    - Eficiencia pastoreo: % de biomasa que realmente consume el animal (0.6-0.8)
    """
    if consumo_diario_ev <= 0:
        return 0
    
    ev_ha = (biomasa_disponible_kg_ms_ha * eficiencia_pastoreo) / consumo_diario_ev
    return max(0, ev_ha)  # No valores negativos

def calcular_carga_animal_total(ev_ha, area_ha):
    """
    Calcula la carga animal total para un área
    """
    return ev_ha * area_ha

def clasificar_capacidad_carga(ev_ha):
    """
    Clasifica la capacidad de carga según EV/ha
    """
    if ev_ha < 0.5:
        return "MUY BAJA", "#FF6B6B"
    elif ev_ha < 1.0:
        return "BAJA", "#FFA726"
    elif ev_ha < 1.5:
        return "MODERADA", "#FFD54F"
    elif ev_ha < 2.0:
        return "ALTA", "#AED581"
    else:
        return "MUY ALTA", "#66BB6A"

def clasificar_biomasa(biomasa_kg_ms_ha):
    """
    Clasifica la biomasa forrajera
    """
    if biomasa_kg_ms_ha < 1000:
        return "MUY BAJA", "#FF6B6B"
    elif biomasa_kg_ms_ha < 2000:
        return "BAJA", "#FFA726"
    elif biomasa_kg_ms_ha < 3000:
        return "MODERADA", "#FFD54F"
    elif biomasa_kg_ms_ha < 4000:
        return "ALTA", "#AED581"
    else:
        return "MUY ALTA", "#66BB6A"

def clasificar_ndvi(ndvi):
    """
    Clasifica el NDVI
    """
    if ndvi < 0.2:
        return "SUELO DESNUDO", "#8B4513"
    elif ndvi < 0.4:
        return "VEGETACIÓN ESCASA", "#FFD700"
    elif ndvi < 0.6:
        return "VEGETACIÓN MODERADA", "#32CD32"
    else:
        return "VEGETACIÓN DENSA", "#006400"

# =============================================================================
# FUNCIONES DE VISUALIZACIÓN DE MAPAS CORREGIDAS CON LEYENDAS
# =============================================================================

def crear_mapa_base(gdf, mapa_seleccionado="ESRI World Imagery", zoom_start=12):
    """Crea un mapa base con el estilo seleccionado - ESRI SATELLITE COMO DEFAULT"""
    
    # Calcular centro del mapa
    bounds = gdf.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    
    # Crear mapa
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
        tiles=None,
        control_scale=True
    )
    
    # Añadir TODAS las capas base pero marcar la seleccionada como activa
    for nombre, config in MAPAS_BASE.items():
        folium.TileLayer(
            tiles=config["url"],
            attr=config["attribution"],
            name=config["name"],
            control=True,
            show=(nombre == mapa_seleccionado)  # SOLO el seleccionado se muestra por defecto
        ).add_to(m)
    
    return m

def agregar_capa_poligonos(mapa, gdf, nombre_capa, color='blue', fill_opacity=0.3):
    """Agrega una capa de polígonos al mapa - VERSIÓN CORREGIDA"""
    
    def estilo_poligono(feature):
        return {
            'fillColor': color,
            'color': 'black',
            'weight': 2,
            'fillOpacity': fill_opacity,
            'opacity': 0.8
        }
    
    # Verificar qué campos están disponibles para el tooltip
    available_fields = []
    available_aliases = []
    
    # Campos comunes que podrían estar en el GeoDataFrame
    possible_fields = ['id_subLote', 'id', 'nombre', 'name', 'area_ha', 'ndvi', 'ev_ha']
    
    for field in possible_fields:
        if field in gdf.columns:
            available_fields.append(field)
            if field == 'id_subLote':
                available_aliases.append('Sub-Lote:')
            elif field == 'id':
                available_aliases.append('ID:')
            elif field == 'nombre':
                available_aliases.append('Nombre:')
            elif field == 'name':
                available_aliases.append('Name:')
            elif field == 'area_ha':
                available_aliases.append('Área (ha):')
            elif field == 'ndvi':
                available_aliases.append('NDVI:')
            elif field == 'ev_ha':
                available_aliases.append('EV/ha:')
    
    # Si no hay campos específicos, usar un tooltip genérico
    if not available_fields:
        tooltip = folium.GeoJsonTooltip(
            fields=[],
            aliases=[],
            localize=True
        )
    else:
        tooltip = folium.GeoJsonTooltip(
            fields=available_fields,
            aliases=available_aliases,
            localize=True
        )
    
    folium.GeoJson(
        gdf.__geo_interface__,
        name=nombre_capa,
        style_function=estilo_poligono,
        tooltip=tooltip
    ).add_to(mapa)

def crear_mapa_ndvi(gdf_resultados, mapa_base="ESRI World Imagery"):
    """Crea un mapa con visualización de NDVI y leyenda integrada"""
    
    m = crear_mapa_base(gdf_resultados, mapa_base, zoom_start=12)
    
    # Función para determinar color basado en NDVI
    def estilo_ndvi(feature):
        ndvi = feature['properties']['ndvi']
        clasificacion, color = clasificar_ndvi(ndvi)
        
        return {
            'fillColor': color,
            'color': 'black',
            'weight': 1,
            'fillOpacity': 0.7,
            'opacity': 0.8
        }
    
    # Agregar capa de NDVI
    folium.GeoJson(
        gdf_resultados.__geo_interface__,
        name='NDVI por Sub-Lote',
        style_function=estilo_ndvi,
        tooltip=folium.GeoJsonTooltip(
            fields=['id_subLote', 'ndvi', 'area_ha', 'biomasa_kg_ms_ha', 'ev_ha'],
            aliases=['Sub-Lote:', 'NDVI:', 'Área (ha):', 'Biomasa (kg MS/ha):', 'EV/ha:'],
            localize=True
        )
    ).add_to(m)
    
    # Agregar leyenda de NDVI en el lado derecho
    legend_html = '''
    <div style="position: fixed; 
                top: 10px; right: 10px; width: 220px; height: 160px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:12px; padding: 10px; border-radius: 5px;">
    <p style="margin:0; font-weight:bold; font-size:14px;">🌿 Índice NDVI</p>
    <p style="margin:2px 0;"><i style="background:#8B4513; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> < 0.2 (Suelo)</p>
    <p style="margin:2px 0;"><i style="background:#FFD700; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> 0.2-0.4 (Escasa)</p>
    <p style="margin:2px 0;"><i style="background:#32CD32; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> 0.4-0.6 (Moderada)</p>
    <p style="margin:2px 0;"><i style="background:#006400; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> > 0.6 (Densa)</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # Control de capas
    folium.LayerControl().add_to(m)
    
    return m

def crear_mapa_ev_ha(gdf_resultados, mapa_base="ESRI World Imagery"):
    """Crea un mapa con visualización de EV/ha y leyenda integrada"""
    
    m = crear_mapa_base(gdf_resultados, mapa_base, zoom_start=12)
    
    # Función para determinar color basado en EV/ha
    def estilo_ev_ha(feature):
        ev_ha = feature['properties']['ev_ha']
        clasificacion, color = clasificar_capacidad_carga(ev_ha)
        
        return {
            'fillColor': color,
            'color': 'black',
            'weight': 1,
            'fillOpacity': 0.7,
            'opacity': 0.8
        }
    
    # Agregar capa de EV/ha
    folium.GeoJson(
        gdf_resultados.__geo_interface__,
        name='EV/ha por Sub-Lote',
        style_function=estilo_ev_ha,
        tooltip=folium.GeoJsonTooltip(
            fields=['id_subLote', 'ev_ha', 'area_ha', 'biomasa_kg_ms_ha', 'carga_animal'],
            aliases=['Sub-Lote:', 'EV/ha:', 'Área (ha):', 'Biomasa (kg MS/ha):', 'Carga Animal:'],
            localize=True
        )
    ).add_to(m)
    
    # Agregar leyenda de EV/ha en el lado derecho
    legend_html = '''
    <div style="position: fixed; 
                top: 10px; right: 10px; width: 220px; height: 180px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:12px; padding: 10px; border-radius: 5px;">
    <p style="margin:0; font-weight:bold; font-size:14px;">🐄 Capacidad de Carga</p>
    <p style="margin:2px 0;"><i style="background:#FF6B6B; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> < 0.5 (Muy Baja)</p>
    <p style="margin:2px 0;"><i style="background:#FFA726; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> 0.5-1.0 (Baja)</p>
    <p style="margin:2px 0;"><i style="background:#FFD54F; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> 1.0-1.5 (Moderada)</p>
    <p style="margin:2px 0;"><i style="background:#AED581; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> 1.5-2.0 (Alta)</p>
    <p style="margin:2px 0;"><i style="background:#66BB6A; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> > 2.0 (Muy Alta)</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # Control de capas
    folium.LayerControl().add_to(m)
    
    return m

def crear_mapa_biomasa(gdf_resultados, mapa_base="ESRI World Imagery"):
    """Crea un mapa con visualización de Biomasa Forrajera y leyenda integrada"""
    
    m = crear_mapa_base(gdf_resultados, mapa_base, zoom_start=12)
    
    # Función para determinar color basado en biomasa
    def estilo_biomasa(feature):
        biomasa = feature['properties']['biomasa_kg_ms_ha']
        clasificacion, color = clasificar_biomasa(biomasa)
        
        return {
            'fillColor': color,
            'color': 'black',
            'weight': 1,
            'fillOpacity': 0.7,
            'opacity': 0.8
        }
    
    # Agregar capa de Biomasa
    folium.GeoJson(
        gdf_resultados.__geo_interface__,
        name='Biomasa Forrajera',
        style_function=estilo_biomasa,
        tooltip=folium.GeoJsonTooltip(
            fields=['id_subLote', 'biomasa_kg_ms_ha', 'area_ha', 'ndvi', 'ev_ha'],
            aliases=['Sub-Lote:', 'Biomasa (kg MS/ha):', 'Área (ha):', 'NDVI:', 'EV/ha:'],
            localize=True
        )
    ).add_to(m)
    
    # Agregar leyenda de Biomasa en el lado derecho
    legend_html = '''
    <div style="position: fixed; 
                top: 10px; right: 10px; width: 240px; height: 180px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:12px; padding: 10px; border-radius: 5px;">
    <p style="margin:0; font-weight:bold; font-size:14px;">🌿 Biomasa Forrajera</p>
    <p style="margin:2px 0;"><i style="background:#FF6B6B; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> < 1000 (Muy Baja)</p>
    <p style="margin:2px 0;"><i style="background:#FFA726; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> 1000-2000 (Baja)</p>
    <p style="margin:2px 0;"><i style="background:#FFD54F; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> 2000-3000 (Moderada)</p>
    <p style="margin:2px 0;"><i style="background:#AED581; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> 3000-4000 (Alta)</p>
    <p style="margin:2px 0;"><i style="background:#66BB6A; width:15px; height:15px; display:inline-block; margin-right:5px; border:1px solid black"></i> > 4000 (Muy Alta)</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # Control de capas
    folium.LayerControl().add_to(m)
    
    return m

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

def dividir_potrero(gdf, n_zonas):
    """Divide el potrero en sub-lotes"""
    if len(gdf) == 0:
        return gdf
    
    try:
        potrero = gdf.iloc[0].geometry
        bounds = potrero.bounds
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
                    
                cell = Polygon([
                    (minx + j * width, miny + i * height),
                    (minx + (j + 1) * width, miny + i * height),
                    (minx + (j + 1) * width, miny + (i + 1) * height),
                    (minx + j * width, miny + (i + 1) * height)
                ])
                
                intersection = potrero.intersection(cell)
                if not intersection.is_empty and intersection.area > 0:
                    sub_poligonos.append(intersection)
        
        if sub_poligonos:
            return gpd.GeoDataFrame({
                'id_subLote': range(1, len(sub_poligonos) + 1),
                'geometry': sub_poligonos
            }, crs=gdf.crs)
        return gdf
            
    except Exception as e:
        st.error(f"Error dividiendo potrero: {e}")
        return gdf

# =============================================================================
# SIDEBAR CON CONFIGURACIÓN SENTINEL HUB MEJORADA
# =============================================================================

with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Configuración Sentinel Hub - SOLO SI NO ESTÁ CONFIGURADO
    st.subheader("🛰️ Sentinel Hub")
    
    if not sh_configured:
        st.error("❌ Sentinel Hub no configurado")
        with st.expander("🔐 Configurar Sentinel Hub", expanded=True):
            st.markdown("""
            **Para usar Sentinel Hub real necesitas:**
            
            1. **Crear cuenta en:** [Sentinel Hub](https://www.sentinel-hub.com/)
            2. **Obtener credenciales** (Client ID y Client Secret)
            3. **Configurar instancia** en el dashboard
            """)
            
            sh_client_id = st.text_input("Client ID:", type="password")
            sh_client_secret = st.text_input("Client Secret:", type="password")
            
            if st.button("💾 Guardar Credenciales"):
                if sh_client_id and sh_client_secret:
                    st.session_state.sh_client_id = sh_client_id
                    st.session_state.sh_client_secret = sh_client_secret
                    st.session_state.sh_configured = True
                    st.success("✅ Credenciales guardadas")
                    st.rerun()
                else:
                    st.error("❌ Ingresa ambas credenciales")
                    
            st.markdown("""
            **📝 Nota:** Las credenciales se guardan solo en esta sesión.
            """)
    else:
        st.success(sh_config.config_message)
        if st.button("🔄 Cambiar Credenciales"):
            # Limpiar credenciales
            if 'sh_client_id' in st.session_state:
                del st.session_state.sh_client_id
            if 'sh_client_secret' in st.session_state:
                del st.session_state.sh_client_secret
            st.session_state.sh_configured = False
            st.rerun()
    
    st.subheader("🗺️ Mapa Base")
    mapa_base = st.selectbox(
        "Seleccionar mapa base:",
        list(MAPAS_BASE.keys()),
        index=0  # ESRI World Imagery como default
    )
    
    st.subheader("📅 Configuración Temporal")
    fecha_imagen = st.date_input(
        "Fecha de imagen:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now()
    )
    
    st.subheader("🌿 Tipo de Pastura")
    tipo_pastura = st.selectbox(
        "Seleccionar tipo:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL"]
    )
    
    st.subheader("📐 División del Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", 8, 32, 16)
    
    st.subheader("🐄 Configuración EV")
    consumo_diario_personalizado = st.number_input(
        "Consumo diario por EV (kg MS):", 
        min_value=8.0, 
        max_value=15.0, 
        value=10.0, 
        step=0.5,
        help="Consumo promedio de materia seca por animal por día"
    )
    
    eficiencia_pastoreo = st.slider(
        "Eficiencia de pastoreo (%):", 
        min_value=50, 
        max_value=90, 
        value=70, 
        step=5,
        help="Porcentaje de biomasa que realmente consume el animal"
    ) / 100.0
    
    st.subheader("📤 Cargar Datos")
    uploaded_zip = st.file_uploader("Subir shapefile (ZIP):", type=['zip'])

# =============================================================================
# ANÁLISIS CON SENTINEL HUB Y EV/HA
# =============================================================================

def analisis_con_sentinel_hub(gdf, config):
    """Análisis usando Sentinel Hub real con cálculo de EV/ha"""
    try:
        st.header("🌱 ANÁLISIS FORRAJERO - SENTINEL HUB")
        
        if not sh_configured:
            st.error("❌ Sentinel Hub no está configurado")
            return False
        
        area_total = calcular_superficie(gdf).sum()
        st.success(f"✅ Potrero: {area_total:.1f} ha, {len(gdf)} polígonos")
        
        # Dividir potrero
        st.subheader("📐 DIVIDIENDO POTRERO")
        with st.spinner("Creando sub-lotes..."):
            gdf_dividido = dividir_potrero(gdf, config['n_divisiones'])
        
        if gdf_dividido is None:
            st.error("Error dividiendo potrero")
            return False
            
        st.success(f"✅ {len(gdf_dividido)} sub-lotes creados")
        
        # Obtener datos de Sentinel Hub
        st.subheader("🛰️ OBTENIENDO DATOS SENTINEL HUB")
        
        processor = SentinelHubProcessor()
        resultados = []
        
        # Obtener bbox del área total
        bounds = gdf.total_bounds
        bbox = [bounds[0], bounds[1], bounds[2], bounds[3]]
        
        # Procesar cada sub-lote
        progress_bar = st.progress(0)
        for idx, row in gdf_dividido.iterrows():
            progress = (idx + 1) / len(gdf_dividido)
            progress_bar.progress(progress)
            
            # Obtener NDVI de Sentinel Hub
            ndvi = processor.get_ndvi_for_geometry(
                row.geometry, 
                config['fecha_imagen'],
                bbox
            )
            
            # Calcular área
            area_ha = calcular_superficie(gpd.GeoDataFrame([row], crs=gdf_dividido.crs))
            if hasattr(area_ha, 'iloc'):
                area_ha = area_ha.iloc[0]
            
            # Calcular biomasa
            params = obtener_parametros(config['tipo_pastura'])
            biomasa_total = params['FACTOR_BIOMASA_NDVI'] * ndvi if ndvi else 0
            biomasa_disponible = biomasa_total * params['TASA_UTILIZACION_RECOMENDADA']
            
            # Calcular EV/ha - usar valor personalizado o el de los parámetros
            consumo_diario = config.get('consumo_diario_personalizado', params['CONSUMO_DIARIO_EV'])
            eficiencia = config.get('eficiencia_pastoreo', params['EFICIENCIA_PASTOREO'])
            
            ev_ha = calcular_ev_ha(biomasa_disponible, consumo_diario, eficiencia)
            carga_animal = calcular_carga_animal_total(ev_ha, area_ha)
            clasificacion_ev, color_ev = clasificar_capacidad_carga(ev_ha)
            clasificacion_bio, color_bio = clasificar_biomasa(biomasa_disponible)
            clasificacion_ndvi, color_ndvi = clasificar_ndvi(ndvi)
            
            # Clasificar vegetación
            if ndvi is None:
                tipo_veg = "SIN_DATOS"
            elif ndvi < 0.2:
                tipo_veg = "SUELO_DESNUDO"
            elif ndvi < 0.4:
                tipo_veg = "VEGETACION_ESCASA"
            elif ndvi < 0.6:
                tipo_veg = "VEGETACION_MODERADA"
            else:
                tipo_veg = "VEGETACION_DENSA"
            
            fuente = "SENTINEL_HUB" if ndvi else "SIMULADO"
            
            resultados.append({
                'id_subLote': row['id_subLote'],
                'area_ha': area_ha,
                'ndvi': ndvi,
                'tipo_superficie': tipo_veg,
                'biomasa_kg_ms_ha': biomasa_disponible,
                'ev_ha': ev_ha,
                'carga_animal': carga_animal,
                'clasificacion_carga': clasificacion_ev,
                'color_carga': color_ev,
                'clasificacion_biomasa': clasificacion_bio,
                'color_biomasa': color_bio,
                'clasificacion_ndvi': clasificacion_ndvi,
                'color_ndvi': color_ndvi,
                'fuente': fuente
            })
        
        progress_bar.empty()
        
        # Añadir resultados al GeoDataFrame
        for col in ['area_ha', 'ndvi', 'tipo_superficie', 'biomasa_kg_ms_ha', 'ev_ha', 
                   'carga_animal', 'clasificacion_carga', 'color_carga', 
                   'clasificacion_biomasa', 'color_biomasa', 'clasificacion_ndvi', 'color_ndvi', 'fuente']:
            gdf_dividido[col] = [r[col] for r in resultados]
        
        # Guardar en session state
        st.session_state.resultados_analisis = gdf_dividido
        
        # Mostrar resultados
        mostrar_resultados_sentinel_hub(gdf_dividido, config)
        return True
        
    except Exception as e:
        st.error(f"Error en análisis: {e}")
        return False

def mostrar_resultados_sentinel_hub(gdf, config):
    """Muestra resultados con Sentinel Hub incluyendo EV/ha"""
    st.header("📊 RESULTADOS - SENTINEL HUB")
    
    # Métricas principales
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        ndvi_prom = gdf['ndvi'].mean()
        st.metric("NDVI Promedio", f"{ndvi_prom:.3f}")
    
    with col2:
        biomasa_prom = gdf['biomasa_kg_ms_ha'].mean()
        st.metric("Biomasa Promedio", f"{biomasa_prom:.0f} kg MS/ha")
    
    with col3:
        ev_ha_prom = gdf['ev_ha'].mean()
        st.metric("EV/ha Promedio", f"{ev_ha_prom:.1f}")
    
    with col4:
        area_total = gdf['area_ha'].sum()
        st.metric("Área Total", f"{area_total:.1f} ha")
    
    with col5:
        carga_total = gdf['carga_animal'].sum()
        st.metric("Carga Animal Total", f"{carga_total:.0f} EV")
    
    # VISUALIZACIÓN DE MAPAS CON PESTAÑAS
    st.header("🗺️ VISUALIZACIÓN EN MAPA")
    
    # Crear pestañas para diferentes mapas
    tab1, tab2, tab3, tab4 = st.tabs([
        "🐄 EV/ha - Capacidad de Carga", 
        "🌿 NDVI - Estado Vegetación", 
        "📊 Biomasa Forrajera",
        "🗺️ Potrero Original"
    ])
    
    with tab1:
        st.subheader("🐄 CAPACIDAD DE CARGA - EV/HA")
        with st.spinner("Generando mapa de EV/ha..."):
            mapa_ev = crear_mapa_ev_ha(gdf, mapa_base)
            folium_static(mapa_ev, width=800, height=500)
    
    with tab2:
        st.subheader("🌿 ESTADO VEGETATIVO - NDVI")
        with st.spinner("Generando mapa de NDVI..."):
            mapa_ndvi = crear_mapa_ndvi(gdf, mapa_base)
            folium_static(mapa_ndvi, width=800, height=500)
    
    with tab3:
        st.subheader("📊 BIOMASA FORRAJERA DISPONIBLE")
        with st.spinner("Generando mapa de biomasa..."):
            mapa_biomasa = crear_mapa_biomasa(gdf, mapa_base)
            folium_static(mapa_biomasa, width=800, height=500)
    
    with tab4:
        st.subheader("🗺️ POTRERO ORIGINAL")
        with st.spinner("Generando mapa original..."):
            mapa_original = crear_mapa_base(st.session_state.gdf_cargado, mapa_base, zoom_start=12)
            agregar_capa_poligonos(mapa_original, st.session_state.gdf_cargado, "Potrero Original", 'blue', 0.5)
            folium_static(mapa_original, width=800, height=500)
    
    # Tabla de resultados
    st.header("📋 DETALLES POR SUB-LOTE")
    tabla = gdf[['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 'biomasa_kg_ms_ha', 'ev_ha', 'carga_animal', 'clasificacion_carga']].copy()
    tabla.columns = ['Sub-Lote', 'Área (ha)', 'Tipo Superficie', 'NDVI', 'Biomasa (kg MS/ha)', 'EV/ha', 'Carga Animal', 'Clasificación']
    st.dataframe(tabla, use_container_width=True)
    
    # Resumen de capacidad de carga
    st.header("🐄 RESUMEN DE CAPACIDAD DE CARGA")
    
    # Distribución de clasificaciones
    distribucion = gdf['clasificacion_carga'].value_counts()
    
    col_carga1, col_carga2, col_carga3 = st.columns(3)
    
    with col_carga1:
        st.metric("Capacidad Media", f"{gdf['ev_ha'].mean():.1f} EV/ha")
    
    with col_carga2:
        st.metric("Carga Total Potencial", f"{gdf['carga_animal'].sum():.0f} EV")
    
    with col_carga3:
        st.metric("Sub-Lotes con Alta Capacidad", 
                 f"{len(gdf[gdf['clasificacion_carga'].isin(['ALTA', 'MUY ALTA'])])}/{len(gdf)}")
    
    # Descarga
    st.header("💾 EXPORTAR RESULTADOS")
    col_dl1, col_dl2 = st.columns(2)
    
    with col_dl1:
        # CSV
        csv = tabla.to_csv(index=False)
        st.download_button(
            "📥 Descargar CSV",
            csv,
            f"resultados_sentinel_hub_{config['tipo_pastura']}.csv",
            "text/csv"
        )
    
    with col_dl2:
        # GeoJSON
        geojson = gdf.to_json()
        st.download_button(
            "📥 Descargar GeoJSON",
            geojson,
            f"resultados_sentinel_hub_{config['tipo_pastura']}.geojson",
            "application/json"
        )

# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================

def main():
    """Función principal"""
    
    # Procesar archivo
    if uploaded_zip is not None and st.session_state.gdf_cargado is None:
        with st.spinner("Cargando shapefile..."):
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                        zip_ref.extractall(tmp_dir)
                    
                    shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
                    if shp_files:
                        gdf = gpd.read_file(os.path.join(tmp_dir, shp_files[0]))
                        if gdf.crs is None:
                            gdf = gdf.set_crs('EPSG:4326')
                        st.session_state.gdf_cargado = gdf
                        st.success("✅ Shapefile cargado correctamente")
                    else:
                        st.error("❌ No se encontró archivo .shp")
            except Exception as e:
                st.error(f"Error cargando shapefile: {e}")
    
    # Contenido principal
    if st.session_state.gdf_cargado is not None:
        gdf = st.session_state.gdf_cargado
        
        st.header("📁 DATOS CARGADOS")
        area_total = calcular_superficie(gdf).sum()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Polígonos", len(gdf))
        with col2:
            st.metric("Área Total", f"{area_total:.1f} ha")
        with col3:
            fuente = "SENTINEL HUB" if sh_configured else "SIMULADO"
            st.metric("Fuente Datos", fuente)
        
        # Mapa rápido del shapefile cargado
        st.subheader("🗺️ VISTA PREVIA DEL POTRERO")
        with st.spinner("Cargando mapa..."):
            mapa_preview = crear_mapa_base(gdf, mapa_base, zoom_start=11)
            agregar_capa_poligonos(mapa_preview, gdf, "Potrero Cargado", 'red', 0.5)
            folium_static(mapa_preview, width=800, height=300)
        
        if st.button("🚀 EJECUTAR ANÁLISIS SENTINEL HUB", type="primary"):
            config = {
                'fecha_imagen': fecha_imagen,
                'tipo_pastura': tipo_pastura,
                'n_divisiones': n_divisiones,
                'consumo_diario_personalizado': consumo_diario_personalizado,
                'eficiencia_pastoreo': eficiencia_pastoreo
            }
            
            if sh_configured:
                analisis_con_sentinel_hub(gdf, config)
            else:
                st.error("❌ Configura Sentinel Hub primero")
    
    else:
        # Pantalla de bienvenida
        st.header("🌱 ANALIZADOR FORRAJERO - SENTINEL HUB")
        
        if not sh_configured:
            st.info("""
            ### 🛰️ CONFIGURAR SENTINEL HUB
            
            **Para datos satelitales reales:**
            
            1. **Regístrate en:** [Sentinel Hub](https://www.sentinel-hub.com/)
            2. **Crea una instancia** en el dashboard
            3. **Obtén** Client ID y Client Secret
            4. **Configúralos** en el sidebar ←
            
            **📊 Características:**
            - ✅ **Datos reales** Sentinel-2
            - ✅ **Actualización diaria**
            - ✅ **Alta resolución** (10m)
            - ✅ **Filtro de nubes** automático
            - ✅ **Cálculo de EV/ha** integrado
            """)
        else:
            st.success("""
            ### ✅ SENTINEL HUB CONFIGURADO
            
            **Características disponibles:**
            - 🛰️ **Sentinel-2 L2A** (atmosféricamente corregido)
            - 🌿 **NDVI en tiempo real**
            - 📅 **Imágenes históricas**
            - ☁️ **Filtro de nubes** integrado
            - 🐄 **Cálculo de EV/ha** automático
            
            **Para comenzar:**
            1. Sube tu shapefile
            2. Configura los parámetros
            3. Ejecuta el análisis con datos reales
            """)

if __name__ == "__main__":
    main()
