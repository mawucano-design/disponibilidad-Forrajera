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
from shapely.geometry import Polygon
import math
import json
import folium
from streamlit_folium import folium_static
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# CONFIGURACIÓN INICIAL
# =============================================================================

st.set_page_config(
    page_title="🌱 Analizador Forrajero",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🌱 ANALIZADOR FORRAJERO - MAPAS ESRI & SENTINEL")
st.markdown("---")

# Configuración para shapefiles
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Inicializar session state
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'analisis_completado' not in st.session_state:
    st.session_state.analisis_completado = False

# =============================================================================
# MAPAS BASE DISPONIBLES
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
    "ESRI Topographic": {
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Esri, HERE, Garmin",
        "name": "ESRI Topo"
    },
    "OpenStreetMap": {
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "OpenStreetMap contributors",
        "name": "OSM"
    },
    "Google Satellite": {
        "url": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        "attribution": "Google Satellite",
        "name": "Google Sat"
    }
}

# =============================================================================
# PARÁMETROS FORRAJEROS
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
        'COLOR': '#1a9850'
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_PORCENTAJE_PESO': 0.028,
        'TASA_UTILIZACION_RECOMENDADA': 0.60,
        'FACTOR_BIOMASA_NDVI': 2500,
        'UMBRAL_NDVI_SUELO': 0.18,
        'UMBRAL_NDVI_PASTURA': 0.50,
        'COLOR': '#a6d96a'
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 50,
        'CONSUMO_PORCENTAJE_PESO': 0.025,
        'TASA_UTILIZACION_RECOMENDADA': 0.55,
        'FACTOR_BIOMASA_NDVI': 2200,
        'UMBRAL_NDVI_SUELO': 0.20,
        'UMBRAL_NDVI_PASTURA': 0.55,
        'COLOR': '#fee08b'
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 2800,
        'CRECIMIENTO_DIARIO': 45,
        'CONSUMO_PORCENTAJE_PESO': 0.022,
        'TASA_UTILIZACION_RECOMENDADA': 0.50,
        'FACTOR_BIOMASA_NDVI': 2000,
        'UMBRAL_NDVI_SUELO': 0.25,
        'UMBRAL_NDVI_PASTURA': 0.60,
        'COLOR': '#fdae61'
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 2500,
        'CRECIMIENTO_DIARIO': 20,
        'CONSUMO_PORCENTAJE_PESO': 0.020,
        'TASA_UTILIZACION_RECOMENDADA': 0.45,
        'FACTOR_BIOMASA_NDVI': 1800,
        'UMBRAL_NDVI_SUELO': 0.30,
        'UMBRAL_NDVI_PASTURA': 0.65,
        'COLOR': '#d73027'
    }
}

def obtener_parametros(tipo_pastura):
    return PARAMETROS_FORRAJEROS.get(tipo_pastura, PARAMETROS_FORRAJEROS['FESTUCA'])

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
# SENTINEL-2 MEJORADO
# =============================================================================

class SimuladorSentinel2:
    """Datos Sentinel-2 realistas basados en patrones espaciales"""
    
    def __init__(self):
        self.patrones_vegetacion = {
            # Patrones basados en casos reales de agricultura
            'SUELO_DESNUDO': {'ndvi_range': (0.05, 0.20), 'frecuencia': 0.1},
            'VEGETACION_ESCASA': {'ndvi_range': (0.20, 0.40), 'frecuencia': 0.3},
            'VEGETACION_MODERADA': {'ndvi_range': (0.40, 0.60), 'frecuencia': 0.4},
            'VEGETACION_DENSA': {'ndvi_range': (0.60, 0.85), 'frecuencia': 0.2}
        }
    
    def simular_indices_vegetacion(self, id_subLote, centroid, fecha, area_ha):
        """índices de vegetación realistas basados en posición y fecha"""
        try:
            # Variación espacial basada en posición (para patrones realistas)
            x_norm = (centroid.x * 1000) % 100 / 100
            y_norm = (centroid.y * 1000) % 100 / 100
            
            # Variación temporal (estacional)
            dia_del_año = fecha.timetuple().tm_yday
            factor_estacional = 0.4 * math.sin(2 * math.pi * dia_del_año / 365 - math.pi/2) + 0.6
            
            # Determinar tipo de vegetación basado en posición (patrones reales)
            valor_base = (x_norm + y_norm) / 2
            
            # Patrones espaciales típicos en agricultura
            if valor_base < 0.1:
                tipo = 'SUELO_DESNUDO'  # Bordes o áreas problemáticas
            elif valor_base < 0.4:
                tipo = 'VEGETACION_ESCASA'  # Transición
            elif valor_base < 0.8:
                tipo = 'VEGETACION_MODERADA'  # Áreas principales
            else:
                tipo = 'VEGETACION_DENSA'  # Zonas óptimas
            
            # Generar NDVI según el tipo con variabilidad realista
            rango = self.patrones_vegetacion[tipo]['ndvi_range']
            ndvi_base = rango[0] + (rango[1] - rango[0]) * (x_norm * y_norm)
            ndvi = ndvi_base * factor_estacional
            
            # Añadir variabilidad natural (ruido gaussiano)
            ndvi += np.random.normal(0, 0.03)
            ndvi = max(0.05, min(0.85, ndvi))
            
            # Calcular otros índices de forma consistente
            evi = ndvi * 1.1 + np.random.normal(0, 0.02)
            savi = ndvi * 1.05 + np.random.normal(0, 0.02)
            msavi2 = ndvi * 1.02 + np.random.normal(0, 0.01)
            
            # Índices de suelo (inversamente relacionados con vegetación)
            bsi = 0.3 - (ndvi * 0.4) + np.random.normal(0, 0.05)
            ndbi = 0.2 - (ndvi * 0.3) + np.random.normal(0, 0.03)
            
            # Cobertura vegetal realista
            cobertura_vegetal = min(0.95, max(0.05, ndvi * 1.2))
            
            return {
                'ndvi': ndvi,
                'evi': max(0.1, min(1.0, evi)),
                'savi': max(0.1, min(1.0, savi)),
                'msavi2': max(0.1, min(1.0, msavi2)),
                'bsi': max(-1.0, min(1.0, bsi)),
                'ndbi': max(-1.0, min(1.0, ndbi)),
                'tipo_superficie': tipo,
                'cobertura_vegetal': cobertura_vegetal,
                'calidad_datos': 'ALTA' if ndvi > 0.3 else 'MEDIA'
            }
            
        except Exception as e:
            # Valores por defecto en caso de error
            return {
                'ndvi': 0.5,
                'evi': 0.55,
                'savi': 0.52,
                'msavi2': 0.51,
                'bsi': 0.1,
                'ndbi': 0.05,
                'tipo_superficie': 'VEGETACION_MODERADA',
                'cobertura_vegetal': 0.6,
                'calidad_datos': 'MEDIA'
            }

# =============================================================================
# VISUALIZADOR DE MAPAS
# =============================================================================

class VisualizadorMapas:
    """Clase para crear mapas interactivos con múltiples bases"""
    
    def __init__(self):
        self.simulador = SimuladorSentinel2()
    
    def crear_mapa_interactivo(self, gdf, mapa_base="ESRI World Imagery", mostrar_ndvi=False):
        """Crea mapa interactivo con la base seleccionada"""
        try:
            # Calcular centro y bounds
            centroid = gdf.geometry.centroid.iloc[0]
            bounds = gdf.total_bounds
            
            # Crear mapa centrado
            m = folium.Map(
                location=[centroid.y, centroid.x],
                zoom_start=13,
                control_scale=True
            )
            
            # Añadir la capa base seleccionada
            base_config = MAPAS_BASE[mapa_base]
            folium.TileLayer(
                tiles=base_config["url"],
                attr=base_config["attribution"],
                name=base_config["name"],
                overlay=False
            ).add_to(m)
            
            # Añadir otras capas base como opciones
            for nombre, config in MAPAS_BASE.items():
                if nombre != mapa_base:
                    folium.TileLayer(
                        tiles=config["url"],
                        attr=config["attribution"],
                        name=config["name"],
                        overlay=False
                    ).add_to(m)
            
            # Añadir polígonos con información
            self._añadir_poligonos_mapa(m, gdf, mostrar_ndvi)
            
            # Ajustar vista al bounds
            m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
            
            # Control de capas
            folium.LayerControl().add_to(m)
            
            return m
            
        except Exception as e:
            st.error(f"Error creando mapa: {e}")
            return None
    
    def _añadir_poligonos_mapa(self, m, gdf, mostrar_ndvi):
        """Añade polígonos al mapa con estilo y tooltips"""
        try:
            for idx, row in gdf.iterrows():
                # Determinar color basado en NDVI si está disponible
                if mostrar_ndvi and 'ndvi' in gdf.columns:
                    ndvi = row['ndvi']
                    if ndvi < 0.2:
                        color = '#d73027'  # Rojo - suelo desnudo
                        opacity = 0.7
                    elif ndvi < 0.4:
                        color = '#fdae61'  # Naranja - vegetación escasa
                        opacity = 0.7
                    elif ndvi < 0.6:
                        color = '#a6d96a'  # Verde claro - moderada
                        opacity = 0.6
                    else:
                        color = '#1a9850'  # Verde oscuro - densa
                        opacity = 0.6
                else:
                    color = '#3388ff'  # Azul por defecto
                    opacity = 0.5
                
                # Crear tooltip informativo
                tooltip_text = f"<b>Sub-lote: {row.get('id_subLote', idx+1)}</b>"
                
                if 'area_ha' in gdf.columns:
                    tooltip_text += f"<br>Área: {row['area_ha']:.2f} ha"
                
                if mostrar_ndvi and 'ndvi' in gdf.columns:
                    tooltip_text += f"<br>NDVI: {row['ndvi']:.3f}"
                
                if 'tipo_superficie' in gdf.columns:
                    tooltip_text += f"<br>Tipo: {row['tipo_superficie']}"
                
                if 'biomasa_disponible_kg_ms_ha' in gdf.columns:
                    tooltip_text += f"<br>Biomasa: {row['biomasa_disponible_kg_ms_ha']:.0f} kg MS/ha"
                
                # Añadir polígono al mapa
                folium.GeoJson(
                    row.geometry.__geo_interface__,
                    style_function=lambda x, color=color, opacity=opacity: {
                        'fillColor': color,
                        'color': '#000000',
                        'weight': 2,
                        'fillOpacity': opacity
                    },
                    tooltip=folium.Tooltip(tooltip_text, sticky=True)
                ).add_to(m)
                
                # Añadir número de sub-lote en el centro
                centroid = row.geometry.centroid
                folium.Marker(
                    [centroid.y, centroid.x],
                    icon=folium.DivIcon(
                        html=f'''
                        <div style="
                            font-weight: bold; 
                            color: black; 
                            background: white; 
                            padding: 3px; 
                            border-radius: 4px; 
                            border: 2px solid black;
                            font-size: 10px;
                        ">{row.get("id_subLote", idx+1)}</div>
                        '''
                    )
                ).add_to(m)
                
        except Exception as e:
            st.error(f"Error añadiendo polígonos: {e}")
    
    def crear_mapa_tematico_ndvi(self, gdf_analizado, tipo_pastura):
        """Crea mapa temático de NDVI para el reporte"""
        try:
            fig, ax = plt.subplots(1, 1, figsize=(15, 10))
            
            # Crear colormap para NDVI
            cmap = LinearSegmentedColormap.from_list('ndvi_cmap', 
                ['#d73027', '#fdae61', '#a6d96a', '#1a9850'])
            
            # Plotear cada polígono con color según NDVI
            for idx, row in gdf_analizado.iterrows():
                ndvi = row['ndvi']
                color = cmap(ndvi)
                
                gdf_analizado.iloc[[idx]].plot(
                    ax=ax,
                    color=color,
                    edgecolor='black',
                    linewidth=1.5
                )
                
                # Añadir etiqueta con ID y NDVI
                centroid = row.geometry.centroid
                ax.annotate(
                    f"S{row['id_subLote']}\n{ndvi:.2f}",
                    (centroid.x, centroid.y),
                    xytext=(5, 5),
                    textcoords="offset points",
                    fontsize=8,
                    color='black',
                    weight='bold',
                    bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.8)
                )
            
            ax.set_title(f'🌿 MAPA DE NDVI - {tipo_pastura}\n(Simulación Sentinel-2 Harmonized)', 
                        fontsize=16, fontweight='bold', pad=20)
            ax.set_xlabel('Longitud')
            ax.set_ylabel('Latitud')
            ax.grid(True, alpha=0.3)
            
            # Añadir barra de color
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=0, vmax=1))
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
            cbar.set_label('NDVI', fontsize=12, fontweight='bold')
            
            # Añadir leyenda de tipos de superficie
            leyenda_elementos = [
                mpatches.Patch(color='#d73027', label='Suelo Desnudo (NDVI < 0.2)'),
                mpatches.Patch(color='#fdae61', label='Vegetación Escasa (0.2-0.4)'),
                mpatches.Patch(color='#a6d96a', label='Vegetación Moderada (0.4-0.6)'),
                mpatches.Patch(color='#1a9850', label='Vegetación Densa (NDVI > 0.6)')
            ]
            ax.legend(handles=leyenda_elementos, loc='upper right', fontsize=9)
            
            plt.tight_layout()
            
            # Convertir a imagen para Streamlit
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            buf.seek(0)
            plt.close()
            
            return buf
            
        except Exception as e:
            st.error(f"Error creando mapa temático: {e}")
            return None

# =============================================================================
# CÁLCULOS FORRAJEROS
# =============================================================================

def calcular_biomasa(ndvi, tipo_pastura):
    """Calcula biomasa basada en NDVI y tipo de pastura"""
    params = obtener_parametros(tipo_pastura)
    
    if ndvi < params['UMBRAL_NDVI_SUELO']:
        return 0  # Suelo desnudo
    
    # Fórmula mejorada de biomasa
    biomasa_base = params['FACTOR_BIOMASA_NDVI'] * ndvi
    
    if ndvi < params['UMBRAL_NDVI_PASTURA']:
        # Vegetación escasa - reducir biomasa progresivamente
        factor_ajuste = (ndvi - params['UMBRAL_NDVI_SUELO']) / (params['UMBRAL_NDVI_PASTURA'] - params['UMBRAL_NDVI_SUELO'])
        biomasa_ajustada = biomasa_base * factor_ajuste * 0.7
    else:
        # Vegetación buena - biomasa completa con ajuste progresivo
        factor_ajuste = min(1.0, (ndvi - params['UMBRAL_NDVI_PASTURA']) / (0.8 - params['UMBRAL_NDVI_PASTURA']))
        biomasa_ajustada = biomasa_base * (0.7 + 0.3 * factor_ajuste)
    
    return max(0, min(params['MS_POR_HA_OPTIMO'], biomasa_ajustada))

def calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio=450, carga_animal=100):
    """Calcula métricas ganaderas realistas"""
    params = obtener_parametros(tipo_pastura)
    metricas = []
    
    for idx, row in gdf_analizado.iterrows():
        biomasa_disponible = row['biomasa_disponible_kg_ms_ha']
        area_ha = row['area_ha']
        
        # 1. CONSUMO INDIVIDUAL (kg MS/animal/día)
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        
        # 2. EQUIVALENTES VACA (EV)
        biomasa_total_disponible = biomasa_disponible * area_ha
        
        if biomasa_total_disponible > 0 and consumo_individual_kg > 0:
            ev_por_dia = biomasa_total_disponible / consumo_individual_kg
            ev_soportable = ev_por_dia * params['TASA_UTILIZACION_RECOMENDADA'] / 100
            ev_soportable = max(0.1, min(50, ev_soportable))
        else:
            ev_soportable = 0.1
        
        # 3. DÍAS DE PERMANENCIA
        if carga_animal > 0:
            consumo_total_diario = carga_animal * consumo_individual_kg
            
            if consumo_total_diario > 0 and biomasa_total_disponible > 0:
                dias_permanencia = biomasa_total_disponible / consumo_total_diario
                # Considerar crecimiento durante el pastoreo
                crecimiento_total = params['CRECIMIENTO_DIARIO'] * area_ha * dias_permanencia * 0.3
                dias_ajustados = (biomasa_total_disponible + crecimiento_total) / consumo_total_diario
                dias_permanencia = min(dias_ajustados, 30)
            else:
                dias_permanencia = 0.1
        else:
            dias_permanencia = 0.1
        
        # EV por hectárea
        ev_ha = ev_soportable / area_ha if area_ha > 0 else 0
        
        metricas.append({
            'ev_soportable': round(ev_soportable, 2),
            'dias_permanencia': max(0.1, round(dias_permanencia, 1)),
            'biomasa_total_kg': round(biomasa_total_disponible, 1),
            'consumo_individual_kg': round(consumo_individual_kg, 1),
            'ev_ha': round(ev_ha, 3)
        })
    
    return metricas

# =============================================================================
# ANÁLISIS PRINCIPAL
# =============================================================================

def ejecutar_analisis_completo(gdf, config):
    """Función principal de análisis forrajero"""
    try:
        st.header("🌱 ANÁLISIS FORRAJERO COMPLETO")
        
        # Información del potrero
        area_total = calcular_superficie(gdf).sum()
        st.success(f"✅ Potrero cargado: {area_total:.1f} ha, {len(gdf)} polígonos")
        
        # PASO 1: Mostrar mapa inicial
        st.subheader("🗺️ MAPA INICIAL DEL POTRERO")
        visualizador = VisualizadorMapas()
        mapa = visualizador.crear_mapa_interactivo(gdf, config['mapa_base'])
        if mapa:
            folium_static(mapa, width=1000, height=500)
        
        # PASO 2: Dividir potrero
        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES")
        with st.spinner("Dividiendo potrero..."):
            gdf_dividido = dividir_potrero(gdf, config['n_divisiones'])
        
        if gdf_dividido is None or len(gdf_dividido) == 0:
            st.error("❌ Error al dividir el potrero")
            return False
            
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # Mostrar mapa dividido
        st.subheader("🗺️ POTRERO DIVIDIDO")
        mapa_dividido = visualizador.crear_mapa_interactivo(gdf_dividido, config['mapa_base'])
        if mapa_dividido:
            folium_static(mapa_dividido, width=1000, height=500)
        
        # PASO 3: Simular datos Sentinel-2
        st.subheader("🛰️ DATOS SENTINEL-2 HARMONIZED")
        with st.spinner("Generando datos de vegetación realistas..."):
            simulador = SimuladorSentinel2()
            resultados = []
            
            for idx, row in gdf_dividido.iterrows():
                centroid = row.geometry.centroid
                area_ha = calcular_superficie(gpd.GeoDataFrame([row], crs=gdf_dividido.crs))
                if hasattr(area_ha, 'iloc'):
                    area_ha = area_ha.iloc[0]
                
                # Simular índices de vegetación
                indices = simulador.simular_indices_vegetacion(
                    row['id_subLote'], 
                    centroid, 
                    config['fecha_imagen'],
                    area_ha
                )
                
                # Calcular biomasa
                biomasa_total = calcular_biomasa(indices['ndvi'], config['tipo_pastura'])
                biomasa_disponible = biomasa_total * 0.6  # 60% de aprovechamiento realista
                
                resultados.append({
                    'id_subLote': row['id_subLote'],
                    'area_ha': area_ha,
                    'ndvi': indices['ndvi'],
                    'evi': indices['evi'],
                    'savi': indices['savi'],
                    'msavi2': indices['msavi2'],
                    'tipo_superficie': indices['tipo_superficie'],
                    'cobertura_vegetal': indices['cobertura_vegetal'],
                    'biomasa_total_kg_ms_ha': biomasa_total,
                    'biomasa_disponible_kg_ms_ha': biomasa_disponible,
                    'crecimiento_diario': obtener_parametros(config['tipo_pastura'])['CRECIMIENTO_DIARIO'],
                    'calidad_datos': indices['calidad_datos']
                })
        
        # Crear GeoDataFrame con resultados
        gdf_analizado = gdf_dividido.copy()
        for col in ['area_ha', 'ndvi', 'evi', 'savi', 'msavi2', 'tipo_superficie', 
                   'cobertura_vegetal', 'biomasa_total_kg_ms_ha', 'biomasa_disponible_kg_ms_ha', 
                   'crecimiento_diario', 'calidad_datos']:
            gdf_analizado[col] = [r[col] for r in resultados]
        
        # PASO 4: Calcular métricas ganaderas
        st.subheader("🐄 CALCULANDO MÉTRICAS GANADERAS")
        with st.spinner("Calculando equivalentes vaca y días de permanencia..."):
            metricas = calcular_metricas_ganaderas(
                gdf_analizado, 
                config['tipo_pastura'], 
                config['peso_promedio'], 
                config['carga_animal']
            )
        
        # Añadir métricas al GeoDataFrame
        for col in ['ev_soportable', 'dias_permanencia', 'biomasa_total_kg', 'consumo_individual_kg', 'ev_ha']:
            gdf_analizado[col] = [m[col] for m in metricas]
        
        # PASO 5: Mostrar resultados completos
        mostrar_resultados_completos(gdf_analizado, config)
        
        st.session_state.analisis_completado = True
        return True
        
    except Exception as e:
        st.error(f"❌ Error en el análisis: {str(e)}")
        import traceback
        st.error(f"Detalle: {traceback.format_exc()}")
        return False

def mostrar_resultados_completos(gdf_analizado, config):
    """Muestra todos los resultados del análisis"""
    st.header("📊 RESULTADOS COMPLETOS DEL ANÁLISIS")
    
    # Métricas principales
    st.subheader("📈 MÉTRICAS PRINCIPALES")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        ndvi_prom = gdf_analizado['ndvi'].mean()
        st.metric("NDVI Promedio", f"{ndvi_prom:.3f}")
    
    with col2:
        biomasa_prom = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
        st.metric("Biomasa Disponible", f"{biomasa_prom:.0f} kg MS/ha")
    
    with col3:
        area_total = gdf_analizado['area_ha'].sum()
        st.metric("Área Total", f"{area_total:.1f} ha")
    
    with col4:
        ev_total = gdf_analizado['ev_soportable'].sum()
        st.metric("Equivalentes Vaca", f"{ev_total:.1f}")
    
    # Mapa temático de NDVI
    st.subheader("🟢 MAPA TEMÁTICO DE NDVI")
    visualizador = VisualizadorMapas()
    mapa_ndvi = visualizador.crear_mapa_tematico_ndvi(gdf_analizado, config['tipo_pastura'])
    if mapa_ndvi:
        st.image(mapa_ndvi, use_container_width=True)
        
        # Botón de descarga del mapa
        st.download_button(
            "📥 Descargar Mapa NDVI",
            mapa_ndvi.getvalue(),
            f"mapa_ndvi_{config['tipo_pastura']}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
            "image/png"
        )
    
    # Mapa interactivo con datos
    st.subheader("🗺️ MAPA INTERACTIVO CON DATOS")
    mapa_interactivo = visualizador.crear_mapa_interactivo(gdf_analizado, config['mapa_base'], mostrar_ndvi=True)
    if mapa_interactivo:
        folium_static(mapa_interactivo, width=1000, height=500)
    
    # Tabla de resultados detallados
    st.subheader("📋 DETALLES POR SUB-LOTE")
    
    columnas_detalle = [
        'id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 'cobertura_vegetal',
        'biomasa_disponible_kg_ms_ha', 'ev_soportable', 'dias_permanencia', 'calidad_datos'
    ]
    
    tabla_detalle = gdf_analizado[columnas_detalle].copy()
    tabla_detalle.columns = [
        'Sub-Lote', 'Área (ha)', 'Tipo Superficie', 'NDVI', 'Cobertura',
        'Biomasa Disp (kg MS/ha)', 'EV', 'Días Permanencia', 'Calidad'
    ]
    
    st.dataframe(tabla_detalle, use_container_width=True)
    
    # Estadísticas detalladas
    with st.expander("📊 ESTADÍSTICAS DETALLADAS"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Distribución de tipos de superficie:**")
            distribucion = gdf_analizado['tipo_superficie'].value_counts()
            for tipo, count in distribucion.items():
                porcentaje = (count / len(gdf_analizado)) * 100
                st.write(f"- {tipo}: {count} sub-lotes ({porcentaje:.1f}%)")
        
        with col2:
            st.write("**Calidad de datos simulados:**")
            calidad = gdf_analizado['calidad_datos'].value_counts()
            for nivel, count in calidad.items():
                porcentaje = (count / len(gdf_analizado)) * 100
                st.write(f"- {nivel}: {count} sub-lotes ({porcentaje:.1f}%)")
    
    # Descarga de resultados
    st.subheader("💾 EXPORTAR RESULTADOS")
    
    # CSV con todos los datos
    csv_completo = gdf_analizado.drop(columns=['geometry']).to_csv(index=False)
    st.download_button(
        "📥 Descargar CSV Completo",
        csv_completo,
        f"resultados_completos_{config['tipo_pastura']}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        "text/csv"
    )
    
    # CSV resumido
    csv_resumido = tabla_detalle.to_csv(index=False)
    st.download_button(
        "📥 Descargar CSV Resumido",
        csv_resumido,
        f"resultados_resumidos_{config['tipo_pastura']}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        "text/csv"
    )

# =============================================================================
# SIDEBAR
# =============================================================================

with st.sidebar:
    st.header("⚙️ Configuración")
    
    st.subheader("🗺️ Mapa Base")
    mapa_base = st.selectbox(
        "Seleccionar mapa base:",
        list(MAPAS_BASE.keys()),
        index=0,  # ESRI World Imagery por defecto
        help="Selecciona la base cartográfica para visualización"
    )
    
    st.subheader("📅 Configuración Temporal")
    fecha_imagen = st.date_input(
        "Fecha de referencia:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now(),
        help="Fecha para la simulación de datos satelitales"
    )
    
    st.subheader("🌿 Tipo de Pastura")
    tipo_pastura = st.selectbox(
        "Seleccionar tipo:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL"],
        help="Parámetros específicos para cada tipo de pastura"
    )
    
    st.subheader("🐄 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal:", 50, 1000, 100)
    
    st.subheader("📐 División del Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", 8, 32, 16)
    
    st.subheader("📤 Cargar Datos")
    uploaded_zip = st.file_uploader(
        "Subir ZIP con shapefile:",
        type=['zip'],
        help="Archivo ZIP que contiene el shapefile del potrero (.shp, .shx, .dbf, .prj)"
    )

# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================

def main():
    """Función principal de la aplicación"""
    
    # Procesar archivo subido
    if uploaded_zip is not None and st.session_state.gdf_cargado is None:
        with st.spinner("Cargando y procesando shapefile..."):
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                        zip_ref.extractall(tmp_dir)
                    
                    # Buscar archivos shapefile
                    shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
                    if shp_files:
                        shp_path = os.path.join(tmp_dir, shp_files[0])
                        gdf_cargado = gpd.read_file(shp_path)
                        
                        # Verificar CRS
                        if gdf_cargado.crs is None:
                            gdf_cargado = gdf_cargado.set_crs('EPSG:4326')
                            st.warning("⚠️ CRS no definido. Asumiendo WGS84 (EPSG:4326)")
                        
                        st.session_state.gdf_cargado = gdf_cargado
                        st.success("✅ Shapefile cargado correctamente")
                    else:
                        st.error("❌ No se encontró archivo .shp en el ZIP")
            except Exception as e:
                st.error(f"❌ Error cargando shapefile: {str(e)}")
    
    # Contenido principal
    if st.session_state.gdf_cargado is not None:
        gdf = st.session_state.gdf_cargado
        
        # Mostrar información del potrero
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
            st.metric("Mapa Base", mapa_base)
        
        # Botón de análisis
        st.markdown("---")
        st.header("🚀 ANÁLISIS FORRAJERO")
        
        if st.button("🎯 EJECUTAR ANÁLISIS COMPLETO", type="primary", use_container_width=True):
            config = {
                'mapa_base': mapa_base,
                'fecha_imagen': fecha_imagen,
                'tipo_pastura': tipo_pastura,
                'peso_promedio': peso_promedio,
                'carga_animal': carga_animal,
                'n_divisiones': n_divisiones
            }
            
            with st.spinner("Realizando análisis forrajero completo..."):
                resultado = ejecutar_analisis_completo(gdf, config)
                
            if resultado:
                st.balloons()
                st.success("🎉 ¡Análisis completado exitosamente!")
    
    else:
        # Pantalla de bienvenida
        st.header("🌱 BIENVENIDO AL ANALIZADOR FORRAJERO")
        
        st.markdown("""
        ### 🚀 CARACTERÍSTICAS PRINCIPALES:
        
        ✅ **Análisis forrajero** completo sin dependencias externas  
        ✅ **Mapas ESRI de alta calidad** (World Imagery, Street Map, Topographic)  
        ✅ **Analisis realista** de datos Sentinel-2 Harmonized  
        ✅ **Cálculo de biomasa** y equivalentes vaca  
        ✅ **Mapas interactivos** y reportes descargables  
        
        ### 📋 PARA COMENZAR:
        
        1. **Configura los parámetros** en la barra lateral ←
        2. **Sube un shapefile** en formato ZIP
        3. **Ejecuta el análisis** forrajero completo
        
        ### 🗺️ MAPAS BASE DISPONIBLES:
        
        - **ESRI World Imagery**: Imágenes satelitales de alta resolución
        - **ESRI World Street Map**: Mapas cartográficos detallados  
        - **ESRI Topographic**: Mapas con relieve y curvas de nivel
        - **OpenStreetMap**: Datos cartográficos abiertos
        - **Google Satellite**: Imágenes satelitales de Google
        
        ### 🌿 DATOS:
        
        Los datos Sentinel-2 se simulan basándose en:
        - Patrones espaciales realistas de vegetación
        - Variación estacional y temporal
        - Parámetros específicos por tipo de pastura
        - Índices de vegetación consistentes (NDVI, EVI, SAVI)
        """)
        
        # Mostrar ejemplo de mapas base
        st.subheader("🗺️ EJEMPLO DE MAPAS BASE")
        col1, col2 = st.columns(2)
        
        with col1:
            st.info("**ESRI World Imagery**")
            st.image("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/0/0/0", 
                    use_container_width=True)
        
        with col2:
            st.info("**ESRI World Street Map**")
            st.image("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/0/0/0",
                    use_container_width=True)

if __name__ == "__main__":
    main()
