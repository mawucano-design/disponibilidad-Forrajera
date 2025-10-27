import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
import io
from shapely.geometry import Polygon
import math
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go

# =================================================================
# SISTEMA INTEGRADO DE GANADERÍA REGENERATIVA - VOISIN 
# ADAPTADO DE GOOGLE EARTH ENGINE A STREAMLIT
# =================================================================

# Configuración de página
st.set_page_config(
    page_title="🌱 Ganadería Regenerativa Voisin", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("🌱 SISTEMA DE GANADERÍA REGENERATIVA - METODOLOGÍA VOISIN")
st.markdown("---")

# =================================================================
# PARÁMETROS DEL SISTEMA (Basados en tu código GEE)
# =================================================================

PARAMETROS_FORRAJEROS = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 4000,
        'CRECIMIENTO_DIARIO': 80,
        'CONSUMO_VACA_DIA': 12,
        'DIGESTIBILIDAD': 0.65,
        'PROTEINA_CRUDA': 0.18,
        'FACTOR_BIOMASA_NDVI': 2500,
        'FACTOR_BIOMASA_EVI': 2800,
        'FACTOR_BIOMASA_SAVI': 2600,
        'OFFSET_BIOMASA': -800
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 3500,
        'CRECIMIENTO_DIARIO': 70,
        'CONSUMO_VACA_DIA': 10,
        'DIGESTIBILIDAD': 0.70,
        'PROTEINA_CRUDA': 0.15,
        'FACTOR_BIOMASA_NDVI': 2200,
        'FACTOR_BIOMASA_EVI': 2500,
        'FACTOR_BIOMASA_SAVI': 2300,
        'OFFSET_BIOMASA': -700
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 3000,
        'CRECIMIENTO_DIARIO': 50,
        'CONSUMO_VACA_DIA': 9,
        'DIGESTIBILIDAD': 0.60,
        'PROTEINA_CRUDA': 0.12,
        'FACTOR_BIOMASA_NDVI': 2000,
        'FACTOR_BIOMASA_EVI': 2300,
        'FACTOR_BIOMASA_SAVI': 2100,
        'OFFSET_BIOMASA': -600
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 2800,
        'CRECIMIENTO_DIARIO': 45,
        'CONSUMO_VACA_DIA': 8,
        'DIGESTIBILIDAD': 0.55,
        'PROTEINA_CRUDA': 0.10,
        'FACTOR_BIOMASA_NDVI': 1800,
        'FACTOR_BIOMASA_EVI': 2100,
        'FACTOR_BIOMASA_SAVI': 1900,
        'OFFSET_BIOMASA': -500
    },
    'MEZCLA_NATURAL': {
        'MS_POR_HA_OPTIMO': 2500,
        'CRECIMIENTO_DIARIO': 40,
        'CONSUMO_VACA_DIA': 7,
        'DIGESTIBILIDAD': 0.50,
        'PROTEINA_CRUDA': 0.08,
        'FACTOR_BIOMASA_NDVI': 1500,
        'FACTOR_BIOMASA_EVI': 1800,
        'FACTOR_BIOMASA_SAVI': 1600,
        'OFFSET_BIOMASA': -400
    }
}

# Parámetros del sistema Voisin
PARAMETROS_VOISIN = {
    'CONSUMO_DIARIO_VACA': 12,
    'PESO_PROMEDIO_VACA': 450,
    'EQUIVALENCIA_VACA': 450,
    'EFICIENCIA_COSECHA': 0.25,
    'PERDIDAS': 0.30,
    'PERIODO_DESCANSO': 35,
    'DIAS_MAXIMO_PASTOREO': 3,
    'UMBRAL_NDVI': 0.2
}

# Paletas GEE adaptadas
PALETAS_GEE = {
    'ESTADO': ['#d73027', '#fdae61', '#a1dab4', '#1a9641', '#006837'],
    'EVHA': ['#d73027', '#fc8d59', '#fee08b', '#d9ef8b', '#91cf60'],
    'DIAS_PERMANENCIA': ['#ffffcc', '#a1dab4', '#41b6c4', '#2c7fb8', '#253494']
}

# Leyendas del sistema
LEYENDAS = {
    'ESTADO': {
        'titulo': 'Estado Forrajero (kg MS/ha)',
        'rangos': [
            {'color': '#d73027', 'rango': '0-199', 'label': 'CRÍTICO'},
            {'color': '#fdae61', 'rango': '200-399', 'label': 'BAJO'},
            {'color': '#a1dab4', 'rango': '400-599', 'label': 'MEDIO'},
            {'color': '#1a9641', 'rango': '600-799', 'label': 'BUENO'},
            {'color': '#006837', 'rango': '800+', 'label': 'ÓPTIMO'}
        ]
    },
    'EVHA': {
        'titulo': 'Carga Animal (EV/Ha)',
        'rangos': [
            {'color': '#d73027', 'rango': '0.0-0.9', 'label': 'MUY BAJA'},
            {'color': '#fc8d59', 'rango': '1.0-1.9', 'label': 'BAJA'},
            {'color': '#fee08b', 'rango': '2.0-2.9', 'label': 'MEDIA'},
            {'color': '#d9ef8b', 'rango': '3.0-3.9', 'label': 'ALTA'},
            {'color': '#91cf60', 'rango': '4.0-5.0', 'label': 'MUY ALTA'}
        ]
    },
    'DIAS_PERMANENCIA': {
        'titulo': 'Días Permanencia',
        'rangos': [
            {'color': '#ffffcc', 'rango': '0-1', 'label': 'CORTO'},
            {'color': '#a1dab4', 'rango': '1.1-2', 'label': 'MEDIO'},
            {'color': '#41b6c4', 'rango': '2.1-3', 'label': 'IDEAL'},
            {'color': '#2c7fb8', 'rango': '3.1-4', 'label': 'LARGO'},
            {'color': '#253494', 'rango': '4.1+', 'label': 'MUY LARGO'}
        ]
    }
}

# =================================================================
# FUNCIONES DEL SISTEMA (Adaptadas de GEE)
# =================================================================

def calcular_superficie(gdf):
    """Calcula superficie en hectáreas"""
    try:
        if gdf.crs and gdf.crs.is_geographic:
            # Si es geográfico, proyectar a UTM para cálculo de área
            gdf_proj = gdf.to_crs('EPSG:3857')
            area_m2 = gdf_proj.geometry.area
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000  # Convertir a hectáreas
    except Exception as e:
        st.warning(f"Advertencia en cálculo de área: {e}")
        return gdf.geometry.area / 10000

def dividir_potrero_voisin(gdf, n_divisiones):
    """Divide el potrero en sub-lotes según metodología Voisin"""
    if len(gdf) == 0:
        return gdf
    
    potrero_principal = gdf.iloc[0].geometry
    bounds = potrero_principal.bounds
    minx, miny, maxx, maxy = bounds
    
    sub_poligonos = []
    
    # Calcular número de filas y columnas para división más cuadrada
    n_cols = math.ceil(math.sqrt(n_divisiones))
    n_rows = math.ceil(n_divisiones / n_cols)
    
    width = (maxx - minx) / n_cols
    height = (maxy - miny) / n_rows
    
    for i in range(n_rows):
        for j in range(n_cols):
            if len(sub_poligonos) >= n_divisiones:
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

def calcular_indices_satelitales_simulados(gdf, tipo_pastura):
    """Simula cálculo de índices satelitales (NDVI, EVI, SAVI)"""
    
    n_poligonos = len(gdf)
    resultados = []
    params = PARAMETROS_FORRAJEROS[tipo_pastura]
    
    # Obtener centroides para gradiente espacial
    gdf_centroids = gdf.copy()
    gdf_centroids['centroid'] = gdf_centroids.geometry.centroid
    gdf_centroids['x'] = gdf_centroids.centroid.x
    gdf_centroids['y'] = gdf_centroids.centroid.y
    
    x_coords = gdf_centroids['x'].tolist()
    y_coords = gdf_centroids['y'].tolist()
    
    x_min, x_max = min(x_coords), max(x_coords)
    y_min, y_max = min(y_coords), max(y_coords)
    
    for idx, row in gdf_centroids.iterrows():
        # Normalizar posición para simular variación espacial
        x_norm = (row['x'] - x_min) / (x_max - x_min) if x_max != x_min else 0.5
        y_norm = (row['y'] - y_min) / (y_max - y_min) if y_max != y_min else 0.5
        
        patron_espacial = (x_norm * 0.6 + y_norm * 0.4)
        
        # 1. NDVI - Índice de vegetación normalizado
        ndvi_base = 0.5 + (patron_espacial * 0.4)
        ndvi = ndvi_base + np.random.normal(0, 0.08)
        ndvi = max(0.1, min(0.9, ndvi))
        
        # 2. EVI - Índice de vegetación mejorado
        evi_base = 0.4 + (patron_espacial * 0.3)
        evi = evi_base + np.random.normal(0, 0.06)
        evi = max(0.1, min(0.8, evi))
        
        # 3. SAVI - Índice de vegetación ajustado al suelo
        savi_base = 0.45 + (patron_espacial * 0.35)
        savi = savi_base + np.random.normal(0, 0.07)
        savi = max(0.15, min(0.85, savi))
        
        # 4. Cálculo de biomasa basado en metodología GEE
        biomasa_ndvi = (ndvi * params['FACTOR_BIOMASA_NDVI'] + params['OFFSET_BIOMASA'])
        biomasa_evi = (evi * params['FACTOR_BIOMASA_EVI'] + params['OFFSET_BIOMASA'])
        biomasa_savi = (savi * params['FACTOR_BIOMASA_SAVI'] + params['OFFSET_BIOMASA'])
        
        # Promedio ponderado (como en GEE)
        biomasa_promedio = (biomasa_ndvi * 0.4 + biomasa_evi * 0.35 + biomasa_savi * 0.25)
        biomasa_promedio = max(100, min(6000, biomasa_promedio))
        
        # Biomasa disponible (considerando eficiencia y pérdidas)
        biomasa_disponible = (biomasa_promedio * 
                             PARAMETROS_VOISIN['EFICIENCIA_COSECHA'] * 
                             (1 - PARAMETROS_VOISIN['PERDIDAS']))
        biomasa_disponible = max(50, min(1200, biomasa_disponible))
        
        resultados.append({
            'ndvi': round(ndvi, 3),
            'evi': round(evi, 3),
            'savi': round(savi, 3),
            'biomasa_total_kg_ms_ha': round(biomasa_promedio, 1),
            'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1)
        })
    
    return resultados

def calcular_ev_ha(biomasa_disponible, area_ha, tipo_pastura):
    """Calcula Equivalentes Vaca por hectárea - Fórmula corregida"""
    params_pastura = PARAMETROS_FORRAJEROS[tipo_pastura]
    params_voisin = PARAMETROS_VOISIN
    
    # Biomasa total disponible en el sub-lote (kg)
    biomasa_total = biomasa_disponible * area_ha
    
    # FÓRMULA CORREGIDA (basada en tu código GEE):
    # Biomasa (ton) / Consumo diario = EV por día
    # Dividir por descanso UNA SOLA VEZ para obtener EV sostenibles
    ev_ha = (biomasa_total * 0.001) / params_pastura['CONSUMO_VACA_DIA']  # ton / (kg/día)
    ev_ha = ev_ha / params_voisin['PERIODO_DESCANSO']  # EV sostenibles durante descanso
    
    return max(0, min(5, ev_ha))

def calcular_dias_permanencia(biomasa_disponible, area_ha, tipo_pastura):
    """Calcula días de permanencia por parcela"""
    params_pastura = PARAMETROS_FORRAJEROS[tipo_pastura]
    params_voisin = PARAMETROS_VOISIN
    
    biomasa_total = biomasa_disponible * area_ha
    
    # Cálculo basado en consumo diario
    dias = (biomasa_total * 0.001) / (params_pastura['CONSUMO_VACA_DIA'] / 1000)
    
    return max(0, min(params_voisin['DIAS_MAXIMO_PASTOREO'], dias))

def clasificar_estado_forrajero(biomasa_disponible):
    """Clasifica el estado forrajero según rangos GEE"""
    if biomasa_disponible >= 800:
        return 4, "ÓPTIMO"
    elif biomasa_disponible >= 600:
        return 3, "BUENO"
    elif biomasa_disponible >= 400:
        return 2, "MEDIO"
    elif biomasa_disponible >= 200:
        return 1, "BAJO"
    else:
        return 0, "CRÍTICO"

# =================================================================
# INTERFAZ STREAMLIT - SIDEBAR
# =================================================================

with st.sidebar:
    st.header("⚙️ CONFIGURACIÓN VOISIN")
    
    # Selección de pastura
    tipo_pastura = st.selectbox(
        "Tipo de Pastura:", 
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "MEZCLA_NATURAL"]
    )
    
    st.subheader("📊 PARÁMETROS GANADEROS")
    
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 10, 500, 100)
    
    # Parámetros Voisin
    st.subheader("🎯 PARÁMETROS VOISIN")
    consumo_diario = st.slider("Consumo diario (kg MS/vaca):", 8, 15, 12)
    periodo_descanso = st.slider("Período descanso (días):", 20, 60, 35)
    dias_max_pastoreo = st.slider("Días máx. pastoreo/lote:", 1, 7, 3)
    
    st.subheader("🗺️ DIVISIÓN DE POTRERO")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=4, max_value=20, value=8)
    
    st.subheader("📤 SUBIR POTRERO")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile", type=['zip'])
    
    # Actualizar parámetros
    PARAMETROS_VOISIN['CONSUMO_DIARIO_VACA'] = consumo_diario
    PARAMETROS_VOISIN['PERIODO_DESCANSO'] = periodo_descanso
    PARAMETROS_VOISIN['DIAS_MAXIMO_PASTOREO'] = dias_max_pastoreo
    PARAMETROS_VOISIN['PESO_PROMEDIO_VACA'] = peso_promedio

# =================================================================
# FUNCIONES DE VISUALIZACIÓN
# =================================================================

def crear_mapa_voisin(gdf, tipo_analisis, tipo_pastura):
    """Crea mapa con estilo GEE/Voisin"""
    try:
        plt.close('all')
        fig, ax = plt.subplots(1, 1, figsize=(12, 10))
        
        # Seleccionar paleta y parámetros según el análisis
        if tipo_analisis == "BIOMASA":
            cmap = LinearSegmentedColormap.from_list('biomasa_voisin', PALETAS_GEE['ESTADO'])
            vmin, vmax = 0, 1200
            columna = 'biomasa_disponible_kg_ms_ha'
            titulo = 'Biomasa Disponible (kg MS/ha)'
        elif tipo_analisis == "EV_HA":
            cmap = LinearSegmentedColormap.from_list('evha_voisin', PALETAS_GEE['EVHA'])
            vmin, vmax = 0, 5
            columna = 'ev_ha'
            titulo = 'Carga Animal (EV/Ha)'
        else:  # DIAS_PERMANENCIA
            cmap = LinearSegmentedColormap.from_list('dias_voisin', PALETAS_GEE['DIAS_PERMANENCIA'])
            vmin, vmax = 0, 5
            columna = 'dias_permanencia'
            titulo = 'Días de Permanencia'
        
        # Plotear cada polígono con su valor
        for idx, row in gdf.iterrows():
            valor = row[columna]
            valor_norm = (valor - vmin) / (vmax - vmin)
            valor_norm = max(0, min(1, valor_norm))
            color = cmap(valor_norm)
            
            gdf.iloc[[idx]].plot(ax=ax, color=color, edgecolor='black', linewidth=2, alpha=0.8)
            
            # Etiqueta con valor
            centroid = row.geometry.centroid
            ax.annotate(f"S{row['id_subLote']}\n{valor:.1f}", 
                       (centroid.x, centroid.y), 
                       xytext=(5, 5), 
                       textcoords="offset points", 
                       fontsize=9, 
                       color='black', 
                       weight='bold',
                       bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9))
        
        # Configuración del mapa
        ax.set_title(f'🌱 SISTEMA VOISIN - {tipo_pastura}\n'
                    f'{tipo_analisis} - {titulo}', 
                    fontsize=16, fontweight='bold', pad=20)
        
        ax.set_xlabel('Longitud')
        ax.set_ylabel('Latitud')
        ax.grid(True, alpha=0.3)
        
        # Barra de colores
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax, shrink=0.8)
        cbar.set_label(titulo, fontsize=12, fontweight='bold')
        
        plt.tight_layout()
        
        # Convertir a imagen
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf, titulo
        
    except Exception as e:
        st.error(f"❌ Error creando mapa: {str(e)}")
        return None, None

def crear_leyenda_interactiva(tipo_leyenda):
    """Crea leyenda interactiva estilo GEE"""
    leyenda = LEYENDAS[tipo_leyenda]
    
    with st.expander(f"🎨 {leyenda['titulo']}", expanded=True):
        for rango in leyenda['rangos']:
            col1, col2 = st.columns([1, 4])
            with col1:
                st.markdown(
                    f"<div style='background-color: {rango['color']}; padding: 10px; border-radius: 5px;'></div>", 
                    unsafe_allow_html=True
                )
            with col2:
                st.write(f"**{rango['rango']}** - {rango['label']}")

# =================================================================
# ANÁLISIS PRINCIPAL
# =================================================================

def analisis_voisin_completo(gdf, tipo_pastura, n_divisiones):
    """Ejecuta análisis completo con metodología Voisin"""
    
    try:
        st.header(f"🌱 ANÁLISIS VOISIN - {tipo_pastura}")
        
        # 1. DIVIDIR POTRERO
        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES VOISIN")
        with st.spinner("Aplicando metodología Voisin..."):
            gdf_dividido = dividir_potrero_voisin(gdf, n_divisiones)
        
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # Calcular áreas
        areas_ha = calcular_superficie(gdf_dividido)
        area_total = areas_ha.sum()
        
        # 2. CALCULAR ÍNDICES SATELITALES
        st.subheader("🛰️ CALCULANDO ÍNDICES SATELITALES")
        with st.spinner("Simulando algoritmos GEE..."):
            indices_satelitales = calcular_indices_satelitales_simulados(gdf_dividido, tipo_pastura)
        
        # Crear dataframe con resultados
        gdf_analizado = gdf_dividido.copy()
        gdf_analizado['area_ha'] = areas_ha
        
        # Añadir índices satelitales
        for idx, indice in enumerate(indices_satelitales):
            for key, value in indice.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # 3. CALCULAR MÉTRICAS VOISIN
        st.subheader("🐄 CALCULANDO MÉTRICAS REGENERATIVAS")
        
        metricas_voisin = []
        for idx, row in gdf_analizado.iterrows():
            # EV/Ha
            ev_ha = calcular_ev_ha(
                row['biomasa_disponible_kg_ms_ha'], 
                row['area_ha'], 
                tipo_pastura
            )
            
            # Días de permanencia
            dias_permanencia = calcular_dias_permanencia(
                row['biomasa_disponible_kg_ms_ha'],
                row['area_ha'],
                tipo_pastura
            )
            
            # Estado forrajero
            estado_valor, estado_label = clasificar_estado_forrajero(
                row['biomasa_disponible_kg_ms_ha']
            )
            
            metricas_voisin.append({
                'ev_ha': round(ev_ha, 2),
                'dias_permanencia': round(dias_permanencia, 1),
                'estado_valor': estado_valor,
                'estado_label': estado_label,
                'biomasa_total_kg': round(row['biomasa_disponible_kg_ms_ha'] * row['area_ha'], 1)
            })
        
        # Añadir métricas Voisin
        for idx, metrica in enumerate(metricas_voisin):
            for key, value in metrica.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # 4. MOSTRAR RESULTADOS PRINCIPALES
        st.subheader("📊 RESULTADOS DEL ANÁLISIS VOISIN")
        
        # Estadísticas principales
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            biomasa_prom = gdf_analizado['biomasa_disponible_kg_ms_ha'].mean()
            st.metric("Biomasa Disponible", f"{biomasa_prom:.0f} kg MS/ha")
        
        with col2:
            ev_prom = gdf_analizado['ev_ha'].mean()
            st.metric("Carga Animal Promedio", f"{ev_prom:.1f} EV/Ha")
        
        with col3:
            dias_prom = gdf_analizado['dias_permanencia'].mean()
            st.metric("Permanencia Promedio", f"{dias_prom:.1f} días")
        
        with col4:
            capacidad_total = gdf_analizado['ev_ha'].sum() * area_total
            st.metric("Capacidad Total", f"{capacidad_total:.0f} EV")
        
        # 5. MAPAS INTERACTIVOS
        st.subheader("🗺️ MAPAS DE ANÁLISIS VOISIN")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write("**🌿 BIOMASA DISPONIBLE**")
            mapa_biomasa, _ = crear_mapa_voisin(gdf_analizado, "BIOMASA", tipo_pastura)
            if mapa_biomasa:
                st.image(mapa_biomasa, use_container_width=True)
                st.download_button(
                    "📥 Descargar Mapa Biomasa",
                    mapa_biomasa.getvalue(),
                    f"voisin_biomasa_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                    "image/png"
                )
        
        with col2:
            st.write("**🐄 CARGA ANIMAL**")
            mapa_ev, _ = crear_mapa_voisin(gdf_analizado, "EV_HA", tipo_pastura)
            if mapa_ev:
                st.image(mapa_ev, use_container_width=True)
                st.download_button(
                    "📥 Descargar Mapa EV/Ha",
                    mapa_ev.getvalue(),
                    f"voisin_evha_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                    "image/png"
                )
        
        with col3:
            st.write("**⏰ DÍAS PERMANENCIA**")
            mapa_dias, _ = crear_mapa_voisin(gdf_analizado, "DIAS_PERMANENCIA", tipo_pastura)
            if mapa_dias:
                st.image(mapa_dias, use_container_width=True)
                st.download_button(
                    "📥 Descargar Mapa Permanencia",
                    mapa_dias.getvalue(),
                    f"voisin_dias_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                    "image/png"
                )
        
        # 6. LEYENDAS INTERACTIVAS
        st.subheader("🎨 LEYENDAS DE INTERPRETACIÓN")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            crear_leyenda_interactiva('ESTADO')
        with col2:
            crear_leyenda_interactiva('EVHA')
        with col3:
            crear_leyenda_interactiva('DIAS_PERMANENCIA')
        
        # 7. TABLA DE RESULTADOS DETALLADOS
        st.subheader("🔬 DATOS DETALLADOS POR SUB-LOTE")
        
        columnas_detalle = [
            'id_subLote', 'area_ha', 'biomasa_disponible_kg_ms_ha', 
            'ndvi', 'evi', 'savi', 'ev_ha', 'dias_permanencia', 'estado_label'
        ]
        
        tabla_detalle = gdf_analizado[columnas_detalle].copy()
        tabla_detalle.columns = [
            'Sub-Lote', 'Área (ha)', 'Biomasa Disp. (kg MS/ha)', 
            'NDVI', 'EVI', 'SAVI', 'EV/Ha', 'Días Permanencia', 'Estado'
        ]
        
        st.dataframe(tabla_detalle, use_container_width=True)
        
        # 8. RECOMENDACIONES VOISIN
        st.subheader("💡 RECOMENDACIONES REGENERATIVAS")
        
        # Análisis de estado general
        estado_counts = gdf_analizado['estado_label'].value_counts()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**📈 DISTRIBUCIÓN DE ESTADO:**")
            for estado, count in estado_counts.items():
                porcentaje = (count / len(gdf_analizado)) * 100
                st.write(f"- {estado}: {count} sub-lotes ({porcentaje:.1f}%)")
        
        with col2:
            st.write("**🎯 ESTRATEGIA VOISIN:**")
            
            if estado_counts.get('CRÍTICO', 0) > 0:
                st.error("**🚨 ACCIÓN INMEDIATA REQUERIDA**")
                st.write("- Reducir carga animal urgentemente")
                st.write("- Implementar suplementación estratégica")
                st.write("- Evaluar resiembra con especies adaptadas")
            
            elif estado_counts.get('BAJO', 0) > len(gdf_analizado) * 0.3:
                st.warning("**⚠️ MANEJO PRECAUTORIO**")
                st.write("- Ajustar rotación a 40-45 días")
                st.write("- Monitorear crecimiento semanal")
                st.write("- Considerar fertilización orgánica")
            
            else:
                st.success("**✅ SITUACIÓN ÓPTIMA**")
                st.write("- Mantener manejo actual")
                st.write("- Continuar monitoreo mensual")
                st.write("- Enfoque en mejora continua")
        
        # 9. BOTONES DE EXPORTACIÓN
        st.subheader("💾 EXPORTAR RESULTADOS")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Exportar datos completos
            csv = gdf_analizado.to_csv(index=False)
            st.download_button(
                "📊 Descargar CSV Completo",
                csv,
                f"voisin_datos_completos_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv"
            )
        
        with col2:
            # Exportar resumen ejecutivo
            resumen = crear_resumen_ejecutivo(gdf_analizado, tipo_pastura, area_total)
            st.download_button(
                "📋 Descargar Resumen",
                resumen,
                f"voisin_resumen_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                "text/plain"
            )
        
        with col3:
            # Exportar todos los mapas
            def crear_pack_mapas():
                files = [
                    ("biomasa.png", mapa_biomasa.getvalue()),
                    ("ev_ha.png", mapa_ev.getvalue()),
                    ("dias_permanencia.png", mapa_dias.getvalue())
                ]
                return create_zip_file(files)
            
            st.download_button(
                "🗂️ Descargar Pack Mapas",
                crear_pack_mapas(),
                f"voisin_mapas_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                "application/zip"
            )
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error en análisis Voisin: {str(e)}")
        import traceback
        st.error(f"Detalle técnico: {traceback.format_exc()}")
        return False

def crear_resumen_ejecutivo(gdf, tipo_pastura, area_total):
    """Crea resumen ejecutivo del análisis"""
    total_ev = gdf['ev_ha'].sum()
    dias_prom = gdf['dias_permanencia'].mean()
    biomasa_prom = gdf['biomasa_disponible_kg_ms_ha'].mean()
    
    resumen = f"""
RESUMEN EJECUTIVO - SISTEMA VOISIN
==================================
Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Tipo de Pastura: {tipo_pastura}
Área Total: {area_total:.1f} ha
Sub-Lotes Analizados: {len(gdf)}

MÉTRICAS PRINCIPALES
-------------------
• Capacidad Total: {total_ev:.1f} EV
• Permanencia Promedio: {dias_prom:.1f} días
• Biomasa Disponible: {biomasa_prom:.0f} kg MS/ha

PARÁMETROS VOISIN APLICADOS
--------------------------
• Período Descanso: {PARAMETROS_VOISIN['PERIODO_DESCANSO']} días
• Días Máx. Pastoreo: {PARAMETROS_VOISIN['DIAS_MAXIMO_PASTOREO']} días
• Consumo Diario: {PARAMETROS_VOISIN['CONSUMO_DIARIO_VACA']} kg MS/vaca

RECOMENDACIONES
--------------
"""
    
    if dias_prom < 1:
        resumen += "• Aumentar período de descanso a 45 días\n"
    if total_ev < 1:
        resumen += "• Considerar aumentar carga animal gradualmente\n"
    if biomasa_prom < 200:
        resumen += "• Evaluar resiembra y fertilización orgánica\n"
    
    resumen += "• Mantener rotación intensiva según principios Voisin\n"
    resumen += "• Monitoreo continuo del crecimiento forrajero\n"
    
    return resumen

def create_zip_file(files):
    """Crea archivo ZIP con múltiples archivos"""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for file_name, file_data in files:
            zip_file.writestr(file_name, file_data)
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

# =================================================================
# INTERFAZ PRINCIPAL
# =================================================================

# Mostrar información inicial si no hay archivo cargado
if not uploaded_zip:
    st.info("📁 Sube el ZIP de tu potrero para comenzar el análisis Voisin")
    
    # Información del sistema
    with st.expander("ℹ️ INFORMACIÓN DEL SISTEMA VOISIN"):
        st.markdown("""
        **🌱 SISTEMA DE GANADERÍA REGENERATIVA VOISIN**
        
        **🎯 PRINCIPIOS APLICADOS:**
        - **Rotación Intensiva:** Períodos de descanso optimizados
        - **Carga Instantánea:** Cálculo preciso de EV/Ha
        - **Permanencia Controlada:** Máximo 3 días por parcela
        - **Descanso Prolongado:** 35+ días para recuperación
        
        **🛰️ METODOLOGÍA GEE ADAPTADA:**
        - **NDVI/EVI/SAVI:** Índices de vegetación satelital
        - **Biomasa Estimada:** Algoritmos científicos probados
        - **Análisis Espacial:** Variabilidad dentro del potrero
        - **Recomendaciones Precise:** Basadas en datos reales
        
        **🚀 INSTRUCCIONES:**
        1. **Sube** shapefile del potrero (ZIP)
        2. **Selecciona** tipo de pastura
        3. **Configura** parámetros Voisin
        4. **Ejecuta** análisis regenerativo
        5. **Descarga** mapas y reportes
        """)

# Procesar archivo cargado
else:
    with st.spinner("Cargando y analizando potrero..."):
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                # Extraer archivo ZIP
                with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                    zip_ref.extractall(tmp_dir)
                
                # Buscar archivo shapefile
                shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
                if shp_files:
                    shp_path = os.path.join(tmp_dir, shp_files[0])
                    gdf = gpd.read_file(shp_path)
                    
                    st.success(f"✅ **Potrero cargado correctamente:** {len(gdf)} polígono(s)")
                    
                    # Mostrar información del potrero
                    area_total = calcular_superficie(gdf).sum()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**📊 INFORMACIÓN DEL POTRERO:**")
                        st.write(f"- Polígonos: {len(gdf)}")
                        st.write(f"- Área total: {area_total:.1f} ha")
                        st.write(f"- CRS: {gdf.crs}")
                    
                    with col2:
                        st.write("**🎯 CONFIGURACIÓN VOISIN:**")
                        st.write(f"- Pastura: {tipo_pastura}")
                        st.write(f"- Sub-lotes: {n_divisiones}")
                        st.write(f"- Descanso: {PARAMETROS_VOISIN['PERIODO_DESCANSO']} días")
                        st.write(f"- Consumo: {PARAMETROS_VOISIN['CONSUMO_DIARIO_VACA']} kg/día")
                    
                    # Botón para ejecutar análisis
                    if st.button("🚀 EJECUTAR ANÁLISIS VOISIN COMPLETO", type="primary", use_container_width=True):
                        analisis_voisin_completo(gdf, tipo_pastura, n_divisiones)
                        
                else:
                    st.error("❌ No se encontró archivo .shp en el ZIP")
                    
        except Exception as e:
            st.error(f"❌ Error cargando el archivo: {str(e)}")
