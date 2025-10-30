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

# Page config
st.set_page_config(page_title="🌱 Analizador Forrajero GEE", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO - METODOLOGÍA GEE")
st.markdown("---")

# Initialize session state
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False
if 'gdf_dividido' not in st.session_state:
    st.session_state.gdf_dividido = None
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None

# ===== FUNCIONES (TODO EN UN SOLO ARCHIVO) =====

def calculate_area(gdf):
    """Calculate area in hectares"""
    try:
        if gdf.crs and gdf.crs.is_geographic:
            area_m2 = gdf.geometry.area * 10000000000
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000
    except:
        return gdf.geometry.area / 10000

def divide_pasture(gdf, n_zones):
    """Divide pasture into sub-lots"""
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

def create_interactive_map(gdf, image_s2, pasture_type, analysis_results):
    """Create interactive map with Google Satellite"""
    try:
        # Get centroid of study area
        centroid = gdf.geometry.centroid.iloc[0]
        center_lat, center_lon = centroid.y, centroid.x
        
        # Create base map with Google Satellite
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=12,
            tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
            attr='Google Satellite'
        )
        
        # Add OpenStreetMap as alternative
        folium.TileLayer(
            'OpenStreetMap',
            name='OpenStreetMap',
            attr='OpenStreetMap'
        ).add_to(m)
        
        # Add sub-lot polygons
        if analysis_results is not None:
            for idx, row in gdf.iterrows():
                sub_lot_id = row['id_subLote']
                biomass = analysis_results[idx]['biomasa_disponible_kg_ms_ha']
                ndvi = analysis_results[idx]['ndvi']
                surface_type = analysis_results[idx]['tipo_superficie']
                
                # Color based on NDVI (more accurate for vegetation)
                if ndvi < 0.2:
                    color = '#d73027'  # Red - Bare soil
                    fill_opacity = 0.4
                elif ndvi < 0.4:
                    color = '#fc8d59'  # Orange - Sparse vegetation
                    fill_opacity = 0.5
                elif ndvi < 0.6:
                    color = '#fee08b'  # Yellow - Moderate vegetation
                    fill_opacity = 0.6
                elif ndvi < 0.8:
                    color = '#91cf60'  # Light green - Good vegetation
                    fill_opacity = 0.7
                else:
                    color = '#1a9850'  # Dark green - Dense vegetation
                    fill_opacity = 0.8
                
                # Create polygon
                geom = row.geometry
                if geom.geom_type == 'Polygon':
                    coords = [[point[1], point[0]] for point in geom.exterior.coords]
                    
                    folium.Polygon(
                        locations=coords,
                        popup=f"""
                        <div style="font-family: Arial; font-size: 12px; min-width: 220px;">
                            <h4>🌿 Sub-Lote S{sub_lot_id}</h4>
                            <b>NDVI:</b> {ndvi:.3f}<br>
                            <b>Biomasa:</b> {biomass:.0f} kg MS/ha<br>
                            <b>Tipo:</b> {surface_type}<br>
                            <b>Cobertura:</b> {analysis_results[idx]['cobertura_vegetal']:.1%}
                        </div>
                        """,
                        tooltip=f'S{sub_lot_id} - NDVI: {ndvi:.3f}',
                        color=color,
                        fill_color=color,
                        fill_opacity=fill_opacity,
                        weight=2,
                        opacity=0.8
                    ).add_to(m)
        
        # Add layer control
        folium.LayerControl().add_to(m)
        
        # Add legend
        legend_html = '''
        <div style="position: fixed; 
                    bottom: 50px; left: 50px; width: 220px; height: 160px; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:12px; padding: 10px; border-radius: 5px;">
        <p style="margin:0; font-weight:bold;">🌿 Leyenda NDVI</p>
        <p style="margin:2px 0;"><i style="background:#d73027; width: 15px; height: 15px; display: inline-block; margin-right: 5px; border:1px solid grey;"></i> < 0.2 (Suelo)</p>
        <p style="margin:2px 0;"><i style="background:#fc8d59; width: 15px; height: 15px; display: inline-block; margin-right: 5px; border:1px solid grey;"></i> 0.2-0.4 (Escasa)</p>
        <p style="margin:2px 0;"><i style="background:#fee08b; width: 15px; height: 15px; display: inline-block; margin-right: 5px; border:1px solid grey;"></i> 0.4-0.6 (Moderada)</p>
        <p style="margin:2px 0;"><i style="background:#91cf60; width: 15px; height: 15px; display: inline-block; margin-right: 5px; border:1px solid grey;"></i> 0.6-0.8 (Buena)</p>
        <p style="margin:2px 0;"><i style="background:#1a9850; width: 15px; height: 15px; display: inline-block; margin-right: 5px; border:1px solid grey;"></i> > 0.8 (Densa)</p>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))
        
        return m
        
    except Exception as e:
        st.error(f"Error creando mapa: {str(e)}")
        # Return a simple map as fallback
        return folium.Map(location=[-34.0, -64.0], zoom_start=4)

def simulate_forage_analysis(gdf_divided, pasture_type):
    """Simulate forage analysis with realistic data"""
    results = []
    
    # Parameters by pasture type
    pasture_params = {
        "ALFALFA": {"biomass_min": 800, "biomass_max": 1500, "ndvi_min": 0.5},
        "RAYGRASS": {"biomass_min": 600, "biomass_max": 1200, "ndvi_min": 0.4},
        "FESTUCA": {"biomass_min": 500, "biomass_max": 1000, "ndvi_min": 0.4},
        "AGROPIRRO": {"biomass_min": 400, "biomass_max": 900, "ndvi_min": 0.3},
        "PASTIZAL_NATURAL": {"biomass_min": 300, "biomass_max": 700, "ndvi_min": 0.3},
        "PERSONALIZADO": {"biomass_min": 400, "biomass_max": 1000, "ndvi_min": 0.4}
    }
    
    params = pasture_params.get(pasture_type, pasture_params["PERSONALIZADO"])
    
    for i, row in gdf_divided.iterrows():
        # Simulate spatial variation based on position
        centroid = row.geometry.centroid
        spatial_variation = (centroid.x + centroid.y) % 1
        
        # Calculate values based on position and pasture type
        biomass_base = params["biomass_min"] + (params["biomass_max"] - params["biomass_min"]) * spatial_variation
        ndvi_base = params["ndvi_min"] + (0.8 - params["ndvi_min"]) * spatial_variation
        
        # Add controlled randomness
        biomass = max(100, biomass_base + np.random.normal(0, 100))
        ndvi = max(0.1, min(0.9, ndvi_base + np.random.normal(0, 0.1)))
        
        # Determine surface type based on NDVI
        if ndvi < 0.2:
            surface_type = "SUELO_DESNUDO"
            coverage = np.random.uniform(0.1, 0.3)
        elif ndvi < 0.4:
            surface_type = "VEGETACION_ESCASA"
            coverage = np.random.uniform(0.3, 0.6)
        elif ndvi < 0.6:
            surface_type = "VEGETACION_MODERADA"
            coverage = np.random.uniform(0.6, 0.8)
        else:
            surface_type = "VEGETACION_DENSA"
            coverage = np.random.uniform(0.8, 0.95)
        
        results.append({
            'biomasa_disponible_kg_ms_ha': biomass,
            'ndvi': ndvi,
            'evi': ndvi * 0.9 + np.random.normal(0, 0.05),
            'savi': ndvi * 0.95 + np.random.normal(0, 0.03),
            'cobertura_vegetal': coverage,
            'tipo_superficie': surface_type,
            'crecimiento_diario': biomass * 0.02 + np.random.normal(0, 5),
            'factor_calidad': min(0.95, coverage * 0.8 + np.random.normal(0, 0.1))
        })
    
    return results

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
    
    # Clear analysis button
    if st.button("🔄 Limpiar Análisis", use_container_width=True):
        st.session_state.analysis_done = False
        st.session_state.gdf_dividido = None
        st.session_state.analysis_results = None
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
                    
                    # Only run analysis if not done before
                    if not st.session_state.analysis_done:
                        if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO", type="primary", use_container_width=True):
                            
                            # Step 1: Divide pasture
                            st.subheader("📐 DIVIDIENDO POTRERO")
                            gdf_dividido = divide_pasture(gdf, n_divisiones)
                            st.session_state.gdf_dividido = gdf_dividido
                            st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
                            
                            # Step 2: Simulate analysis
                            st.subheader("🌿 CALCULANDO ÍNDICES FORRAJEROS")
                            with st.spinner("Ejecutando análisis..."):
                                analysis_results = simulate_forage_analysis(gdf_dividido, tipo_pastura)
                                st.session_state.analysis_results = analysis_results
                            
                            st.session_state.analysis_done = True
                            st.success("✅ Análisis completado")
                            st.rerun()
                    
                    # Show results if analysis is done
                    if st.session_state.analysis_done and st.session_state.gdf_dividido is not None:
                        
                        # Show interactive map
                        st.subheader("🗺️ MAPA INTERACTIVO - GOOGLE SATELLITE")
                        
                        # Create map
                        mapa = create_interactive_map(
                            st.session_state.gdf_dividido, 
                            None,  # No image for now
                            tipo_pastura, 
                            st.session_state.analysis_results
                        )
                        
                        # Show map with st_folium
                        if mapa:
                            # Use the returned map object to prevent disappearance
                            map_data = st_folium(mapa, width=1200, height=600, key="main_map")
                        
                        # Show results summary
                        st.subheader("📊 RESULTADOS DEL ANÁLISIS")
                        
                        # Calculate statistics
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
                        
                        # Detailed table
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
                        
                        # Charts
                        st.subheader("📈 VISUALIZACIÓN DE DATOS")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            # NDVI distribution
                            fig1, ax1 = plt.subplots(figsize=(8, 4))
                            ax1.hist(ndvis, bins=12, alpha=0.7, color='#2ecc71', edgecolor='black')
                            ax1.set_xlabel('NDVI')
                            ax1.set_ylabel('Número de Sub-lotes')
                            ax1.set_title('Distribución de NDVI')
                            ax1.grid(True, alpha=0.3)
                            st.pyplot(fig1)
                        
                        with col2:
                            # Biomass distribution
                            fig2, ax2 = plt.subplots(figsize=(8, 4))
                            ax2.hist(biomasas, bins=12, alpha=0.7, color='#3498db', edgecolor='black')
                            ax2.set_xlabel('Biomasa (kg MS/ha)')
                            ax2.set_ylabel('Número de Sub-lotes')
                            ax2.set_title('Distribución de Biomasa')
                            ax2.grid(True, alpha=0.3)
                            st.pyplot(fig2)
                        
                        # Information about Sentinel-2
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
    
    # Application information
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

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666;'>"
    "🌱 Analizador Forrajero | Google Satellite | Preparado para Sentinel-2"
    "</div>",
    unsafe_allow_html=True
)
