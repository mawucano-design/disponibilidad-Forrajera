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
# CONFIGURACIÓN INICIAL
# =============================================================================

# Configurar página de Streamlit
st.set_page_config(
    page_title="🌱 Analizador Forrajero GitHub",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("🌱 ANALIZADOR FORRAJERO - MODO GITHUB")
st.markdown("---")

# Configuración para shapefiles
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Inicializar variables de session state
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'analisis_completado' not in st.session_state:
    st.session_state.analisis_completado = False

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
# SIMULACIÓN DE DATOS SATELITALES
# =============================================================================

class SimuladorSatelital:
    """Simula datos satelitales realistas para GitHub"""
    
    def __init__(self):
        self.patrones_vegetacion = {
            # Patrones basados en casos reales
            'SUELO_DESNUDO': {'ndvi_range': (0.05, 0.20), 'frecuencia': 0.1},
            'VEGETACION_ESCASA': {'ndvi_range': (0.20, 0.40), 'frecuencia': 0.3},
            'VEGETACION_MODERADA': {'ndvi_range': (0.40, 0.60), 'frecuencia': 0.4},
            'VEGETACION_DENSA': {'ndvi_range': (0.60, 0.85), 'frecuencia': 0.2}
        }
    
    def simular_indices_vegetacion(self, id_subLote, centroid, fecha):
        """Simula índices de vegetación realistas"""
        try:
            # Variación basada en posición (para patrones espaciales)
            x_norm = (centroid.x * 1000) % 100 / 100
            y_norm = (centroid.y * 1000) % 100 / 100
            
            # Variación estacional
            dia_del_año = fecha.timetuple().tm_yday
            factor_estacional = 0.3 * math.sin(2 * math.pi * dia_del_año / 365 - math.pi/2) + 0.7
            
            # Determinar tipo de vegetación basado en posición
            valor_base = (x_norm + y_norm) / 2
            
            if valor_base < 0.1:
                tipo = 'SUELO_DESNUDO'
            elif valor_base < 0.4:
                tipo = 'VEGETACION_ESCASA'
            elif valor_base < 0.8:
                tipo = 'VEGETACION_MODERADA'
            else:
                tipo = 'VEGETACION_DENSA'
            
            # Generar NDVI según el tipo
            rango = self.patrones_vegetacion[tipo]['ndvi_range']
            ndvi_base = rango[0] + (rango[1] - rango[0]) * (x_norm * y_norm)
            ndvi = ndvi_base * factor_estacional
            
            # Añadir variabilidad natural
            ndvi += np.random.normal(0, 0.05)
            ndvi = max(0.05, min(0.85, ndvi))
            
            # Calcular otros índices de forma consistente
            evi = ndvi * 1.1 + np.random.normal(0, 0.02)
            savi = ndvi * 1.05 + np.random.normal(0, 0.02)
            msavi2 = ndvi * 1.02 + np.random.normal(0, 0.01)
            
            # Índices de suelo (inversamente relacionados con vegetación)
            bsi = 0.3 - (ndvi * 0.4) + np.random.normal(0, 0.05)
            ndbi = 0.2 - (ndvi * 0.3) + np.random.normal(0, 0.03)
            
            return {
                'ndvi': ndvi,
                'evi': max(0.1, min(1.0, evi)),
                'savi': max(0.1, min(1.0, savi)),
                'msavi2': max(0.1, min(1.0, msavi2)),
                'bsi': max(-1.0, min(1.0, bsi)),
                'ndbi': max(-1.0, min(1.0, ndbi)),
                'tipo_superficie': tipo,
                'cobertura_vegetal': min(0.95, max(0.05, ndvi * 1.2))
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
                'cobertura_vegetal': 0.6
            }

# =============================================================================
# CÁLCULOS FORRAJEROS
# =============================================================================

def calcular_biomasa(ndvi, tipo_pastura):
    """Calcula biomasa basada en NDVI y tipo de pastura"""
    params = obtener_parametros_forrajeros(tipo_pastura)
    
    # Fórmula mejorada de biomasa
    if ndvi < params['UMBRAL_NDVI_SUELO']:
        return 0  # Suelo desnudo
    
    # Biomasa base según NDVI
    biomasa_base = params['FACTOR_BIOMASA_NDVI'] * ndvi
    
    # Ajustar según tipo de pastura
    if ndvi < params['UMBRAL_NDVI_PASTURA']:
        # Vegetación escasa - reducir biomasa
        factor_ajuste = (ndvi - params['UMBRAL_NDVI_SUELO']) / (params['UMBRAL_NDVI_PASTURA'] - params['UMBRAL_NDVI_SUELO'])
        biomasa_ajustada = biomasa_base * factor_ajuste * 0.7
    else:
        # Vegetación buena - biomasa completa
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
        
        # Consumo individual
        consumo_individual_kg = peso_promedio * params['CONSUMO_PORCENTAJE_PESO']
        
        # Biomasa total disponible
        biomasa_total = biomasa_disponible * area_ha
        
        # Equivalentes vaca
        if biomasa_total > 0 and consumo_individual_kg > 0:
            ev_soportable = (biomasa_total * params['TASA_UTILIZACION_RECOMENDADA']) / (consumo_individual_kg * 100)
            ev_soportable = max(0.1, ev_soportable)
        else:
            ev_soportable = 0.1
        
        # Días de permanencia
        if carga_animal > 0 and consumo_individual_kg > 0:
            consumo_total_diario = carga_animal * consumo_individual_kg
            if consumo_total_diario > 0:
                dias_permanencia = biomasa_total / consumo_total_diario
                dias_permanencia = max(0.1, min(30, dias_permanencia))
            else:
                dias_permanencia = 0.1
        else:
            dias_permanencia = 0.1
        
        # EV por hectárea
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
# VISUALIZACIÓN DE MAPAS
# =============================================================================

class VisualizadorMapas:
    """Clase para crear mapas interactivos"""
    
    def __init__(self):
        self.simulador = SimuladorSatelital()
    
    def crear_mapa_base(self, gdf, tipo_mapa="google_satellite"):
        """Crea mapa base interactivo"""
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
            
            # Añadir capas base
            if tipo_mapa == "google_satellite":
                folium.TileLayer(
                    tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                    attr='Google Satellite',
                    name='Google Satellite',
                    overlay=False
                ).add_to(m)
                
            elif tipo_mapa == "world_imagery":
                folium.TileLayer(
                    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                    attr='Esri World Imagery',
                    name='World Imagery',
                    overlay=False
                ).add_to(m)
            
            # Capa OpenStreetMap por defecto
            folium.TileLayer(
                tiles='OpenStreetMap',
                name='OpenStreetMap',
                overlay=False
            ).add_to(m)
            
            # Añadir polígonos
            self._añadir_poligonos_mapa(m, gdf)
            
            # Ajustar vista
            m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
            
            # Control de capas
            folium.LayerControl().add_to(m)
            
            return m
            
        except Exception as e:
            st.error(f"Error creando mapa: {e}")
            return None
    
    def _añadir_poligonos_mapa(self, m, gdf):
        """Añade polígonos al mapa con estilo"""
        try:
            for idx, row in gdf.iterrows():
                # Determinar color basado en datos disponibles
                if 'ndvi' in gdf.columns:
                    ndvi = row['ndvi']
                    if ndvi < 0.2:
                        color = '#d73027'  # Rojo
                    elif ndvi < 0.4:
                        color = '#fdae61'  # Naranja
                    elif ndvi < 0.6:
                        color = '#a6d96a'  # Verde claro
                    else:
                        color = '#1a9850'  # Verde oscuro
                else:
                    color = '#3388ff'  # Azul por defecto
                
                # Crear tooltip
                tooltip_text = f"Sub-lote: {row.get('id_subLote', idx+1)}"
                if 'area_ha' in gdf.columns:
                    tooltip_text += f"<br>Área: {row['area_ha']:.2f} ha"
                if 'ndvi' in gdf.columns:
                    tooltip_text += f"<br>NDVI: {row['ndvi']:.3f}"
                
                # Añadir polígono
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
                
                # Añadir número de sub-lote
                centroid = row.geometry.centroid
                folium.Marker(
                    [centroid.y, centroid.x],
                    icon=folium.DivIcon(
                        html=f'<div style="font-weight: bold; color: black; background: white; padding: 2px; border-radius: 3px; border: 1px solid black;">{row.get("id_subLote", idx+1)}</div>'
                    )
                ).add_to(m)
                
        except Exception as e:
            st.error(f"Error añadiendo polígonos: {e}")
    
    def crear_mapa_ndvi(self, gdf_analizado, tipo_pastura):
        """Crea mapa temático de NDVI"""
        try:
            fig, ax = plt.subplots(1, 1, figsize=(15, 10))
            
            # Crear colormap para NDVI
            cmap = LinearSegmentedColormap.from_list('ndvi_cmap', ['#d73027', '#fee08b', '#a6d96a', '#1a9850'])
            
            # Plotear cada polígono con color según NDVI
            for idx, row in gdf_analizado.iterrows():
                ndvi = row['ndvi']
                color = cmap(ndvi)
                
                gdf_analizado.iloc[[idx]].plot(
                    ax=ax,
                    color=color,
                    edgecolor='black',
                    linewidth=1
                )
                
                # Añadir etiqueta
                centroid = row.geometry.centroid
                ax.annotate(
                    f"S{row['id_subLote']}\n{ndvi:.2f}",
                    (centroid.x, centroid.y),
                    xytext=(5, 5),
                    textcoords="offset points",
                    fontsize=8,
                    color='black',
                    weight='bold',
                    bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8)
                )
            
            ax.set_title(f'🌿 MAPA DE NDVI - {tipo_pastura}', fontsize=16, fontweight='bold', pad=20)
            ax.set_xlabel('Longitud')
            ax.set_ylabel('Latitud')
            ax.grid(True, alpha=0.3)
            
            # Añadir barra de color
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=0, vmax=1))
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
            cbar.set_label('NDVI', fontsize=12, fontweight='bold')
            
            plt.tight_layout()
            
            # Convertir a imagen para Streamlit
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            buf.seek(0)
            plt.close()
            
            return buf
            
        except Exception as e:
            st.error(f"Error creando mapa NDVI: {e}")
            return None

# =============================================================================
# ANÁLISIS PRINCIPAL
# =============================================================================

def analisis_forrajero_completo(gdf, config):
    """Función principal de análisis forrajero"""
    try:
        st.header("🌱 ANÁLISIS FORRAJERO COMPLETO")
        
        # Mostrar información del potrero
        area_total = calcular_superficie(gdf).sum()
        st.success(f"✅ Potrero cargado: {area_total:.1f} ha, {len(gdf)} polígonos")
        
        # PASO 1: Mostrar mapa inicial
        st.subheader("🗺️ MAPA INICIAL DEL POTRERO")
        visualizador = VisualizadorMapas()
        mapa = visualizador.crear_mapa_base(gdf, config['mapa_base'])
        if mapa:
            folium_static(mapa, width=1000, height=500)
        
        # PASO 2: Dividir potrero
        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES")
        with st.spinner("Dividiendo potrero..."):
            gdf_dividido = dividir_potrero_en_subLotes(gdf, config['n_divisiones'])
        
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # Mostrar mapa dividido
        st.subheader("🗺️ POTRERO DIVIDIDO")
        mapa_dividido = visualizador.crear_mapa_base(gdf_dividido, config['mapa_base'])
        if mapa_dividido:
            folium_static(mapa_dividido, width=1000, height=500)
        
        # PASO 3: Simular datos satelitales
        st.subheader("🛰️ SIMULANDO DATOS SATELITALES")
        with st.spinner("Generando datos de vegetación..."):
            simulador = SimuladorSatelital()
            resultados = []
            
            for idx, row in gdf_dividido.iterrows():
                centroid = row.geometry.centroid
                indices = simulador.simular_indices_vegetacion(
                    row['id_subLote'], 
                    centroid, 
                    config['fecha_imagen']
                )
                
                # Calcular biomasa
                biomasa_total = calcular_biomasa(indices['ndvi'], config['tipo_pastura'])
                biomasa_disponible = biomasa_total * 0.6  # 60% de aprovechamiento
                
                resultados.append({
                    'id_subLote': row['id_subLote'],
                    'area_ha': calcular_superficie(gpd.GeoDataFrame([row], crs=gdf_dividido.crs))[0],
                    'ndvi': indices['ndvi'],
                    'evi': indices['evi'],
                    'savi': indices['savi'],
                    'tipo_superficie': indices['tipo_superficie'],
                    'cobertura_vegetal': indices['cobertura_vegetal'],
                    'biomasa_total_kg_ms_ha': biomasa_total,
                    'biomasa_disponible_kg_ms_ha': biomasa_disponible,
                    'crecimiento_diario': obtener_parametros_forrajeros(config['tipo_pastura'])['CRECIMIENTO_DIARIO']
                })
        
        # Crear GeoDataFrame con resultados
        gdf_analizado = gdf_dividido.copy()
        for col in ['area_ha', 'ndvi', 'evi', 'savi', 'tipo_superficie', 'cobertura_vegetal', 
                   'biomasa_total_kg_ms_ha', 'biomasa_disponible_kg_ms_ha', 'crecimiento_diario']:
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
        
        # Añadir métricas al GeoDataFrame
        for col in ['ev_soportable', 'dias_permanencia', 'biomasa_total_kg', 'consumo_individual_kg', 'ev_ha']:
            gdf_analizado[col] = [m[col] for m in metricas]
        
        # PASO 5: Mostrar resultados
        mostrar_resultados_completos(gdf_analizado, config)
        
        st.session_state.analisis_completado = True
        return True
        
    except Exception as e:
        st.error(f"❌ Error en análisis: {str(e)}")
        import traceback
        st.error(f"Detalle: {traceback.format_exc()}")
        return False

def mostrar_resultados_completos(gdf_analizado, config):
    """Muestra todos los resultados del análisis"""
    st.header("📊 RESULTADOS DEL ANÁLISIS")
    
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
    
    # Mapa de NDVI
    st.subheader("🟢 MAPA DE NDVI")
    visualizador = VisualizadorMapas()
    mapa_ndvi = visualizador.crear_mapa_ndvi(gdf_analizado, config['tipo_pastura'])
    if mapa_ndvi:
        st.image(mapa_ndvi, use_container_width=True)
        
        # Botón de descarga
        st.download_button(
            "📥 Descargar Mapa NDVI",
            mapa_ndvi.getvalue(),
            f"mapa_ndvi_{config['tipo_pastura']}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
            "image/png"
        )
    
    # Tabla de resultados detallados
    st.subheader("📋 DETALLES POR SUB-LOTE")
    
    columnas_detalle = [
        'id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 
        'biomasa_disponible_kg_ms_ha', 'ev_soportable', 'dias_permanencia'
    ]
    
    tabla_detalle = gdf_analizado[columnas_detalle].copy()
    tabla_detalle.columns = [
        'Sub-Lote', 'Área (ha)', 'Tipo Superficie', 'NDVI',
        'Biomasa Disp (kg MS/ha)', 'EV', 'Días Permanencia'
    ]
    
    st.dataframe(tabla_detalle, use_container_width=True)
    
    # Descarga de resultados
    st.subheader("💾 EXPORTAR RESULTADOS")
    
    # CSV
    csv = tabla_detalle.to_csv(index=False)
    st.download_button(
        "📥 Descargar CSV",
        csv,
        f"resultados_forrajeros_{config['tipo_pastura']}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        "text/csv"
    )
    
    # Información adicional
    with st.expander("📊 ESTADÍSTICAS DETALLADAS"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Distribución de tipos de superficie:**")
            distribucion = gdf_analizado['tipo_superficie'].value_counts()
            for tipo, count in distribucion.items():
                porcentaje = (count / len(gdf_analizado)) * 100
                st.write(f"- {tipo}: {count} sub-lotes ({porcentaje:.1f}%)")
        
        with col2:
            st.write("**Rangos de NDVI:**")
            st.write(f"- Mínimo: {gdf_analizado['ndvi'].min():.3f}")
            st.write(f"- Máximo: {gdf_analizado['ndvi'].max():.3f}")
            st.write(f"- Promedio: {gdf_analizado['ndvi'].mean():.3f}")

# =============================================================================
# SIDEBAR - CONFIGURACIÓN
# =============================================================================

with st.sidebar:
    st.header("⚙️ Configuración")
    
    st.subheader("🗺️ Mapa Base")
    mapa_base = st.selectbox(
        "Tipo de mapa:",
        ["google_satellite", "world_imagery", "openstreetmap"],
        help="Selecciona la base cartográfica"
    )
    
    st.subheader("📅 Configuración Temporal")
    fecha_imagen = st.date_input(
        "Fecha de análisis:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now()
    )
    
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
        type=['zip'],
        help="Archivo ZIP que contiene el shapefile del potrero"
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
        # Mostrar información del potrero cargado
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
            st.metric("Sub-lotes", n_divisiones)
        
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
                resultado = analisis_forrajero_completo(gdf, config)
                
            if resultado:
                st.balloons()
                st.success("🎉 ¡Análisis completado exitosamente!")
    
    else:
        # Pantalla de bienvenida
        st.header("🌱 BIENVENIDO AL ANALIZADOR FORRAJERO")
        
        st.markdown("""
        ### 📋 INSTRUCCIONES DE USO:
        
        1. **Configura los parámetros** en la barra lateral ←
        2. **Sube un shapefile** en formato ZIP
        3. **Ejecuta el análisis** forrajero completo
        4. **Explora los resultados** y mapas interactivos
        
        ### 🛠️ CARACTERÍSTICAS:
        
        ✅ **Análisis forrajero** completo  
        ✅ **Mapas interactivos** con Google Satellite  
        ✅ **Simulación realista** de datos satelitales  
        ✅ **Cálculo de biomasa** y equivalentes vaca  
        ✅ **Recomendaciones** de manejo ganadero  
        
        ### 📁 FORMATO REQUERIDO:
        
        - **Archivo:** Formato ZIP que contenga shapefile (.shp, .shx, .dbf, .prj)
        - **Sistema de coordenadas:** Preferiblemente WGS84 (EPSG:4326)
        - **Tamaño máximo:** 50 MB
        """)
        
        # Ejemplo de datos
        with st.expander("🧪 PROBAR CON DATOS DE EJEMPLO"):
            st.info("""
            **Para probar sin datos:**
            - Descarga shapefiles de ejemplo de [Natural Earth](https://www.naturalearthdata.com/)
            - O crea polígonos simples en QGIS/ArcGIS
            - Cualquier shapefile válido funcionará
            """)

if __name__ == "__main__":
    main()
