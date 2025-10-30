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
from shapely.geometry import Polygon
import math

# Page config - DEBE SER LA PRIMERA LÍNEA
st.set_page_config(
    page_title="🌱 Analizador Forrajero GEE", 
    page_icon="🌱",
    layout="wide"
)

st.title("🌱 ANALIZADOR FORRAJERO - METODOLOGÍA GEE")
st.markdown("---")

# Importar módulos de forma segura
try:
    from utils.analysis_utils import calculate_area, divide_pasture, simulate_forage_analysis
    from utils.mapping_utils import create_interactive_map
    st.success("✅ Módulos cargados correctamente")
except ImportError as e:
    st.error(f"❌ Error cargando módulos: {e}")
    
    # Definir funciones básicas como fallback
    def calculate_area(gdf):
        try:
            if gdf.crs and gdf.crs.is_geographic:
                area_m2 = gdf.geometry.area * 10000000000
            else:
                area_m2 = gdf.geometry.area
            return area_m2 / 10000
        except:
            return gdf.geometry.area / 10000

    def divide_pasture(gdf, n_zones):
        if len(gdf) == 0:
            return gdf
        
        main_pasture = gdf.iloc[0].geometry
        bounds = main_pasture.bounds
        minx, miny, maxx, maxy = bounds
        
        sub_polygons = []
        n_cols = math.ceil(math.sqrt(n_zones))
        n_rows = math.ceil(n_zones / n_cols)
        width = (maxx - minx) / n_cols
        height = (maxy - miny) / n_rows
        
        for i in range(n_rows):
            for j in range(n_cols):
                if len(sub_polygons) >= n_zones:
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
                
                intersection = main_pasture.intersection(cell_poly)
                if not intersection.is_empty and intersection.area > 0:
                    sub_polygons.append(intersection)
        
        if sub_polygons:
            new_gdf = gpd.GeoDataFrame({
                'id_subLote': range(1, len(sub_polygons) + 1),
                'geometry': sub_polygons
            }, crs=gdf.crs)
            return new_gdf
        else:
            return gdf

    def simulate_forage_analysis(gdf_divided, pasture_type):
        results = []
        for i in range(len(gdf_divided)):
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
            
            if ndvi < 0.3:
                surface_type = "SUELO_DESNUDO"
            elif ndvi < 0.6:
                surface_type = "VEGETACION_MODERADA"
            else:
                surface_type = "VEGETACION_DENSA"
            
            results.append({
                'biomasa_disponible_kg_ms_ha': biomass,
                'ndvi': ndvi,
                'tipo_superficie': surface_type
            })
        return results

    def create_interactive_map(gdf, image_s2, pasture_type, analysis_results):
        try:
            centroid = gdf.geometry.centroid.iloc[0]
            center_lat, center_lon = centroid.y, centroid.x
            
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=12,
                tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                attr='Google Satellite'
            )
            
            for idx, row in gdf.iterrows():
                sub_lot_id = row['id_subLote']
                biomass = analysis_results[idx]['biomasa_disponible_kg_ms_ha']
                ndvi = analysis_results[idx]['ndvi']
                
                if biomass < 200:
                    color = 'red'
                elif biomass < 400:
                    color = 'orange'
                elif biomass < 600:
                    color = 'yellow'
                elif biomass < 800:
                    color = 'lightgreen'
                else:
                    color = 'darkgreen'
                
                geom = row.geometry
                if geom.geom_type == 'Polygon':
                    coords = [[point[1], point[0]] for point in geom.exterior.coords]
                    
                    folium.Polygon(
                        locations=coords,
                        popup=f"Sub-Lote {sub_lot_id}<br>Biomasa: {biomass} kg/ha<br>NDVI: {ndvi}",
                        color=color,
                        fill_color=color,
                        fill_opacity=0.3,
                        weight=2
                    ).add_to(m)
            
            return m
        except Exception as e:
            return folium.Map(location=[-34.0, -64.0], zoom_start=4)

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
                        
                        # Paso 2: Simular análisis
                        st.subheader("🌿 SIMULANDO ANÁLISIS")
                        
                        example_results = simulate_forage_analysis(gdf_dividido, tipo_pastura)
                        
                        # Mostrar mapa interactivo
                        st.subheader("🗺️ MAPA INTERACTIVO")
                        
                        mapa = create_interactive_map(
                            gdf_dividido, 
                            None,
                            tipo_pastura, 
                            example_results
                        )
                        
                        # Mostrar mapa
                        if mapa:
                            returned_data = st_folium(mapa, width=1200, height=600)
                        
                        # Información adicional
                        st.subheader("📊 RESULTADOS")
                        
                        biomasas = [r['biomasa_disponible_kg_ms_ha'] for r in example_results]
                        ndvis = [r['ndvi'] for r in example_results]
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Biomasa Promedio", f"{np.mean(biomasas):.0f} kg/ha")
                        with col2:
                            st.metric("NDVI Promedio", f"{np.mean(ndvis):.3f}")
                        with col3:
                            st.metric("Sub-lotes", len(gdf_dividido))
                        
        except Exception as e:
            st.error(f"Error cargando shapefile: {str(e)}")

else:
    st.info("📁 Sube el ZIP de tu potrero para comenzar el análisis forrajero")
    
    with st.expander("ℹ️ INFORMACIÓN DE LA APLICACIÓN"):
        st.markdown("""
        **🌱 SISTEMA DE ANÁLISIS FORRAJERO**
        
        **Funcionalidades:**
        - 🗺️ Visualización de potreros
        - 📊 Análisis de biomasa
        - 🐄 Cálculo de capacidad ganadera
        - 🛰️ Integración con Sentinel-2 (local)
        
        **Instrucciones:**
        1. Prepara tu shapefile (.shp, .shx, .dbf, .prj)
        2. Comprímelo en un archivo ZIP
        3. Súbelo usando el botón arriba
        4. Configura los parámetros
        5. Ejecuta el análisis
        """)
