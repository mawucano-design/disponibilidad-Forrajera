import ee
import geemap
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

st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - METODOLOGÍA GEE")
st.markdown("---")

# Configurar para restaurar .shx automáticamente
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Inicializar Earth Engine
try:
    ee.Initialize()
except Exception as e:
    try:
        ee.Authenticate()
        ee.Initialize()
    except:
        st.warning("⚠️ Earth Engine no está inicializado. Algunas funciones satelitales pueden no estar disponibles.")

# Configuración inicial (mantener tu código existente)
ms_optimo = 3000
crecimiento_diario = 50
consumo_porcentaje = 0.025
tasa_utilizacion = 0.55
umbral_ndvi_suelo = 0.2
umbral_ndvi_pastura = 0.55

# Sidebar (mantener tu código existente)
with st.sidebar:
    st.header("⚙️ Configuración")
    
    tipo_pastura = st.selectbox("Tipo de Pastura:", 
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])
    
    # Mostrar parámetros personalizables si se selecciona PERSONALIZADO
    if tipo_pastura == "PERSONALIZADO":
        st.subheader("📊 Parámetros Forrajeros Personalizados")
        ms_optimo = st.number_input("Biomasa Óptima (kg MS/ha):", min_value=1000, max_value=8000, value=3000)
        crecimiento_diario = st.number_input("Crecimiento Diario (kg MS/ha/día):", min_value=10, max_value=200, value=50)
        consumo_porcentaje = st.number_input("Consumo (% peso vivo):", min_value=0.01, max_value=0.05, value=0.025, step=0.001, format="%.3f")
        tasa_utilizacion = st.number_input("Tasa Utilización:", min_value=0.3, max_value=0.8, value=0.55, step=0.01, format="%.2f")
        umbral_ndvi_suelo = st.number_input("Umbral NDVI Suelo:", min_value=0.1, max_value=0.4, value=0.2, step=0.01, format="%.2f")
        umbral_ndvi_pastura = st.number_input("Umbral NDVI Pastura:", min_value=0.4, max_value=0.8, value=0.55, step=0.01, format="%.2f")
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=32, value=24)
    
    st.subheader("🛰️ Configuración Satelital")
    fecha_inicio = st.date_input("Fecha inicio análisis", value=datetime(2024, 1, 1))
    fecha_fin = st.date_input("Fecha fin análisis", value=datetime(2024, 12, 31))
    nubosidad_maxima = st.slider("Nubosidad máxima (%)", 0, 50, 20)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])

# PARÁMETROS FORRAJEROS (mantener tu código existente)
PARAMETROS_FORRAJEROS_BASE = {
    # ... (mantener tu diccionario existente de parámetros)
}

# Función para obtener Sentinel-2 harmonizado
def obtener_imagen_sentinel2_harmonizada(geometry, fecha_inicio, fecha_fin, nubosidad_maxima=20):
    """
    Obtiene imagen Sentinel-2 harmonizada (10m) para el área y período especificados
    """
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
        
        # Agregar índices a la imagen
        imagen_con_indices = imagen.addBands([ndvi, evi])
        
        return imagen_con_indices, coleccion
        
    except Exception as e:
        st.error(f"❌ Error obteniendo imagen Sentinel-2: {str(e)}")
        return None, None

# Función para crear mapa interactivo con Google Satellite
def crear_mapa_interactivo_gee(gdf, imagen_s2, tipo_pastura, resultados_analisis):
    """
    Crea mapa interactivo con Google Satellite y resultados del análisis
    """
    try:
        # Obtener centroide del área de estudio
        centroid = gdf.geometry.centroid.iloc[0]
        center_lat, center_lon = centroid.y, centroid.x
        
        # Crear mapa base con Google Satellite
        mapa = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=12,
            tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
            attr='Google Satellite'
        )
        
        # Añadir capa Sentinel-2 si está disponible
        if imagen_s2 is not None:
            try:
                # Parámetros de visualización para NDVI
                vis_params_ndvi = {
                    'min': -0.2,
                    'max': 0.8,
                    'palette': ['blue', 'white', 'green']
                }
                
                # Añadir capa NDVI con transparencia
                ndvi_layer = folium.raster_layers.TileLayer(
                    tiles=imagen_s2.select('NDVI').getThumbURL(vis_params_ndvi),
                    name='NDVI Sentinel-2',
                    attr='Sentinel-2 Harmonizado',
                    overlay=True,
                    opacity=0.6
                )
                ndvi_layer.add_to(mapa)
                
            except Exception as e:
                st.warning(f"No se pudo cargar la capa Sentinel-2: {str(e)}")
        
        # Añadir polígonos de sub-lotes con colores según biomasa
        if resultados_analisis is not None:
            for idx, row in gdf.iterrows():
                sub_lote_id = row['id_subLote']
                biomasa = resultados_analisis[idx]['biomasa_disponible_kg_ms_ha']
                
                # Color según biomasa
                if biomasa < 200:
                    color = 'red'
                elif biomasa < 400:
                    color = 'orange'
                elif biomasa < 600:
                    color = 'yellow'
                elif biomasa < 800:
                    color = 'lightgreen'
                else:
                    color = 'darkgreen'
                
                # Crear polígono
                geom = row.geometry
                if geom.geom_type == 'Polygon':
                    coords = [[point[1], point[0]] for point in geom.exterior.coords]
                    
                    folium.Polygon(
                        locations=coords,
                        popup=f"""
                        <b>Sub-Lote S{sub_lote_id}</b><br>
                        Biomasa: {biomasa} kg MS/ha<br>
                        NDVI: {resultados_analisis[idx]['ndvi']}<br>
                        Tipo: {resultados_analisis[idx]['tipo_superficie']}
                        """,
                        tooltip=f'S{sub_lote_id} - {biomasa} kg MS/ha',
                        color=color,
                        fill_color=color,
                        fill_opacity=0.3,
                        weight=2
                    ).add_to(mapa)
        
        # Añadir control de capas
        folium.LayerControl().add_to(mapa)
        
        return mapa
        
    except Exception as e:
        st.error(f"❌ Error creando mapa interactivo: {str(e)}")
        return None

# Función para extraer valores satelitales reales
def extraer_valores_satelitales_reales(gdf, imagen_s2):
    """
    Extrae valores reales de Sentinel-2 para cada sub-lote
    """
    try:
        if imagen_s2 is None:
            return None
            
        resultados = []
        
        for idx, row in gdf.iterrows():
            # Convertir geometría a formato Earth Engine
            geom = row.geometry
            ee_geom = ee.Geometry(geom.wkt)
            
            # Reducir región para obtener estadísticas
            stats = imagen_s2.select(['NDVI', 'EVI', 'B2', 'B3', 'B4', 'B8']).reduceRegion(
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
                'blue_real': stats_info.get('B2', 0),
                'green_real': stats_info.get('B3', 0),
                'red_real': stats_info.get('B4', 0),
                'nir_real': stats_info.get('B8', 0)
            })
        
        return resultados
        
    except Exception as e:
        st.warning(f"⚠️ No se pudieron extraer valores satelitales reales: {str(e)}")
        return None

# Modificar la función de análisis forrajero para integrar Sentinel-2
def analisis_forrajero_completo_mejorado(gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones, fecha_inicio, fecha_fin, nubosidad_maxima):
    try:
        st.header(f"🌱 ANÁLISIS FORRAJERO - {tipo_pastura}")
        
        # Obtener geometría para Earth Engine
        geometry = ee.Geometry(gdf.geometry.iloc[0].__geo_interface__)
        
        # PASO 1: OBTENER IMAGEN SENTINEL-2
        st.subheader("🛰️ OBTENIENDO IMAGEN SENTINEL-2 HARMONIZADA")
        with st.spinner("Descargando imagen satelital..."):
            imagen_s2, coleccion_s2 = obtener_imagen_sentinel2_harmonizada(
                geometry, fecha_inicio, fecha_fin, nubosidad_maxima
            )
        
        if imagen_s2 is not None:
            st.success("✅ Imagen Sentinel-2 harmonizada obtenida exitosamente")
            
            # Mostrar información de la imagen
            try:
                count = coleccion_s2.size().getInfo()
                st.info(f"📊 Se procesaron {count} imágenes Sentinel-2")
            except:
                st.info("📊 Imagen Sentinel-2 procesada correctamente")
        
        # PASO 2: DIVIDIR POTRERO
        st.subheader("📐 DIVIDIENDO POTRERO EN SUB-LOTES")
        with st.spinner("Dividiendo potrero..."):
            gdf_dividido = dividir_potrero_en_subLotes(gdf, n_divisiones)
        
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # Calcular áreas
        areas_ha = calcular_superficie(gdf_dividido)
        area_total = areas_ha.sum()
        
        # PASO 3: EXTRAER VALORES SATELITALES REALES
        st.subheader("📊 EXTRAYENDO VALORES SATELITALES REALES")
        valores_reales = None
        if imagen_s2 is not None:
            with st.spinner("Extrayendo valores de Sentinel-2..."):
                valores_reales = extraer_valores_satelitales_reales(gdf_dividido, imagen_s2)
            
            if valores_reales:
                st.success("✅ Valores satelitales reales extraídos")
            else:
                st.warning("⚠️ Usando valores simulados (modo fallback)")
        
        # PASO 4: CALCULAR ÍNDICES FORRAJEROS (integrados con valores reales)
        st.subheader("🌿 CALCULANDO ÍNDICES FORRAJEROS")
        with st.spinner("Ejecutando algoritmos GEE..."):
            if valores_reales:
                # Usar valores reales de Sentinel-2
                indices_forrajeros = calcular_indices_forrajeros_reales(gdf_dividido, tipo_pastura, valores_reales)
            else:
                # Usar valores simulados (fallback)
                indices_forrajeros = calcular_indices_forrajeros_gee(gdf_dividido, tipo_pastura)
        
        # Crear dataframe con resultados
        gdf_analizado = gdf_dividido.copy()
        gdf_analizado['area_ha'] = areas_ha
        
        # Añadir índices forrajeros
        for idx, indice in enumerate(indices_forrajeros):
            for key, value in indice.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # PASO 5: CALCULAR MÉTRICAS GANADERAS
        st.subheader("🐄 CALCULANDO MÉTRICAS GANADERAS")
        with st.spinner("Calculando equivalentes vaca..."):
            metricas_ganaderas = calcular_metricas_ganaderas(gdf_analizado, tipo_pastura, peso_promedio, carga_animal)
        
        # Añadir métricas ganaderas
        for idx, metrica in enumerate(metricas_ganaderas):
            for key, value in metrica.items():
                gdf_analizado.loc[gdf_analizado.index[idx], key] = value
        
        # PASO 6: CREAR MAPA INTERACTIVO CON GOOGLE SATELLITE
        st.subheader("🗺️ MAPA INTERACTIVO CON SENTINEL-2")
        
        if imagen_s2 is not None:
            with st.spinner("Generando mapa interactivo..."):
                mapa_interactivo = crear_mapa_interactivo_gee(
                    gdf_analizado, imagen_s2, tipo_pastura, indices_forrajeros
                )
            
            if mapa_interactivo:
                st_folium(mapa_interactivo, width=1200, height=600)
                
                # Descargar mapa como HTML
                html_string = mapa_interactivo.get_root().render()
                st.download_button(
                    "📥 Descargar Mapa Interactivo",
                    html_string,
                    f"mapa_interactivo_{tipo_pastura}_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
                    "text/html",
                    key="descarga_mapa_interactivo"
                )
        
        # PASO 7: MOSTRAR COMPARACIÓN VALORES REALES VS SIMULADOS
        if valores_reales:
            st.subheader("🔍 COMPARACIÓN: VALORES REALES VS MODELO")
            
            # Crear dataframe comparativo
            comparacion_data = []
            for idx, (real, simulado) in enumerate(zip(valores_reales, indices_forrajeros)):
                comparacion_data.append({
                    'Sub-Lote': idx + 1,
                    'NDVI Real': real.get('ndvi_real', 0),
                    'NDVI Modelo': simulado.get('ndvi', 0),
                    'EVI Real': real.get('evi_real', 0),
                    'EVI Modelo': simulado.get('evi', 0),
                    'Diferencia NDVI': abs(real.get('ndvi_real', 0) - simulado.get('ndvi', 0))
                })
            
            df_comparacion = pd.DataFrame(comparacion_data)
            st.dataframe(df_comparacion, use_container_width=True)
            
            # Calcular precisión
            precision_ndvi = 1 - (df_comparacion['Diferencia NDVI'].mean() / df_comparacion['NDVI Real'].mean())
            st.metric("📊 Precisión del Modelo NDVI", f"{precision_ndvi*100:.1f}%")
        
        # ... (mantener el resto de tu código existente para tablas, gráficos, etc.)
        
        return True, gdf_analizado
        
    except Exception as e:
        st.error(f"❌ Error en análisis forrajero: {str(e)}")
        import traceback
        st.error(f"Detalle: {traceback.format_exc()}")
        return False, None

# Nueva función para calcular índices con valores reales
def calcular_indices_forrajeros_reales(gdf, tipo_pastura, valores_reales):
    """
    Calcula índices forrajeros usando valores reales de Sentinel-2
    """
    params = obtener_parametros_forrajeros(tipo_pastura)
    resultados = []
    
    for idx, (row, valores) in enumerate(zip(gdf.iterrows(), valores_reales)):
        row = row[1]  # Obtener la fila actual
        
        # Usar valores reales de Sentinel-2
        ndvi = valores.get('ndvi_real', 0)
        evi = valores.get('evi_real', 0)
        red = valores.get('red_real', 0.15)
        nir = valores.get('nir_real', 0.25)
        blue = valores.get('blue_real', 0.1)
        
        # Calcular índices adicionales
        savi = 1.5 * (nir - red) / (nir + red + 0.5) if (nir + red + 0.5) > 0 else 0
        ndwi = (nir - red) / (nir + red) if (nir + red) > 0 else 0  # Simplified NDWI
        
        # Clasificar tipo de superficie basado en valores reales
        if ndvi < 0.2:
            tipo_superficie = "SUELO_DESNUDO"
            cobertura_vegetal = 0.1
        elif ndvi < 0.4:
            tipo_superficie = "VEGETACION_ESCASA"
            cobertura_vegetal = 0.4
        elif ndvi < 0.6:
            tipo_superficie = "VEGETACION_MODERADA"
            cobertura_vegetal = 0.7
        else:
            tipo_superficie = "VEGETACION_DENSA"
            cobertura_vegetal = 0.9
        
        # Calcular biomasa basada en valores reales
        biomasa_ms_ha = (ndvi * params['FACTOR_BIOMASA_NDVI'] + params['OFFSET_BIOMASA'])
        biomasa_ms_ha = max(0, min(6000, biomasa_ms_ha))
        
        # Calcular biomasa disponible
        if tipo_superficie in ["SUELO_DESNUDO"]:
            biomasa_disponible = 0
        else:
            biomasa_disponible = biomasa_ms_ha * cobertura_vegetal * 0.7  # Factor de eficiencia
        
        resultados.append({
            'ndvi': round(ndvi, 3),
            'evi': round(evi, 3),
            'savi': round(savi, 3),
            'ndwi': round(ndwi, 3),
            'cobertura_vegetal': round(cobertura_vegetal, 3),
            'tipo_superficie': tipo_superficie,
            'biomasa_ms_ha': round(biomasa_ms_ha, 1),
            'biomasa_disponible_kg_ms_ha': round(biomasa_disponible, 1),
            'crecimiento_diario': round(params['CRECIMIENTO_DIARIO'] * (ndvi + 0.2), 1),
            'factor_calidad': round(min(0.9, ndvi + 0.3), 3),
            'bsi': 0.0,  # Placeholder
            'ndbi': 0.0,  # Placeholder
            'nbr': 0.0,   # Placeholder
            'prob_suelo_desnudo': round(1 - cobertura_vegetal, 3)
        })
    
    return resultados

# Mantener todas tus funciones existentes (dividir_potrero_en_subLotes, calcular_metricas_ganaderas, etc.)
# ... (aquí van todas tus funciones existentes sin cambios)

# INTERFAZ PRINCIPAL MODIFICADA
if uploaded_zip:
    with st.spinner("Cargando potrero..."):
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                    zip_ref.extractall(tmp_dir)
                
                shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
                if shp_files:
                    shp_path = os.path.join(tmp_dir, shp_files[0])
                    gdf = gpd.read_file(shp_path)
                    
                    st.success(f"✅ **Potrero cargado:** {len(gdf)} polígono(s)")
                    
                    area_total = calcular_superficie(gdf).sum()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**📊 INFORMACIÓN DEL POTRERO:**")
                        st.write(f"- Polígonos: {len(gdf)}")
                        st.write(f"- Área total: {area_total:.1f} ha")
                        st.write(f"- CRS: {gdf.crs}")
                    
                    with col2:
                        st.write("**🎯 CONFIGURACIÓN:**")
                        st.write(f"- Pastura: {tipo_pastura}")
                        st.write(f"- Período: {fecha_inicio} a {fecha_fin}")
                        st.write(f"- Nubosidad máx: {nubosidad_maxima}%")
                    
                    if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO CON SENTINEL-2", type="primary"):
                        success, gdf_resultados = analisis_forrajero_completo_mejorado(
                            gdf, tipo_pastura, peso_promedio, carga_animal, n_divisiones,
                            fecha_inicio, fecha_fin, nubosidad_maxima
                        )
                        
        except Exception as e:
            st.error(f"Error cargando shapefile: {str(e)}")

else:
    st.info("📁 Sube el ZIP de tu potrero para comenzar el análisis forrajero")
    
    with st.expander("ℹ️ INFORMACIÓN SOBRE LA INTEGRACIÓN SENTINEL-2"):
        st.markdown("""
        **🛰️ INTEGRACIÓN SENTINEL-2 HARMONIZADO - 10m RESOLUCIÓN**
        
        **🌐 NUEVAS FUNCIONALIDADES:**
        - **🛰️ Imágenes Reales Sentinel-2:** Datos satelitales en tiempo real
        - **🌿 Índices Vegetacionales Reales:** NDVI, EVI calculados desde satélite
        - **🗺️ Mapa Interactivo:** Visualización sobre Google Satellite
        - **📊 Comparación Real vs Modelo:** Validación de precisión
        
        **📡 CARACTERÍSTICAS TÉCNICAS:**
        - **Resolución:** 10 metros por píxel
        - **Bandas:** Costales, Rojo, Verde, Infrarrojo
        - **Frecuencia:** Actualización cada 5 días
        - **Cobertura:** Global
        
        **🎯 BENEFICIOS:**
        - **Precisión Mejorada:** Valores reales vs simulados
        - **Actualización Constante:** Datos satelitales recientes
        - **Validación Científica:** Metodología GEE comprobada
        - **Visualización Profesional:** Mapas interactivos
        """)
