import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime
import matplotlib.pyplot as plt
import folium
from streamlit_folium import st_folium

# Page config - DEBE SER LA PRIMERA LÍNEA
st.set_page_config(
    page_title="🌱 Analizador Forrajero GEE", 
    page_icon="🌱",
    layout="wide"
)

st.title("🌱 ANALIZADOR FORRAJERO - METODOLOGÍA GEE")
st.markdown("---")

# Debug info
st.info("🚀 Aplicación cargada correctamente")

# Import utils
try:
    from utils.analysis_utils import calculate_area, divide_pasture, simulate_forage_analysis
    from utils.mapping_utils import create_interactive_map
    st.success("✅ Módulos utils cargados correctamente")
except ImportError as e:
    st.error(f"❌ Error cargando módulos: {e}")
    # Definir funciones básicas como fallback
    def calculate_area(gdf):
        return gdf.geometry.area / 10000
    
    def divide_pasture(gdf, n_zones):
        return gdf
    
    def simulate_forage_analysis(gdf, pasture_type):
        return [{'biomasa_disponible_kg_ms_ha': 500, 'ndvi': 0.5, 'tipo_superficie': 'TEST'}] * len(gdf)
    
    def create_interactive_map(gdf, img, pasture, results):
        return folium.Map(location=[-34.0, -64.0], zoom_start=10)

# Initialize session state
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False
if 'gdf_divided' not in st.session_state:
    st.session_state.gdf_divided = None
if 'results' not in st.session_state:
    st.session_state.results = None

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    tipo_pastura = st.selectbox("Tipo de Pastura:", 
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=4, max_value=36, value=16)
    
    st.subheader("🛰️ Configuración Satelital")
    fecha_inicio = st.date_input("Fecha inicio análisis", value=datetime(2024, 1, 1))
    fecha_fin = st.date_input("Fecha fin análisis", value=datetime(2024, 12, 31))
    nubosidad_maxima = st.slider("Nubosidad máxima (%)", 0, 50, 20)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])

# Main application
if uploaded_zip:
    st.success("📁 Archivo ZIP cargado - Procesando...")
    
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
                    with st.spinner("Dividiendo potrero..."):
                        gdf_dividido = divide_pasture(gdf, n_divisiones)
                        st.session_state.gdf_divided = gdf_dividido
                    
                    st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
                    
                    # Paso 2: Simular análisis
                    with st.spinner("Calculando índices forrajeros..."):
                        analysis_results = simulate_forage_analysis(gdf_dividido, tipo_pastura)
                        st.session_state.results = analysis_results
                    
                    st.session_state.analysis_done = True
                    st.success("✅ Análisis completado")
                    st.rerun()
                
                # Mostrar resultados si el análisis está hecho
                if st.session_state.analysis_done and st.session_state.gdf_divided is not None:
                    
                    # Mostrar mapa interactivo
                    st.subheader("🗺️ MAPA INTERACTIVO - GOOGLE SATELLITE")
                    
                    # Crear mapa
                    mapa = create_interactive_map(
                        st.session_state.gdf_divided, 
                        None,
                        tipo_pastura, 
                        st.session_state.results
                    )
                    
                    # Mostrar mapa
                    if mapa:
                        st_folium(mapa, width=1200, height=600, key="main_map")
                    
                    # Mostrar resumen
                    st.subheader("📊 RESULTADOS DEL ANÁLISIS")
                    
                    biomasas = [r['biomasa_disponible_kg_ms_ha'] for r in st.session_state.results]
                    ndvis = [r['ndvi'] for r in st.session_state.results]
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Biomasa Promedio", f"{np.mean(biomasas):.0f} kg MS/ha")
                    with col2:
                        st.metric("NDVI Promedio", f"{np.mean(ndvis):.3f}")
                    with col3:
                        st.metric("Sub-lotes", len(st.session_state.gdf_divided))
                    
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")

else:
    st.info("📁 Sube el ZIP de tu potrero para comenzar el análisis forrajero")
