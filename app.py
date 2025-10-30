import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime
import folium
from streamlit_folium import st_folium

# Page config - DEBE SER LO PRIMERO
st.set_page_config(
    page_title="🌱 Analizador Forrajero",
    page_icon="🌱",
    layout="wide"
)

st.title("🌱 ANALIZADOR FORRAJERO")
st.markdown("---")

# Import functions
try:
    from utils.analysis_utils import calculate_area, divide_pasture, simulate_forage_analysis
    from utils.mapping_utils import create_interactive_map
except ImportError as e:
    st.error(f"Error importing modules: {e}")

# Sidebar
with st.sidebar:
    st.header("Configuración")
    
    tipo_pastura = st.selectbox(
        "Tipo de Pastura:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL"]
    )
    
    n_divisiones = st.slider("Número de sub-lotes:", 4, 24, 12)
    
    uploaded_zip = st.file_uploader("Subir shapefile (ZIP)", type=['zip'])

# Main app
if uploaded_zip:
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)
            
            shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
            if shp_files:
                shp_path = os.path.join(tmp_dir, shp_files[0])
                gdf = gpd.read_file(shp_path)
                
                st.success(f"✅ Potrero cargado: {len(gdf)} polígono(s)")
                
                area_total = calculate_area(gdf).sum()
                st.write(f"**Área total:** {area_total:.1f} ha")
                
                if st.button("🚀 Ejecutar Análisis"):
                    # Divide pasture
                    gdf_dividido = divide_pasture(gdf, n_divisiones)
                    st.success(f"✅ Dividido en {len(gdf_dividido)} sub-lotes")
                    
                    # Simulate analysis
                    resultados = simulate_forage_analysis(gdf_dividido, tipo_pastura)
                    
                    # Show map
                    st.subheader("🗺️ Mapa del Potrero")
                    mapa = create_interactive_map(gdf_dividido, None, tipo_pastura, resultados)
                    st_folium(mapa, width=1000, height=500)
                    
                    # Show results
                    st.subheader("📊 Resultados")
                    
                    biomasas = [r['biomasa_disponible_kg_ms_ha'] for r in resultados]
                    ndvis = [r['ndvi'] for r in resultados]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Biomasa Promedio", f"{np.mean(biomasas):.0f} kg/ha")
                    with col2:
                        st.metric("NDVI Promedio", f"{np.mean(ndvis):.3f}")
    
    except Exception as e:
        st.error(f"Error: {str(e)}")

else:
    st.info("📁 Sube un archivo ZIP con shapefile para comenzar")
