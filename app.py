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

# Page config - ESTO DEBE IR PRIMERO
st.set_page_config(
    page_title="🌱 Analizador Forrajero",
    page_icon="🌱", 
    layout="wide"
)

st.title("🌱 ANALIZADOR FORRAJERO CON SENTINEL-2")
st.markdown("---")

# Import functions from utils
from utils.analysis_utils import calculate_area, divide_pasture

# Simple forage analysis simulation
def simulate_forage_analysis(gdf_divided, pasture_type):
    results = []
    for i in range(len(gdf_divided)):
        # Simple simulation based on pasture type
        if pasture_type == "ALFALFA":
            biomass = np.random.uniform(800, 1500)
            ndvi = np.random.uniform(0.5, 0.9)
        elif pasture_type == "RAYGRASS":
            biomass = np.random.uniform(600, 1200)
            ndvi = np.random.uniform(0.4, 0.8)
        elif pasture_type == "FESTUCA":
            biomass = np.random.uniform(500, 1000)
            ndvi = np.random.uniform(0.4, 0.8)
        else:
            biomass = np.random.uniform(400, 900)
            ndvi = np.random.uniform(0.3, 0.7)
        
        # Determine surface type
        if ndvi < 0.3:
            surface_type = "SUELO_DESNUDO"
            coverage = np.random.uniform(0.1, 0.3)
        elif ndvi < 0.6:
            surface_type = "VEGETACION_MODERADA"
            coverage = np.random.uniform(0.4, 0.7)
        else:
            surface_type = "VEGETACION_DENSA"
            coverage = np.random.uniform(0.7, 0.95)
        
        results.append({
            'biomasa_disponible_kg_ms_ha': biomass,
            'ndvi': ndvi,
            'cobertura_vegetal': coverage,
            'tipo_superficie': surface_type
        })
    return results

# Simple map creation
def create_simple_map(gdf, analysis_results):
    try:
        centroid = gdf.geometry.centroid.iloc[0]
        center_lat, center_lon = centroid.y, centroid.x
        
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=12
        )
        
        for idx, row in gdf.iterrows():
            sub_lot_id = row['id_subLote']
            biomass = analysis_results[idx]['biomasa_disponible_kg_ms_ha']
            ndvi = analysis_results[idx]['ndvi']
            
            # Simple color coding
            if ndvi < 0.3:
                color = 'red'
            elif ndvi < 0.6:
                color = 'orange'
            else:
                color = 'green'
            
            geom = row.geometry
            if geom.geom_type == 'Polygon':
                coords = [[point[1], point[0]] for point in geom.exterior.coords]
                
                folium.Polygon(
                    locations=coords,
                    popup=f"S{sub_lot_id}<br>Biomasa: {biomass:.0f} kg/ha<br>NDVI: {ndvi:.3f}",
                    color=color,
                    fill_color=color,
                    fill_opacity=0.5
                ).add_to(m)
        
        return m
    except Exception as e:
        return folium.Map(location=[-34.0, -64.0], zoom_start=4)

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
                    mapa = create_simple_map(gdf_dividido, resultados)
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
                    
                    # Simple table
                    df = pd.DataFrame({
                        'Sub-Lote': range(1, len(resultados) + 1),
                        'Biomasa (kg/ha)': [f"{r['biomasa_disponible_kg_ms_ha']:.0f}" for r in resultados],
                        'NDVI': [f"{r['ndvi']:.3f}" for r in resultados],
                        'Tipo': [r['tipo_superficie'] for r in resultados]
                    })
                    st.dataframe(df)
    
    except Exception as e:
        st.error(f"Error: {str(e)}")

else:
    st.info("📁 Sube un archivo ZIP con shapefile para comenzar")
    st.markdown("""
    ### 🌟 Características:
    - Análisis de biomasa forrajera
    - División automática en sub-lotes  
    - Visualización en mapa interactivo
    - Preparado para datos Sentinel-2
    """)
