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
from utils.gee_utils import initialize_earth_engine, get_sentinel2_image, extract_satellite_values
from utils.mapping_utils import create_interactive_map
from utils.analysis_utils import calculate_area, divide_pasture, simulate_forage_analysis

# Page config
st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - METODOLOGÍA GEE")
st.markdown("---")

# Initialize session state - LA CLAVE PARA QUE EL MAPA NO DESAPAREZCA
if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False
if 'gdf_divided' not in st.session_state:
    st.session_state.gdf_divided = None
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None
if 'map_created' not in st.session_state:
    st.session_state.map_created = False

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
    n_divisiones = st.slider("Número de sub-lotes:", min_value=12, max_value=32, value=24)
    
    st.subheader("🛰️ Configuración Satelital")
    fecha_inicio = st.date_input("Fecha inicio análisis", value=datetime(2024, 1, 1))
    fecha_fin = st.date_input("Fecha fin análisis", value=datetime(2024, 12, 31))
    nubosidad_maxima = st.slider("Nubosidad máxima (%)", 0, 50, 20)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])

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
                    
                    # Botón para ejecutar análisis
                    if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO", type="primary"):
                        
                        # Paso 1: Dividir potrero
                        st.subheader("📐 DIVIDIENDO POTRERO")
                        gdf_dividido = divide_pasture(gdf, n_divisiones)
                        st.session_state.gdf_divided = gdf_dividido
                        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
                        
                        # Paso 2: Simular análisis
                        st.subheader("🌿 CALCULANDO ÍNDICES FORRAJEROS")
                        with st.spinner("Ejecutando análisis..."):
                            analysis_results = simulate_forage_analysis(gdf_dividido, tipo_pastura)
                            st.session_state.analysis_results = analysis_results
                        
                        st.session_state.analysis_complete = True
                        st.session_state.map_created = True
                        st.success("✅ Análisis completado")
                    
                    # Mostrar resultados si el análisis está completo
                    if st.session_state.analysis_complete and st.session_state.gdf_divided is not None:
                        
                        # Mostrar mapa interactivo - ESTA ES LA PARTE CLAVE
                        st.subheader("🗺️ MAPA INTERACTIVO - GOOGLE SATELLITE")
                        
                        # Crear mapa
                        mapa = create_interactive_map(
                            st.session_state.gdf_divided, 
                            None,  # No image for now
                            tipo_pastura, 
                            st.session_state.analysis_results
                        )
                        
                        # Mostrar mapa - USANDO KEY ÚNICA PARA EVITAR DESAPARICIÓN
                        if mapa and st.session_state.map_created:
                            # Usar una key única basada en el estado
                            map_key = f"map_{hash(str(st.session_state.analysis_complete))}"
                            st_folium(mapa, width=1200, height=600, key=map_key)
                        
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
                            st.metric("🗺️ Sub-lotes", len(st.session_state.gdf_divided))
                        
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
                        
                        # Información adicional
                        st.subheader("📊 PRÓXIMOS PASOS")
                        st.info("""
                        **Para habilitar el análisis completo con Sentinel-2:**
                        1. Ejecuta la aplicación localmente
                        2. Autentica con Google Earth Engine
                        3. Los datos satelitales reales estarán disponibles
                        """)
                        
        except Exception as e:
            st.error(f"Error cargando shapefile: {str(e)}")

else:
    st.info("📁 Sube el ZIP de tu potrero para comenzar el análisis forrajero")
    
    # Información de la aplicación
    with st.expander("ℹ️ INFORMACIÓN DE LA APLICACIÓN"):
        st.markdown("""
        **🌱 SISTEMA DE ANÁLISIS FORRAJERO**
        
        **Funcionalidades:**
        - 🗺️ Visualización de potreros
        - 📊 Análisis de biomasa
        - 🐄 Cálculo de capacidad ganadera
        - 🛰️ Integración con Sentinel-2 (local)
        
        **Requisitos:**
        - Shapefile del potrero en formato ZIP
        - Conexión a internet para datos satelitales
        - Ejecución local para Earth Engine
        
        **Instrucciones:**
        1. Prepara tu shapefile (.shp, .shx, .dbf, .prj)
        2. Comprímelo en un archivo ZIP
        3. Súbelo usando el botón arriba
        4. Configura los parámetros
        5. Ejecuta el análisis
        """)
