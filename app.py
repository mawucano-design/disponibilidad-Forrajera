import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime
import matplotlib.pyplot as plt
import io
from shapely.geometry import Polygon
import math
import folium
from streamlit_folium import st_folium

# Import utils
from utils.analysis_utils import calculate_area, divide_pasture, simulate_forage_analysis
from utils.mapping_utils import create_interactive_map
from utils.gee_utils import initialize_earth_engine, get_sentinel2_image, extract_satellite_values

# Page config
st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - METODOLOGÍA GEE")
st.markdown("---")

# Initialize session state - ESTA ES LA PARTE CLAVE QUE FALTABA
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False
if 'gdf_dividido' not in st.session_state:
    st.session_state.gdf_dividido = None
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None
if 'map_key' not in st.session_state:
    st.session_state.map_key = 0

# Initialize Earth Engine (commented for now to avoid errors)
# gee_initialized = initialize_earth_engine()

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    tipo_pastura = st.selectbox("Tipo de Pastura:", 
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=8, max_value=36, value=16, step=4)
    
    st.subheader("🛰️ Configuración Satelital")
    fecha_inicio = st.date_input("Fecha inicio análisis", value=datetime(2024, 1, 1))
    fecha_fin = st.date_input("Fecha fin análisis", value=datetime(2024, 12, 31))
    nubosidad_maxima = st.slider("Nubosidad máxima (%)", 0, 50, 20)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])
    
    # Botón para limpiar análisis - IMPORTANTE PARA EL MANEJO DE ESTADO
    if st.button("🔄 Limpiar Análisis", use_container_width=True):
        st.session_state.analysis_done = False
        st.session_state.gdf_dividido = None
        st.session_state.analysis_results = None
        st.session_state.map_key += 1  # Force map refresh
        st.rerun()

# Main application
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
                    
                    area_total = calculate_area(gdf).sum()
                    
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
                        st.write(f"- Sub-lotes: {n_divisiones}")
                    
                    # Solo ejecutar análisis si no se ha hecho antes
                    if not st.session_state.analysis_done:
                        if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO", type="primary", use_container_width=True):
                            
                            # Paso 1: Dividir potrero
                            st.subheader("📐 DIVIDIENDO POTRERO")
                            gdf_dividido = divide_pasture(gdf, n_divisiones)
                            st.session_state.gdf_dividido = gdf_dividido
                            st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
                            
                            # Paso 2: Simular análisis
                            st.subheader("🌿 CALCULANDO ÍNDICES FORRAJEROS")
                            with st.spinner("Ejecutando análisis..."):
                                analysis_results = simulate_forage_analysis(gdf_dividido, tipo_pastura)
                                st.session_state.analysis_results = analysis_results
                            
                            st.session_state.analysis_done = True
                            st.success("✅ Análisis completado")
                            st.rerun()
                    
                    # Mostrar resultados si el análisis está hecho - ESTA PARTE SE MANTIENE EN EL ESTADO
                    if st.session_state.analysis_done and st.session_state.gdf_dividido is not None:
                        
                        # Mostrar mapa interactivo
                        st.subheader("🗺️ MAPA INTERACTIVO - GOOGLE SATELLITE")
                        
                        # Crear mapa
                        mapa = create_interactive_map(
                            st.session_state.gdf_dividido, 
                            None,  # No image for now
                            tipo_pastura, 
                            st.session_state.analysis_results
                        )
                        
                        # Mostrar mapa con st_folium - USANDO KEY ÚNICA PARA EVITAR DESAPARICIÓN
                        if mapa:
                            st_folium(mapa, width=1200, height=600, key=f"main_map_{st.session_state.map_key}")
                        
                        # Mostrar resumen de resultados
                        st.subheader("📊 RESULTADOS DEL ANÁLISIS")
                        
                        # Calcular estadísticas
                        biomasas = [r['biomasa_disponible_kg_ms_ha'] for r in st.session_state.analysis_results]
                        ndvis = [r['ndvi'] for r in st.session_state.analysis_results]
                        coberturas = [r['cobertura_vegetal'] for r in st.session_state.analysis_results]
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("🌿 NDVI Promedio", f"{np.mean(ndvis):.3f}")
                        with col2:
                            st.metric("📈 Biomasa Promedio", f"{np.mean(biomasas):.0f} kg MS/ha")
                        with col3:
                            st.metric("🟢 Cobertura Promedio", f"{np.mean(coberturas):.1%}")
                        with col4:
                            st.metric("🗺️ Sub-lotes", len(st.session_state.gdf_dividido))
                        
                        # Tabla de resultados detallados
                        st.subheader("📋 DETALLE POR SUB-LOTE")
                        
                        df_resultados = pd.DataFrame({
                            'Sub-Lote': range(1, len(st.session_state.analysis_results) + 1),
                            'Biomasa (kg MS/ha)': [f"{r['biomasa_disponible_kg_ms_ha']:.0f}" for r in st.session_state.analysis_results],
                            'NDVI': [f"{r['ndvi']:.3f}" for r in st.session_state.analysis_results],
                            'Cobertura': [f"{r['cobertura_vegetal']:.1%}" for r in st.session_state.analysis_results],
                            'Tipo Superficie': [r['tipo_superficie'] for r in st.session_state.analysis_results],
                            'Crecimiento (kg/día)': [f"{r['crecimiento_diario']:.1f}" for r in st.session_state.analysis_results]
                        })
                        
                        st.dataframe(df_resultados, use_container_width=True)
                        
                        # Gráficos
                        st.subheader("📈 VISUALIZACIÓN DE DATOS")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            # Distribución de NDVI
                            fig1, ax1 = plt.subplots(figsize=(8, 4))
                            ax1.hist(ndvis, bins=12, alpha=0.7, color='#2ecc71', edgecolor='black')
                            ax1.set_xlabel('NDVI')
                            ax1.set_ylabel('Número de Sub-lotes')
                            ax1.set_title('Distribución de NDVI')
                            ax1.grid(True, alpha=0.3)
                            st.pyplot(fig1)
                        
                        with col2:
                            # Distribución de Biomasa
                            fig2, ax2 = plt.subplots(figsize=(8, 4))
                            ax2.hist(biomasas, bins=12, alpha=0.7, color='#3498db', edgecolor='black')
                            ax2.set_xlabel('Biomasa (kg MS/ha)')
                            ax2.set_ylabel('Número de Sub-lotes')
                            ax2.set_title('Distribución de Biomasa')
                            ax2.grid(True, alpha=0.3)
                            st.pyplot(fig2)
                        
                        # Información sobre Sentinel-2
                        st.subheader("🛰️ INFORMACIÓN SOBRE SENTINEL-2")
                        st.info("""
                        **Para habilitar el análisis con Sentinel-2 real:**
                        1. Ejecuta la aplicación localmente
                        2. Instala: `pip install earthengine-api geemap`
                        3. Autentica con: `earthengine authenticate`
                        4. Los datos satelitales reales estarán disponibles
                        
                        **Características de Sentinel-2 Harmonized:**
                        - Resolución: 10 metros
                        - Índices: NDVI, EVI, SAVI en tiempo real
                        - Frecuencia: Actualización cada 5 días
                        - Cobertura: Global
                        """)
                        
        except Exception as e:
            st.error(f"Error cargando shapefile: {str(e)}")

else:
    st.info("📁 Sube el ZIP de tu potrero para comenzar el análisis forrajero")
    
    # Información de la aplicación
    with st.expander("ℹ️ INFORMACIÓN DE LA APLICACIÓN"):
        st.markdown("""
        **🌱 SISTEMA DE ANÁLISIS FORRAJERO CON GOOGLE SATELLITE**
        
        **Funcionalidades:**
        - 🗺️ **Google Satellite** - Mapa base de alta resolución
        - 📊 **Análisis de biomasa** - Estimación de productividad
        - 🌿 **Índices de vegetación** - NDVI, cobertura vegetal
        - 🐄 **Capacidad ganadera** - Cálculo de equivalentes vaca
        - 🛰️ **Preparado para Sentinel-2** - Estructura para datos reales
        
        **Características del mapa:**
        - **Google Satellite** como base
        - **Polígonos interactivos** con información detallada
        - **Leyenda NDVI** integrada
        - **Control de capas** para alternar entre mapas
        
        **Instrucciones:**
        1. Prepara tu shapefile (.shp, .shx, .dbf, .prj)
        2. Comprímelo en un archivo ZIP
        3. Súbelo usando el botón arriba
        4. Configura los parámetros
        5. Ejecuta el análisis
        6. Explora el mapa satelital interactivo
        """)
