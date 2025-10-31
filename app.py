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
# CONFIGURACIÓN INICIAL
# =============================================================================

st.set_page_config(
    page_title="🌱 Analizador Forrajero - Satélite",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🌱 ANALIZADOR FORRAJERO CON IMÁGENES SATELITALES")
st.markdown("---")

# Configuración para shapefiles
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Inicializar session state
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'resultados_analisis' not in st.session_state:
    st.session_state.resultados_analisis = None

# =============================================================================
# PROCESADOR DE IMÁGENES SATELITALES (SIN CREDENCIALES)
# =============================================================================

class SatelliteProcessor:
    """Procesa datos de satélite usando servicios públicos"""
    
    def __init__(self):
        self.available = True
    
    def get_ndvi_from_gee(self, geometry, fecha):
        """Obtiene NDVI usando Google Earth Engine (simulado para demo)"""
        try:
            # En una implementación real, aquí iría la conexión a GEE
            # Por ahora simulamos con datos realistas basados en la ubicación
            
            centroid = geometry.centroid
            lat, lon = centroid.y, centroid.x
            
            # Simular patrones realistas basados en ubicación y época
            base_ndvi = self._simulate_seasonal_ndvi(lat, lon, fecha)
            
            # Variación espacial dentro del lote
            variation = (hash(f"{lat:.3f},{lon:.3f}") % 100) / 1000  # Pequeña variación
            
            ndvi = base_ndvi + variation
            return max(0.1, min(0.9, ndvi))
            
        except Exception as e:
            st.error(f"Error obteniendo NDVI: {e}")
            return self._get_fallback_ndvi()
    
    def _simulate_seasonal_ndvi(self, lat, lon, fecha):
        """Simula NDVI basado en ubicación y época del año"""
        # Factores estacionales
        mes = fecha.month
        if mes in [12, 1, 2]:  # Verano (hemisferio sur)
            base = 0.6
        elif mes in [3, 4, 5]:  # Otoño
            base = 0.5
        elif mes in [6, 7, 8]:  # Invierno
            base = 0.4
        else:  # Primavera
            base = 0.7
        
        # Ajustar por latitud (mayor latitud = menor NDVI en general)
        lat_factor = 1 - (abs(lat) / 90) * 0.3
        
        # Variación por ubicación específica
        location_variation = (hash(f"{lat:.1f},{lon:.1f}") % 50) / 1000
        
        return base * lat_factor + location_variation
    
    def _get_fallback_ndvi(self):
        """NDVI por defecto si falla la obtención"""
        return 0.5 + np.random.normal(0, 0.1)
    
    def get_satellite_image_url(self, bounds, fecha, mapa_base="ESRI"):
        """Genera URL para imagen satelital (usando servicios públicos)"""
        try:
            # Servicios públicos de imágenes satelitales
            if mapa_base == "ESRI":
                # ESRI World Imagery (incluye imágenes satelitales)
                return None  # Se usa directamente en el mapa base
            
            elif mapa_base == "SENTINEL":
                # Para una implementación real, aquí iría la URL de Sentinel Hub
                # Usando WMS público (ejemplo)
                minx, miny, maxx, maxy = bounds
                url = f"https://tiles.maps.eox.at/wms?service=WMS&request=GetMap&version=1.1.1&layers=s2cloudless&styles=&format=image%2Fjpeg&transparent=false&width=800&height=600&srs=EPSG%3A4326&bbox={minx},{miny},{maxx},{maxy}"
                return url
                
        except:
            return None

# Inicializar procesador
satellite_processor = SatelliteProcessor()

# =============================================================================
# MAPAS BASE MEJORADOS
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
    "Google Satellite": {
        "url": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        "attribution": "Google",
        "name": "Google Satellite"
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
        'CONSUMO_DIARIO_EV': 12,
        'EFICIENCIA_PASTOREO': 0.75
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
    """Calcula Equivalente Vaca por hectárea (EV/ha)"""
    if consumo_diario_ev <= 0:
        return 0
    ev_ha = (biomasa_disponible_kg_ms_ha * eficiencia_pastoreo) / consumo_diario_ev
    return max(0, ev_ha)

def calcular_carga_animal_total(ev_ha, area_ha):
    """Calcula la carga animal total para un área"""
    return ev_ha * area_ha

def clasificar_capacidad_carga(ev_ha):
    """Clasifica la capacidad de carga según EV/ha"""
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

# =============================================================================
# FUNCIONES DE VISUALIZACIÓN DE MAPAS
# =============================================================================

def crear_mapa_base(gdf, mapa_seleccionado="ESRI World Imagery", zoom_start=12):
    """Crea un mapa base con el estilo seleccionado"""
    
    bounds = gdf.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
        tiles=None,
        control_scale=True
    )
    
    for nombre, config in MAPAS_BASE.items():
        folium.TileLayer(
            tiles=config["url"],
            attr=config["attribution"],
            name=config["name"],
            control=True,
            show=(nombre == mapa_seleccionado)
        ).add_to(m)
    
    return m

def agregar_capa_poligonos(mapa, gdf, nombre_capa, color='blue', fill_opacity=0.3):
    """Agrega una capa de polígonos al mapa"""
    
    def estilo_poligono(feature):
        return {
            'fillColor': color,
            'color': 'black',
            'weight': 2,
            'fillOpacity': fill_opacity,
            'opacity': 0.8
        }
    
    available_fields = []
    available_aliases = []
    
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
    
    if not available_fields:
        tooltip = folium.GeoJsonTooltip(fields=[], aliases=[], localize=True)
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
    """Crea un mapa con visualización de NDVI"""
    
    m = crear_mapa_base(gdf_resultados, mapa_base, zoom_start=12)
    
    def estilo_ndvi(feature):
        ndvi = feature['properties']['ndvi']
        if ndvi < 0.2:
            color = '#8B4513'
        elif ndvi < 0.4:
            color = '#FFD700'
        elif ndvi < 0.6:
            color = '#32CD32'
        else:
            color = '#006400'
        
        return {
            'fillColor': color,
            'color': 'black',
            'weight': 1,
            'fillOpacity': 0.7,
            'opacity': 0.8
        }
    
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
    
    legend_html = '''
    <div style="position: fixed; bottom: 50px; left: 50px; width: 220px; height: 160px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:14px; padding: 10px; border-radius: 5px;">
    <p style="margin:0; font-weight:bold;">🌿 Leyenda NDVI</p>
    <p style="margin:2px 0;"><i style="background:#8B4513; width:20px; height:20px; display:inline-block; margin-right:5px; border:1px solid black"></i> < 0.2 (Suelo)</p>
    <p style="margin:2px 0;"><i style="background:#FFD700; width:20px; height:20px; display:inline-block; margin-right:5px; border:1px solid black"></i> 0.2-0.4 (Escasa)</p>
    <p style="margin:2px 0;"><i style="background:#32CD32; width:20px; height:20px; display:inline-block; margin-right:5px; border:1px solid black"></i> 0.4-0.6 (Moderada)</p>
    <p style="margin:2px 0;"><i style="background:#006400; width:20px; height:20px; display:inline-block; margin-right:5px; border:1px solid black"></i> > 0.6 (Densa)</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl().add_to(m)
    
    return m

def crear_mapa_ev_ha(gdf_resultados, mapa_base="ESRI World Imagery"):
    """Crea un mapa con visualización de EV/ha"""
    
    m = crear_mapa_base(gdf_resultados, mapa_base, zoom_start=12)
    
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
    
    legend_html = '''
    <div style="position: fixed; bottom: 50px; left: 50px; width: 240px; height: 180px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:14px; padding: 10px; border-radius: 5px;">
    <p style="margin:0; font-weight:bold;">🐄 Capacidad de Carga (EV/ha)</p>
    <p style="margin:2px 0;"><i style="background:#FF6B6B; width:20px; height:20px; display:inline-block; margin-right:5px; border:1px solid black"></i> < 0.5 (Muy Baja)</p>
    <p style="margin:2px 0;"><i style="background:#FFA726; width:20px; height:20px; display:inline-block; margin-right:5px; border:1px solid black"></i> 0.5-1.0 (Baja)</p>
    <p style="margin:2px 0;"><i style="background:#FFD54F; width:20px; height:20px; display:inline-block; margin-right:5px; border:1px solid black"></i> 1.0-1.5 (Moderada)</p>
    <p style="margin:2px 0;"><i style="background:#AED581; width:20px; height:20px; display:inline-block; margin-right:5px; border:1px solid black"></i> 1.5-2.0 (Alta)</p>
    <p style="margin:2px 0;"><i style="background:#66BB6A; width:20px; height:20px; display:inline-block; margin-right:5px; border:1px solid black"></i> > 2.0 (Muy Alta)</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
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
# SIDEBAR SIMPLIFICADO (SIN CREDENCIALES)
# =============================================================================

with st.sidebar:
    st.header("⚙️ Configuración del Análisis")
    
    st.subheader("🗺️ Mapa Base")
    mapa_base = st.selectbox(
        "Seleccionar mapa base:",
        list(MAPAS_BASE.keys()),
        index=0
    )
    
    st.subheader("📅 Fecha de Imagen")
    fecha_imagen = st.date_input(
        "Seleccionar fecha:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now(),
        help="La fecha aproximada de la imagen satelital a analizar"
    )
    
    st.subheader("🌿 Tipo de Pastura")
    tipo_pastura = st.selectbox(
        "Seleccionar tipo de pastura:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL"]
    )
    
    st.subheader("📐 División del Potrero")
    n_divisiones = st.slider(
        "Número de sub-lotes:", 
        min_value=4, 
        max_value=36, 
        value=16,
        help="Entre más divisiones, mayor detalle del análisis"
    )
    
    st.subheader("🐄 Configuración EV")
    consumo_diario_personalizado = st.number_input(
        "Consumo diario por EV (kg MS):", 
        min_value=8.0, 
        max_value=15.0, 
        value=10.0, 
        step=0.5
    )
    
    eficiencia_pastoreo = st.slider(
        "Eficiencia de pastoreo (%):", 
        min_value=50, 
        max_value=90, 
        value=70, 
        step=5
    ) / 100.0
    
    st.subheader("📤 Cargar Shapefile")
    uploaded_zip = st.file_uploader(
        "Subir archivo ZIP con shapefile:",
        type=['zip'],
        help="El ZIP debe contener .shp, .shx, .dbf, .prj"
    )

# =============================================================================
# ANÁLISIS PRINCIPAL
# =============================================================================

def ejecutar_analisis_satelital(gdf, config):
    """Ejecuta el análisis satelital completo"""
    try:
        st.header("🌱 ANÁLISIS FORRAJERO SATELITAL")
        
        area_total = calcular_superficie(gdf).sum()
        st.success(f"✅ Potrero cargado: {area_total:.1f} ha, {len(gdf)} polígonos")
        
        # Dividir potrero
        st.subheader("📐 DIVIDIENDO POTRERO")
        with st.spinner("Creando sub-lotes..."):
            gdf_dividido = dividir_potrero(gdf, config['n_divisiones'])
        
        if gdf_dividido is None or len(gdf_dividido) == 0:
            st.error("Error dividiendo potrero")
            return False
            
        st.success(f"✅ {len(gdf_dividido)} sub-lotes creados")
        
        # Obtener datos satelitales
        st.subheader("🛰️ ANALIZANDO IMÁGENES SATELITALES")
        
        resultados = []
        progress_bar = st.progress(0)
        
        for idx, row in gdf_dividido.iterrows():
            progress = (idx + 1) / len(gdf_dividido)
            progress_bar.progress(progress)
            
            # Obtener NDVI del procesador
            ndvi = satellite_processor.get_ndvi_from_gee(row.geometry, config['fecha_imagen'])
            
            # Calcular área
            area_ha = calcular_superficie(gpd.GeoDataFrame([row], crs=gdf_dividido.crs))
            if hasattr(area_ha, 'iloc'):
                area_ha = area_ha.iloc[0]
            
            # Calcular biomasa y EV/ha
            params = obtener_parametros(config['tipo_pastura'])
            biomasa_total = params['FACTOR_BIOMASA_NDVI'] * ndvi
            biomasa_disponible = biomasa_total * params['TASA_UTILIZACION_RECOMENDADA']
            
            consumo_diario = config.get('consumo_diario_personalizado', params['CONSUMO_DIARIO_EV'])
            eficiencia = config.get('eficiencia_pastoreo', params['EFICIENCIA_PASTOREO'])
            
            ev_ha = calcular_ev_ha(biomasa_disponible, consumo_diario, eficiencia)
            carga_animal = calcular_carga_animal_total(ev_ha, area_ha)
            clasificacion_ev, color_ev = clasificar_capacidad_carga(ev_ha)
            
            # Clasificar vegetación
            if ndvi < 0.2:
                tipo_veg = "SUELO_DESNUDO"
            elif ndvi < 0.4:
                tipo_veg = "VEGETACION_ESCASA"
            elif ndvi < 0.6:
                tipo_veg = "VEGETACION_MODERADA"
            else:
                tipo_veg = "VEGETACION_DENSA"
            
            resultados.append({
                'id_subLote': row['id_subLote'],
                'area_ha': area_ha,
                'ndvi': ndvi,
                'tipo_superficie': tipo_veg,
                'biomasa_kg_ms_ha': biomasa_disponible,
                'ev_ha': ev_ha,
                'carga_animal': carga_animal,
                'clasificacion_carga': clasificacion_ev,
                'color_carga': color_ev
            })
        
        progress_bar.empty()
        
        # Añadir resultados al GeoDataFrame
        for col in ['area_ha', 'ndvi', 'tipo_superficie', 'biomasa_kg_ms_ha', 'ev_ha', 
                   'carga_animal', 'clasificacion_carga', 'color_carga']:
            gdf_dividido[col] = [r[col] for r in resultados]
        
        # Guardar en session state
        st.session_state.resultados_analisis = gdf_dividido
        
        # Mostrar resultados
        mostrar_resultados_analisis(gdf_dividido, config)
        return True
        
    except Exception as e:
        st.error(f"Error en análisis: {e}")
        return False

def mostrar_resultados_analisis(gdf, config):
    """Muestra los resultados del análisis"""
    st.header("📊 RESULTADOS DEL ANÁLISIS")
    
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
    
    # VISUALIZACIÓN DE MAPAS
    st.header("🗺️ VISUALIZACIÓN EN MAPA")
    
    col_map1, col_map2 = st.columns(2)
    with col_map1:
        tipo_mapa = st.selectbox(
            "Tipo de visualización:",
            ["NDVI por Sub-Lote", "EV/ha por Sub-Lote", "Potrero Original"]
        )
    with col_map2:
        mapa_base_seleccionado = st.selectbox(
            "Mapa base:",
            list(MAPAS_BASE.keys()),
            index=0,
            key="mapa_resultados"
        )
    
    # Crear mapa según selección
    if tipo_mapa == "NDVI por Sub-Lote":
        st.subheader("🌿 MAPA DE NDVI")
        with st.spinner("Generando mapa..."):
            mapa_ndvi = crear_mapa_ndvi(gdf, mapa_base_seleccionado)
            folium_static(mapa_ndvi, width=800, height=400)
    
    elif tipo_mapa == "EV/ha por Sub-Lote":
        st.subheader("🐄 MAPA DE EV/HA")
        with st.spinner("Generando mapa..."):
            mapa_ev = crear_mapa_ev_ha(gdf, mapa_base_seleccionado)
            folium_static(mapa_ev, width=800, height=400)
    
    elif tipo_mapa == "Potrero Original":
        st.subheader("🗺️ POTRERO ORIGINAL")
        with st.spinner("Generando mapa..."):
            mapa_original = crear_mapa_base(st.session_state.gdf_cargado, mapa_base_seleccionado, zoom_start=12)
            agregar_capa_poligonos(mapa_original, st.session_state.gdf_cargado, "Potrero Original", 'blue', 0.5)
            folium_static(mapa_original, width=800, height=400)
    
    # Tabla de resultados
    st.header("📋 DETALLES POR SUB-LOTE")
    tabla = gdf[['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 'biomasa_kg_ms_ha', 'ev_ha', 'carga_animal', 'clasificacion_carga']].copy()
    tabla.columns = ['Sub-Lote', 'Área (ha)', 'Tipo Superficie', 'NDVI', 'Biomasa (kg MS/ha)', 'EV/ha', 'Carga Animal', 'Clasificación']
    st.dataframe(tabla, use_container_width=True)
    
    # Resumen de capacidad de carga
    st.header("🐄 RESUMEN DE CAPACIDAD DE CARGA")
    
    col_carga1, col_carga2, col_carga3 = st.columns(3)
    
    with col_carga1:
        st.metric("Capacidad Media", f"{gdf['ev_ha'].mean():.1f} EV/ha")
    
    with col_carga2:
        st.metric("Carga Total Potencial", f"{gdf['carga_animal'].sum():.0f} EV")
    
    with col_carga3:
        alta_capacidad = len(gdf[gdf['clasificacion_carga'].isin(['ALTA', 'MUY ALTA'])])
        st.metric("Sub-Lotes con Alta Capacidad", f"{alta_capacidad}/{len(gdf)}")
    
    # Descarga
    st.header("💾 EXPORTAR RESULTADOS")
    col_dl1, col_dl2 = st.columns(2)
    
    with col_dl1:
        csv = tabla.to_csv(index=False)
        st.download_button(
            "📥 Descargar CSV",
            csv,
            f"analisis_forrajero_{config['tipo_pastura']}_{datetime.now().strftime('%Y%m%d')}.csv",
            "text/csv"
        )
    
    with col_dl2:
        geojson = gdf.to_json()
        st.download_button(
            "📥 Descargar GeoJSON",
            geojson,
            f"analisis_forrajero_{config['tipo_pastura']}_{datetime.now().strftime('%Y%m%d')}.geojson",
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
                        st.error("❌ No se encontró archivo .shp en el ZIP")
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
            st.metric("Estado", "✅ Listo para analizar")
        
        # Mapa rápido del shapefile cargado
        st.subheader("🗺️ VISTA PREVIA DEL POTRERO")
        with st.spinner("Cargando mapa..."):
            mapa_preview = crear_mapa_base(gdf, mapa_base, zoom_start=11)
            agregar_capa_poligonos(mapa_preview, gdf, "Potrero Cargado", 'red', 0.5)
            folium_static(mapa_preview, width=800, height=300)
        
        # BOTÓN SIEMPRE VISIBLE
        st.markdown("---")
        st.header("🚀 EJECUTAR ANÁLISIS")
        
        if st.button("🌱 INICIAR ANÁLISIS SATELITAL", type="primary", use_container_width=True):
            config = {
                'fecha_imagen': fecha_imagen,
                'tipo_pastura': tipo_pastura,
                'n_divisiones': n_divisiones,
                'consumo_diario_personalizado': consumo_diario_personalizado,
                'eficiencia_pastoreo': eficiencia_pastoreo
            }
            
            ejecutar_analisis_satelital(gdf, config)
    
    else:
        # Pantalla de bienvenida
        st.header("🌱 ANALIZADOR FORRAJERO CON IMÁGENES SATELITALES")
        
        st.success("""
        ### ✅ ANÁLISIS SIN CONFIGURACIÓN COMPLEJA
        
        **Características:**
        - 🛰️ **Análisis satelital** sin necesidad de credenciales
        - 🌿 **NDVI estimado** basado en ubicación y época del año
        - 📅 **Imágenes históricas** simuladas
        - 🐄 **Cálculo de EV/ha** automático
        - 💰 **Completamente gratuito**
        
        **Para comenzar:**
        1. ⬆️ **Sube tu shapefile** en formato ZIP en el sidebar
        2. ⚙️ **Configura** los parámetros de análisis
        3. 🚀 **Ejecuta el análisis** con el botón principal
        
        **📁 Formato requerido:** ZIP con archivos .shp, .shx, .dbf, .prj
        """)

if __name__ == "__main__":
    main()
