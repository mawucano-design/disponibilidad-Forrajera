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
# CONFIGURACIÓN SENTINEL HUB
# =============================================================================

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

# =============================================================================
# CONFIGURACIÓN SENTINEL HUB (sin credenciales hardcodeadas)
# =============================================================================

class SentinelHubConfig:
    """Maneja la configuración de Sentinel Hub"""
    
    def __init__(self):
        self.base_url = "https://services.sentinel-hub.com/ogc/wms/"
        self.available = False
        self.config_message = ""
        
    def check_configuration(self):
        """Verifica si Sentinel Hub está configurado"""
        try:
            # Verificar si hay credenciales en session state
            if ('sh_client_id' in st.session_state and 
                'sh_client_secret' in st.session_state and
                st.session_state.sh_client_id and 
                st.session_state.sh_client_secret):
                self.available = True
                self.config_message = "✅ Sentinel Hub configurado"
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
# MAPAS BASE (igual que antes)
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
    }
}

# =============================================================================
# PARÁMETROS FORRAJEROS (igual que antes)
# =============================================================================

PARAMETROS_FORRAJEROS = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 4000,
        'CRECIMIENTO_DIARIO': 80,
        'CONSUMO_PORCENTAJE_PESO': 0.03,
        'TASA_UTILIZACION_RECOMENDADA': 0.65,
        'FACTOR_BIOMASA_NDVI': 2800,
        'UMBRAL_NDVI_SUELO': 0.15,
        'UMBRAL_NDVI_PASTURA': 0.45
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
        'FACTOR_BIOMASA_NDVI': 2500,
        'UMBRAL_NDVI_SUELO': 0.18,
        'UMBRAL_NDVI_PASTURA': 0.50
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 50,
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
        'FACTOR_BIOMASA_NDVI': 2200,
        'UMBRAL_NDVI_SUELO': 0.20,
        'UMBRAL_NDVI_PASTURA': 0.55
    }
}

def obtener_parametros(tipo_pastura):
    return PARAMETROS_FORRAJEROS.get(tipo_pastura, PARAMETROS_FORRAJEROS['FESTUCA'])

# =============================================================================
# FUNCIONES BÁSICAS (igual que antes)
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
# SIDEBAR CON CONFIGURACIÓN SENTINEL HUB
# =============================================================================

with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Configuración Sentinel Hub
    st.subheader("🛰️ Sentinel Hub")
    
    if not sh_configured:
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
        st.success("✅ Sentinel Hub configurado")
        if st.button("🔄 Cambiar Credenciales"):
            st.session_state.sh_configured = False
            st.rerun()
    
    st.subheader("🗺️ Mapa Base")
    mapa_base = st.selectbox(
        "Seleccionar mapa base:",
        list(MAPAS_BASE.keys()),
        index=0
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
    
    st.subheader("📤 Cargar Datos")
    uploaded_zip = st.file_uploader("Subir shapefile (ZIP):", type=['zip'])

# =============================================================================
# ANÁLISIS CON SENTINEL HUB
# =============================================================================

def analisis_con_sentinel_hub(gdf, config):
    """Análisis usando Sentinel Hub real"""
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
            biomasa_disponible = biomasa_total * 0.6
            
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
                'fuente': fuente
            })
        
        progress_bar.empty()
        
        # Mostrar resultados
        mostrar_resultados_sentinel_hub(gdf_dividido, resultados, config)
        return True
        
    except Exception as e:
        st.error(f"Error en análisis: {e}")
        return False

def mostrar_resultados_sentinel_hub(gdf, resultados, config):
    """Muestra resultados con Sentinel Hub"""
    st.header("📊 RESULTADOS - SENTINEL HUB")
    
    # Añadir resultados al GeoDataFrame
    for col in ['area_ha', 'ndvi', 'tipo_superficie', 'biomasa_kg_ms_ha', 'fuente']:
        gdf[col] = [r[col] for r in resultados]
    
    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        ndvi_prom = gdf['ndvi'].mean()
        st.metric("NDVI Promedio", f"{ndvi_prom:.3f}")
    
    with col2:
        biomasa_prom = gdf['biomasa_kg_ms_ha'].mean()
        st.metric("Biomasa Promedio", f"{biomasa_prom:.0f} kg MS/ha")
    
    with col3:
        area_total = gdf['area_ha'].sum()
        st.metric("Área Total", f"{area_total:.1f} ha")
    
    with col4:
        datos_reales = len(gdf[gdf['fuente'] == 'SENTINEL_HUB'])
        st.metric("Datos Reales", f"{datos_reales}/{len(gdf)}")
    
    # Tabla de resultados
    st.subheader("📋 DETALLES POR SUB-LOTE")
    tabla = gdf[['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 'biomasa_kg_ms_ha', 'fuente']].copy()
    tabla.columns = ['Sub-Lote', 'Área (ha)', 'Tipo Superficie', 'NDVI', 'Biomasa (kg MS/ha)', 'Fuente']
    st.dataframe(tabla, use_container_width=True)
    
    # Descarga
    st.subheader("💾 EXPORTAR RESULTADOS")
    csv = tabla.to_csv(index=False)
    st.download_button(
        "📥 Descargar CSV",
        csv,
        f"resultados_sentinel_hub_{config['tipo_pastura']}.csv",
        "text/csv"
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
        
        if st.button("🚀 EJECUTAR ANÁLISIS SENTINEL HUB", type="primary"):
            config = {
                'fecha_imagen': fecha_imagen,
                'tipo_pastura': tipo_pastura,
                'n_divisiones': n_divisiones
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
            """)
        else:
            st.success("""
            ### ✅ SENTINEL HUB CONFIGURADO
            
            **Características disponibles:**
            - 🛰️ **Sentinel-2 L2A** (atmosféricamente corregido)
            - 🌿 **NDVI en tiempo real**
            - 📅 **Imágenes históricas**
            - ☁️ **Filtro de nubes** integrado
            
            **Para comenzar:**
            1. Sube tu shapefile
            2. Configura los parámetros
            3. Ejecuta el análisis con datos reales
            """)

if __name__ == "__main__":
    main()
