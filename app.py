import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import io
from shapely.geometry import Polygon
import math
import folium
from streamlit_folium import st_folium
import ee
import geemap

# Configuración de la página
st.set_page_config(
    page_title="🌱 Analizador Forrajero con Sentinel-2",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("🌱 ANALIZADOR FORRAJERO CON SENTINEL-2")
st.markdown("---")

# Inicializar Earth Engine
try:
    ee.Initialize()
    st.session_state.ee_initialized = True
except:
    st.session_state.ee_initialized = False
    st.warning("⚠️ Earth Engine no está inicializado. Algunas funciones pueden no estar disponibles.")

# Inicializar estado de la sesión
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False
if 'gdf_dividido' not in st.session_state:
    st.session_state.gdf_dividido = None
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None
if 'sentinel_image' not in st.session_state:
    st.session_state.sentinel_image = None

# ===== FUNCIONES EARTH ENGINE Y SENTINEL-2 =====

def obtener_imagen_sentinel2(geometry, fecha_inicio, fecha_fin, nubosidad_maxima=20):
    """Obtiene imagen Sentinel-2 harmonizada"""
    try:
        # Convertir fechas
        start_date = ee.Date(fecha_inicio.strftime('%Y-%m-%d'))
        end_date = ee.Date(fecha_fin.strftime('%Y-%m-%d'))
        
        # Colección Sentinel-2 MSI harmonizada
        coleccion = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                    .filterBounds(geometry)
                    .filterDate(start_date, end_date)
                    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', nubosidad_maxima))
                    .sort('CLOUDY_PIXEL_PERCENTAGE'))
        
        # Verificar si hay imágenes
        count = coleccion.size().getInfo()
        if count == 0:
            st.warning("⚠️ No se encontraron imágenes Sentinel-2 para los criterios seleccionados")
            return None, None
        
        # Crear mosaico con la mediana
        imagen = coleccion.median()
        
        # Aplicar factor de escala
        imagen = imagen.multiply(0.0001)
        
        # Calcular índices de vegetación
        ndvi = imagen.normalizedDifference(['B8', 'B4']).rename('NDVI')
        evi = imagen.expression(
            '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))', {
                'NIR': imagen.select('B8'),
                'RED': imagen.select('B4'),
                'BLUE': imagen.select('B2')
            }).rename('EVI')
        
        # Calcular índices adicionales
        savi = imagen.expression(
            '1.5 * (NIR - RED) / (NIR + RED + 0.5)', {
                'NIR': imagen.select('B8'),
                'RED': imagen.select('B4')
            }).rename('SAVI')
        
        ndwi = imagen.normalizedDifference(['B3', 'B8']).rename('NDWI')
        
        # Agregar índices a la imagen
        imagen_con_indices = imagen.addBands([ndvi, evi, savi, ndwi])
        
        return imagen_con_indices, coleccion
        
    except Exception as e:
        st.error(f"❌ Error obteniendo imagen Sentinel-2: {str(e)}")
        return None, None

def extraer_valores_satelitales(gdf, imagen_s2):
    """Extrae valores reales de Sentinel-2 para cada sub-lote"""
    try:
        if imagen_s2 is None:
            return None
            
        resultados = []
        
        for idx, row in gdf.iterrows():
            # Convertir geometría a formato Earth Engine
            geom = row.geometry
            ee_geom = ee.Geometry(geom.__geo_interface__)
            
            # Reducir región para obtener estadísticas
            stats = imagen_s2.select(['NDVI', 'EVI', 'SAVI', 'NDWI', 'B2', 'B3', 'B4', 'B8']).reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee_geom,
                scale=10,
                bestEffort=True
            )
            
            # Obtener valores
            stats_info = stats.getInfo()
            
            resultados.append({
                'ndvi_real': stats_info.get('NDVI', 0),
                'evi_real': stats_info.get('EVI', 0),
                'savi_real': stats_info.get('SAVI', 0),
                'ndwi_real': stats_info.get('NDWI', 0),
                'blue_real': stats_info.get('B2', 0),
                'green_real': stats_info.get('B3', 0),
                'red_real': stats_info.get('B4', 0),
                'nir_real': stats_info.get('B8', 0)
            })
        
        return resultados
        
    except Exception as e:
        st.warning(f"⚠️ No se pudieron extraer valores satelitales: {str(e)}")
        return None

def crear_mapa_satelital(gdf, imagen_s2, tipo_pastura, resultados_analisis):
    """Crea mapa interactivo con Google Satellite y Sentinel-2"""
    try:
        # Obtener centroide del área
        centroid = gdf.geometry.centroid.iloc[0]
        centro_lat, centro_lon = centroid.y, centroid.x
        
        # Crear mapa base con Google Satellite
        mapa = folium.Map(
            location=[centro_lat, centro_lon],
            zoom_start=12,
            tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
            attr='Google Satellite'
        )
        
        # Añadir capa Sentinel-2 NDVI si está disponible
        if imagen_s2 is not None:
            try:
                # Obtener URL de tiles para NDVI
                vis_params_ndvi = {
                    'min': 0.0,
                    'max': 0.8,
                    'palette': ['0000ff', '00ff00', 'ffff00', 'ff0000']  # Azul a Rojo
                }
                
                # Crear URL del tile
                map_id_dict = imagen_s2.select('NDVI').getMapId(vis_params_ndvi)
                tile_url = map_id_dict['tile_fetcher'].url_format
                
                # Añadir capa de NDVI
                folium.TileLayer(
                    tiles=tile_url,
                    attr='Sentinel-2 NDVI',
                    name='NDVI Sentinel-2',
                    overlay=True,
                    opacity=0.7
                ).add_to(mapa)
                
            except Exception as e:
                st.warning(f"No se pudo cargar la capa NDVI: {str(e)}")
        
        # Añadir polígonos de sub-lotes
        for idx, row in gdf.iterrows():
            id_sub_lote = row['id_subLote']
            
            # Usar valores reales si están disponibles, sino simulados
            if resultados_analisis and idx < len(resultados_analisis):
                if 'ndvi_real' in resultados_analisis[idx] and resultados_analisis[idx]['ndvi_real'] is not None:
                    ndvi = resultados_analisis[idx]['ndvi_real']
                    biomasa = resultados_analisis[idx]['biomasa_real_kg_ms_ha']
                else:
                    ndvi = resultados_analisis[idx]['ndvi']
                    biomasa = resultados_analisis[idx]['biomasa_disponible_kg_ms_ha']
                
                tipo_superficie = resultados_analisis[idx]['tipo_superficie']
                cobertura = resultados_analisis[idx]['cobertura_vegetal']
            else:
                # Valores por defecto
                ndvi = 0.5
                biomasa = 500
                tipo_superficie = "VEGETACION_MODERADA"
                cobertura = 0.7
            
            # Color según NDVI (más preciso que biomasa)
            if ndvi < 0.2:
                color = '#d73027'  # Rojo - Suelo desnudo
            elif ndvi < 0.4:
                color = '#fc8d59'  # Naranja - Vegetación escasa
            elif ndvi < 0.6:
                color = '#fee08b'  # Amarillo - Vegetación moderada
            elif ndvi < 0.8:
                color = '#91cf60'  # Verde claro - Vegetación buena
            else:
                color = '#1a9850'  # Verde oscuro - Vegetación densa
            
            # Crear polígono
            geom = row.geometry
            if geom.geom_type == 'Polygon':
                coords = [[point[1], point[0]] for point in geom.exterior.coords]
                
                folium.Polygon(
                    locations=coords,
                    popup=f"""
                    <div style="font-family: Arial; font-size: 12px; min-width: 200px;">
                        <h4>🌿 Sub-Lote S{id_sub_lote}</h4>
                        <b>NDVI Sentinel-2:</b> {ndvi:.3f}<br>
                        <b>Biomasa estimada:</b> {biomasa:.0f} kg MS/ha<br>
                        <b>Tipo superficie:</b> {tipo_superficie}<br>
                        <b>Cobertura:</b> {cobertura:.1%}<br>
                        <b>Área:</b> {row['area_ha']:.1f} ha
                    </div>
                    """,
                    tooltip=f'S{id_sub_lote} - NDVI: {ndvi:.3f}',
                    color=color,
                    fill_color=color,
                    fill_opacity=0.5,
                    weight=2,
                    opacity=0.8
                ).add_to(mapa)
        
        # Añadir control de capas
        folium.LayerControl().add_to(mapa)
        
        return mapa
        
    except Exception as e:
        st.error(f"❌ Error creando mapa satelital: {str(e)}")
        # Mapa de fallback
        return folium.Map(location=[-34.0, -64.0], zoom_start=4)

# ===== FUNCIONES DE ANÁLISIS =====

def calcular_superficie(gdf):
    """Calcula superficie en hectáreas"""
    try:
        if gdf.crs and gdf.crs.is_geographic:
            gdf_projected = gdf.to_crs('EPSG:3857')
            area_m2 = gdf_projected.geometry.area
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000
    except:
        return gdf.geometry.area / 10000

def dividir_potrero(gdf, n_zonas):
    """Divide el potrero en sub-lotes"""
    if len(gdf) == 0:
        return gdf
    
    potrero_principal = gdf.iloc[0].geometry
    bounds = potrero_principal.bounds
    minx, miny, maxx, maxy = bounds
    
    sub_poligonos = []
    
    n_cols = math.ceil(math.sqrt(n_zonas))
    n_rows = math.ceil(n_zonas / n_cols)
    
    ancho_celda = (maxx - minx) / n_cols
    alto_celda = (maxy - miny) / n_rows
    
    for i in range(n_rows):
        for j in range(n_cols):
            if len(sub_poligonos) >= n_zonas:
                break
                
            celda_minx = minx + (j * ancho_celda)
            celda_maxx = minx + ((j + 1) * ancho_celda)
            celda_miny = miny + (i * alto_celda)
            celda_maxy = miny + ((i + 1) * alto_celda)
            
            celda_poly = Polygon([
                (celda_minx, celda_miny),
                (celda_maxx, celda_miny),
                (celda_maxx, celda_maxy),
                (celda_minx, celda_maxy)
            ])
            
            interseccion = potrero_principal.intersection(celda_poly)
            if not interseccion.is_empty and interseccion.area > 0:
                sub_poligonos.append(interseccion)
    
    if sub_poligonos:
        nuevo_gdf = gpd.GeoDataFrame({
            'id_subLote': range(1, len(sub_poligonos) + 1),
            'geometry': sub_poligonos
        }, crs=gdf.crs)
        return nuevo_gdf
    else:
        return gdf

def analizar_con_sentinel2(gdf_dividido, tipo_pastura, valores_reales):
    """Analiza usando datos reales de Sentinel-2"""
    resultados = []
    
    # Factores de conversión NDVI a biomasa por tipo de pastura
    factores_biomasa = {
        "ALFALFA": 3000,
        "RAYGRASS": 2800,
        "FESTUCA": 2500,
        "AGROPIRRO": 2200,
        "PASTIZAL_NATURAL": 2000,
        "PERSONALIZADO": 2500
    }
    
    factor = factores_biomasa.get(tipo_pastura, 2500)
    
    for idx, (row, valores) in enumerate(zip(gdf_dividido.iterrows(), valores_reales)):
        row = row[1]  # Obtener la fila
        
        # Usar valores reales de Sentinel-2
        ndvi = valores.get('ndvi_real', 0)
        evi = valores.get('evi_real', 0)
        savi = valores.get('savi_real', 0)
        ndwi = valores.get('ndwi_real', 0)
        
        # Calcular biomasa basada en NDVI real
        biomasa_ms_ha = max(0, (ndvi * factor) - 500)  # Ajuste lineal
        
        # Clasificar tipo de superficie basado en NDVI real
        if ndvi < 0.2:
            tipo_superficie = "SUELO_DESNUDO"
            cobertura = max(0.1, ndvi * 0.5)
        elif ndvi < 0.4:
            tipo_superficie = "VEGETACION_ESCASA"
            cobertura = 0.3 + (ndvi - 0.2) * 2
        elif ndvi < 0.6:
            tipo_superficie = "VEGETACION_MODERADA"
            cobertura = 0.6 + (ndvi - 0.4) * 1.5
        else:
            tipo_superficie = "VEGETACION_DENSA"
            cobertura = 0.8 + (ndvi - 0.6) * 1.0
        
        cobertura = min(0.95, cobertura)
        
        # Calcular crecimiento diario basado en NDVI y tipo de pastura
        if tipo_pastura == "ALFALFA":
            crecimiento_base = 80
        elif tipo_pastura == "RAYGRASS":
            crecimiento_base = 70
        elif tipo_pastura == "FESTUCA":
            crecimiento_base = 50
        elif tipo_pastura == "AGROPIRRO":
            crecimiento_base = 45
        else:
            crecimiento_base = 30
        
        crecimiento_diario = crecimiento_base * ndvi
        
        resultados.append({
            'ndvi': ndvi,
            'evi': evi,
            'savi': savi,
            'ndwi': ndwi,
            'cobertura_vegetal': cobertura,
            'tipo_superficie': tipo_superficie,
            'biomasa_disponible_kg_ms_ha': biomasa_ms_ha,
            'biomasa_real_kg_ms_ha': biomasa_ms_ha,
            'crecimiento_diario': crecimiento_diario,
            'factor_calidad': min(0.95, ndwi + 0.5),
            'ndvi_real': ndvi,
            'evi_real': evi
        })
    
    return resultados

# ===== INTERFAZ PRINCIPAL =====

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración del Análisis")
    
    st.subheader("🌿 Tipo de Pastura")
    tipo_pastura = st.selectbox(
        "Selecciona el tipo de pastura:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"]
    )
    
    st.subheader("🛰️ Configuración Satelital")
    fecha_fin = st.date_input("Fecha de análisis", value=datetime.now() - timedelta(days=30))
    fecha_inicio = st.date_input("Fecha inicio", value=fecha_fin - timedelta(days=60))
    nubosidad_maxima = st.slider("Nubosidad máxima (%)", 0, 50, 20)
    
    st.subheader("🐄 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 10, 500, 100)
    
    st.subheader("🎯 División del Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", 4, 36, 16, 4)
    
    st.subheader("📤 Cargar Shapefile")
    uploaded_zip = st.file_uploader(
        "Sube tu shapefile comprimido en ZIP:",
        type=['zip']
    )
    
    st.markdown("---")
    if st.button("🔄 Limpiar Análisis", use_container_width=True):
        st.session_state.analysis_done = False
        st.session_state.gdf_dividido = None
        st.session_state.analysis_results = None
        st.session_state.sentinel_image = None
        st.rerun()

# Contenido principal
if uploaded_zip:
    try:
        with st.spinner("Procesando shapefile..."):
            with tempfile.TemporaryDirectory() as tmp_dir:
                with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                    zip_ref.extractall(tmp_dir)
                
                shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
                if not shp_files:
                    st.error("❌ No se encontró ningún archivo .shp en el ZIP")
                    st.stop()
                
                shp_path = os.path.join(tmp_dir, shp_files[0])
                gdf = gpd.read_file(shp_path)
                
                if len(gdf) == 0:
                    st.error("❌ El shapefile no contiene geometrías válidas")
                    st.stop()
                
                st.success(f"✅ **Potrero cargado correctamente**")
                
                area_total = calcular_superficie(gdf).sum()
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🗺️ Polígonos", len(gdf))
                with col2:
                    st.metric("📏 Área Total", f"{area_total:.1f} ha")
                with col3:
                    st.metric("🎯 Tipo CRS", str(gdf.crs))
                
                # OBTENER IMAGEN SENTINEL-2
                if st.session_state.ee_initialized:
                    st.subheader("🛰️ Obteniendo Imagen Sentinel-2")
                    with st.spinner("Descargando imagen satelital..."):
                        geometry = ee.Geometry(gdf.geometry.iloc[0].__geo_interface__)
                        imagen_s2, coleccion = obtener_imagen_sentinel2(
                            geometry, fecha_inicio, fecha_fin, nubosidad_maxima
                        )
                        
                        if imagen_s2 is not None:
                            st.session_state.sentinel_image = imagen_s2
                            count = coleccion.size().getInfo()
                            st.success(f"✅ Imagen Sentinel-2 obtenida ({count} imágenes procesadas)")
                        else:
                            st.warning("⚠️ Usando datos simulados (no se pudo obtener imagen real)")
                else:
                    st.warning("⚠️ Earth Engine no disponible - Usando datos simulados")
                
                # EJECUTAR ANÁLISIS
                if not st.session_state.analysis_done:
                    st.markdown("---")
                    if st.button("🚀 EJECUTAR ANÁLISIS CON SENTINEL-2", type="primary", use_container_width=True):
                        with st.spinner("Realizando análisis forrajero..."):
                            # Dividir potrero
                            gdf_dividido = dividir_potrero(gdf, n_divisiones)
                            st.session_state.gdf_dividido = gdf_dividido
                            
                            # Calcular áreas
                            areas_ha = calcular_superficie(gdf_dividido)
                            st.session_state.gdf_dividido['area_ha'] = areas_ha
                            
                            # Extraer valores satelitales si están disponibles
                            valores_reales = None
                            if st.session_state.sentinel_image is not None:
                                valores_reales = extraer_valores_satelitales(gdf_dividido, st.session_state.sentinel_image)
                            
                            # Realizar análisis
                            if valores_reales:
                                resultados = analizar_con_sentinel2(gdf_dividido, tipo_pastura, valores_reales)
                                st.success("✅ Análisis completado con datos Sentinel-2 reales")
                            else:
                                # Fallback a datos simulados
                                st.warning("⚠️ Usando datos simulados (no hay datos satelitales)")
                                # Aquí iría tu función de simulación
                                resultados = []  # Placeholder
                            
                            st.session_state.analysis_results = resultados
                            st.session_state.analysis_done = True
                            st.rerun()
                
                # MOSTRAR RESULTADOS
                if st.session_state.analysis_done and st.session_state.gdf_dividido is not None:
                    st.markdown("---")
                    
                    # MAPA SATELITAL INTERACTIVO
                    st.subheader("🗺️ Mapa Satelital con Sentinel-2")
                    
                    mapa = crear_mapa_satelital(
                        st.session_state.gdf_dividido,
                        st.session_state.sentinel_image,
                        tipo_pastura,
                        st.session_state.analysis_results
                    )
                    
                    st_folium(mapa, width=1200, height=600, key="mapa_satelital")
                    
                    # RESULTADOS Y ESTADÍSTICAS
                    st.subheader("📊 Resultados del Análisis")
                    
                    if st.session_state.analysis_results:
                        # Calcular estadísticas
                        if st.session_state.sentinel_image is not None:
                            ndvis = [r['ndvi_real'] for r in st.session_state.analysis_results if r['ndvi_real'] is not None]
                            biomasas = [r['biomasa_real_kg_ms_ha'] for r in st.session_state.analysis_results]
                            fuente = "Sentinel-2 Real"
                        else:
                            ndvis = [r['ndvi'] for r in st.session_state.analysis_results]
                            biomasas = [r['biomasa_disponible_kg_ms_ha'] for r in st.session_state.analysis_results]
                            fuente = "Simulado"
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("🌿 NDVI Promedio", f"{np.mean(ndvis):.3f}", f"Fuente: {fuente}")
                        with col2:
                            st.metric("📈 Biomasa Promedio", f"{np.mean(biomasas):.0f} kg MS/ha")
                        with col3:
                            st.metric("🗺️ Sub-lotes", len(st.session_state.gdf_dividido))
                        with col4:
                            tipos = {}
                            for r in st.session_state.analysis_results:
                                tipos[r['tipo_superficie']] = tipos.get(r['tipo_superficie'], 0) + 1
                            st.metric("🎯 Tipo Principal", max(tipos, key=tipos.get))
                        
                        # TABLA DETALLADA
                        st.subheader("📋 Detalle por Sub-Lote")
                        
                        df_detalle = pd.DataFrame({
                            'Sub-Lote': [f"S{id}" for id in range(1, len(st.session_state.analysis_results) + 1)],
                            'NDVI': [f"{r['ndvi_real'] if r['ndvi_real'] is not None else r['ndvi']:.3f}" for r in st.session_state.analysis_results],
                            'Biomasa (kg/ha)': [f"{r['biomasa_real_kg_ms_ha'] if 'biomasa_real_kg_ms_ha' in r else r['biomasa_disponible_kg_ms_ha']:.0f}" for r in st.session_state.analysis_results],
                            'Cobertura': [f"{r['cobertura_vegetal']:.1%}" for r in st.session_state.analysis_results],
                            'Tipo Superficie': [r['tipo_superficie'] for r in st.session_state.analysis_results],
                            'Área (ha)': [f"{area:.1f}" for area in st.session_state.gdf_dividido['area_ha']]
                        })
                        
                        st.dataframe(df_detalle, use_container_width=True)
    
    except Exception as e:
        st.error(f"❌ Error procesando el archivo: {str(e)}")

else:
    # Pantalla de bienvenida
    st.markdown("""
    ## 🛰️ Analizador Forrajero con Sentinel-2
    
    **¡Bienvenido!** Esta herramienta utiliza imágenes satelitales **Sentinel-2 harmonizadas (10m)**
    para analizar la productividad forrajera de tus potreros.
    
    ### 🌟 Características principales:
    
    - **🛰️ Imágenes Sentinel-2 reales** - Datos satelitales en tiempo real
    - **🗺️ Google Satellite** - Visualización sobre mapa base satelital
    - **🌿 Índices de vegetación** - NDVI, EVI, SAVI, NDWI calculados desde satélite
    - **📊 Análisis preciso** - Biomasa estimada basada en datos reales
    - **🎯 Sub-división inteligente** - Análisis detallado por sub-lotes
    
    ### 📁 Cómo usar:
    
    1. **Prepara tu shapefile** con el potrero (.shp, .shx, .dbf, .prj)
    2. **Comprime en ZIP** y súbelo arriba
    3. **Configura las fechas** para el análisis satelital
    4. **Ejecuta el análisis** y explora los resultados
    
    ### ⚠️ Requisitos para datos satelitales:
    
    - Conexión a Internet
    - Shapefile con sistema de coordenadas válido
    - Fechas con imágenes disponibles (sin nubes)
    """)

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666;'>"
    "🌱 Analizador Forrajero con Sentinel-2 | "
    "Datos satelitales: Copernicus Sentinel-2 | "
    "Google Earth Engine"
    "</div>",
    unsafe_allow_html=True
)
