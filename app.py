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

# Import utils
from utils.gee_utils import initialize_earth_engine, get_sentinel2_image, extract_satellite_values
from utils.mapping_utils import create_interactive_map
from utils.analysis_utils import calculate_area, divide_pasture

# Page config
st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - METODOLOGÍA GEE")
st.markdown("---")

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
                    
                    if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO", type="primary"):
                        
                        # Paso 1: Dividir potrero
                        st.subheader("📐 DIVIDIENDO POTRERO")
                        gdf_dividido = divide_pasture(gdf, n_divisiones)
                        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
                        
                        # Paso 2: Simular análisis (por ahora)
                        st.subheader("🌿 SIMULANDO ANÁLISIS")
                        
                        # Aquí iría tu lógica de análisis existente
                        # Por ahora mostramos un ejemplo básico
                        
                        # Mostrar mapa interactivo
                        st.subheader("🗺️ MAPA INTERACTIVO")
                        
                        # Crear datos de ejemplo para el mapa
                        example_results = []
                        for i in range(len(gdf_dividido)):
                            example_results.append({
                                'biomasa_disponible_kg_ms_ha': np.random.uniform(100, 800),
                                'ndvi': np.random.uniform(0.2, 0.8),
                                'tipo_superficie': 'VEGETACION_MODERADA'
                            })
                        
                        # Crear mapa
                        mapa = create_interactive_map(
                            gdf_dividido, 
                            None,  # No image for now
                            tipo_pastura, 
                            example_results
                        )
                        
                        # Mostrar mapa
                        if mapa:
                            st_folium(mapa, width=1200, height=600)
                        
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
