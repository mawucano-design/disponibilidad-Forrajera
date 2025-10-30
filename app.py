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

# Import st_folium
from streamlit_folium import st_folium
import folium

# Page config
st.set_page_config(page_title="🌱 Analizador Forrajero", layout="wide")
st.title("🌱 ANALIZADOR FORRAJERO")
st.markdown("---")

# Initialize session state
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False
if 'gdf_dividido' not in st.session_state:
    st.session_state.gdf_dividido = None
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None

# Funciones auxiliares
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

def create_interactive_map(gdf, pasture_type, analysis_results):
    """Create interactive map"""
    try:
        # Get centroid of study area
        centroid = gdf.geometry.centroid.iloc[0]
        center_lat, center_lon = centroid.y, centroid.x
        
        # Create base map
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=12
        )
        
        # Add sub-lot polygons
        if analysis_results is not None:
            for idx, row in gdf.iterrows():
                sub_lot_id = row['id_subLote']
                biomass = analysis_results[idx]['biomasa_disponible_kg_ms_ha']
                
                # Color based on biomass
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
                
                # Create polygon
                geom = row.geometry
                if geom.geom_type == 'Polygon':
                    coords = [[point[1], point[0]] for point in geom.exterior.coords]
                    
                    folium.Polygon(
                        locations=coords,
                        popup=f"""
                        <b>Sub-Lote S{sub_lot_id}</b><br>
                        Biomasa: {biomass} kg MS/ha<br>
                        NDVI: {analysis_results[idx]['ndvi']:.3f}<br>
                        Tipo: {analysis_results[idx]['tipo_superficie']}
                        """,
                        tooltip=f'S{sub_lot_id} - {biomass} kg MS/ha',
                        color=color,
                        fill_color=color,
                        fill_opacity=0.5,
                        weight=2
                    ).add_to(m)
        
        return m
        
    except Exception as e:
        st.error(f"Error creando mapa: {str(e)}")
        # Return a simple map as fallback
        return folium.Map(location=[-34.0, -64.0], zoom_start=4)

def simular_analisis_forrajero(gdf_dividido, tipo_pastura):
    """Simula el análisis forrajero"""
    resultados = []
    for i in range(len(gdf_dividido)):
        # Simular datos basados en el tipo de pastura
        if tipo_pastura == "ALFALFA":
            biomasa_base = np.random.uniform(600, 1200)
        elif tipo_pastura == "RAYGRASS":
            biomasa_base = np.random.uniform(500, 1000)
        elif tipo_pastura == "FESTUCA":
            biomasa_base = np.random.uniform(400, 800)
        else:
            biomasa_base = np.random.uniform(300, 700)
        
        resultados.append({
            'biomasa_disponible_kg_ms_ha': biomasa_base,
            'ndvi': np.random.uniform(0.3, 0.8),
            'evi': np.random.uniform(0.2, 0.7),
            'savi': np.random.uniform(0.25, 0.75),
            'cobertura_vegetal': np.random.uniform(0.4, 0.9),
            'tipo_superficie': np.random.choice(['VEGETACION_DENSA', 'VEGETACION_MODERADA', 'VEGETACION_ESCASA']),
            'crecimiento_diario': np.random.uniform(20, 80),
            'factor_calidad': np.random.uniform(0.5, 0.9)
        })
    return resultados

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración")
    
    tipo_pastura = st.selectbox("Tipo de Pastura:", 
                               ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"])
    
    st.subheader("📊 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 50, 1000, 100)
    
    st.subheader("🎯 División de Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", min_value=4, max_value=32, value=12)
    
    st.subheader("📤 Subir Lote")
    uploaded_zip = st.file_uploader("Subir ZIP con shapefile del potrero", type=['zip'])

    # Botón para limpiar análisis
    if st.button("🔄 Limpiar Análisis"):
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
                        st.write(f"- Sub-lotes: {n_divisiones}")
                        st.write(f"- Carga animal: {carga_animal} cabezas")
                    
                    # Solo ejecutar análisis si no se ha hecho antes
                    if not st.session_state.analysis_done:
                        if st.button("🚀 EJECUTAR ANÁLISIS FORRAJERO", type="primary"):
                            
                            # Paso 1: Dividir potrero
                            st.subheader("📐 DIVIDIENDO POTRERO")
                            gdf_dividido = divide_pasture(gdf, n_divisiones)
                            st.session_state.gdf_dividido = gdf_dividido
                            st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
                            
                            # Paso 2: Simular análisis
                            st.subheader("🌿 CALCULANDO ÍNDICES FORRAJEROS")
                            with st.spinner("Ejecutando análisis..."):
                                analysis_results = simular_analisis_forrajero(gdf_dividido, tipo_pastura)
                                st.session_state.analysis_results = analysis_results
                            
                            st.session_state.analysis_done = True
                            st.success("✅ Análisis completado")
                            st.rerun()
                    
                    # Mostrar resultados si el análisis está hecho
                    if st.session_state.analysis_done and st.session_state.gdf_dividido is not None:
                        
                        # Mostrar mapa interactivo
                        st.subheader("🗺️ MAPA INTERACTIVO DEL POTRERO")
                        
                        # Crear mapa
                        mapa = create_interactive_map(
                            st.session_state.gdf_dividido, 
                            tipo_pastura, 
                            st.session_state.analysis_results
                        )
                        
                        # Mostrar mapa con st_folium
                        if mapa:
                            st_data = st_folium(
                                mapa, 
                                width=1200, 
                                height=600,
                                key="main_map"
                            )
                        
                        # Mostrar resumen de resultados
                        st.subheader("📊 RESUMEN DE RESULTADOS")
                        
                        # Calcular estadísticas
                        biomasas = [r['biomasa_disponible_kg_ms_ha'] for r in st.session_state.analysis_results]
                        ndvis = [r['ndvi'] for r in st.session_state.analysis_results]
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Biomasa Promedio", f"{np.mean(biomasas):.0f} kg MS/ha")
                        with col2:
                            st.metric("NDVI Promedio", f"{np.mean(ndvis):.3f}")
                        with col3:
                            st.metric("Sub-lotes", len(st.session_state.gdf_dividido))
                        with col4:
                            # Calcular categorías
                            categorias = {}
                            for result in st.session_state.analysis_results:
                                cat = result['tipo_superficie']
                                categorias[cat] = categorias.get(cat, 0) + 1
                            cat_principal = max(categorias, key=categorias.get)
                            st.metric("Categoría Principal", cat_principal)
                        
                        # Tabla de resultados detallados
                        st.subheader("📋 DETALLE POR SUB-LOTE")
                        
                        # Crear DataFrame para mostrar
                        df_resultados = pd.DataFrame({
                            'Sub-Lote': range(1, len(st.session_state.analysis_results) + 1),
                            'Biomasa (kg MS/ha)': [r['biomasa_disponible_kg_ms_ha'] for r in st.session_state.analysis_results],
                            'NDVI': [r['ndvi'] for r in st.session_state.analysis_results],
                            'Cobertura': [f"{r['cobertura_vegetal']:.1%}" for r in st.session_state.analysis_results],
                            'Tipo Superficie': [r['tipo_superficie'] for r in st.session_state.analysis_results],
                            'Crecimiento (kg/día)': [f"{r['crecimiento_diario']:.1f}" for r in st.session_state.analysis_results]
                        })
                        
                        st.dataframe(df_resultados, use_container_width=True)
                        
                        # Gráfico de distribución de biomasa
                        st.subheader("📈 DISTRIBUCIÓN DE BIOMASA")
                        fig, ax = plt.subplots(figsize=(10, 6))
                        ax.hist(biomasas, bins=10, alpha=0.7, color='green', edgecolor='black')
                        ax.set_xlabel('Biomasa (kg MS/ha)')
                        ax.set_ylabel('Número de Sub-lotes')
                        ax.set_title('Distribución de Biomasa por Sub-lote')
                        ax.grid(True, alpha=0.3)
                        st.pyplot(fig)
                        
        except Exception as e:
            st.error(f"Error cargando shapefile: {str(e)}")
            st.info("""
            **Posibles soluciones:**
            - Verifica que el ZIP contenga todos los archivos del shapefile (.shp, .shx, .dbf, .prj)
            - Asegúrate de que el shapefile tenga un sistema de coordenadas válido
            - Intenta con un shapefile más simple para probar
            """)

else:
    st.info("📁 Sube el ZIP de tu potrero para comenzar el análisis forrajero")
    
    # Información de la aplicación
    with st.expander("ℹ️ INFORMACIÓN DE LA APLICACIÓN"):
        st.markdown("""
        **🌱 SISTEMA DE ANÁLISIS FORRAJERO**
        
        **Funcionalidades:**
        - 🗺️ Visualización interactiva de potreros
        - 📊 Análisis de biomasa y productividad
        - 🌿 Cálculo de índices de vegetación simulados
        - 🐄 Estimación de capacidad ganadera
        - 📈 Gráficos y estadísticas
        
        **Instrucciones de uso:**
        1. **Prepara tu shapefile** - Asegúrate de tener todos los archivos (.shp, .shx, .dbf, .prj)
        2. **Comprime en ZIP** - Crea un archivo ZIP con todos los archivos del shapefile
        3. **Configura los parámetros** en la barra lateral
        4. **Ejecuta el análisis** y visualiza los resultados
        
        **Nota:** Esta versión usa datos simulados. Para análisis con datos satelitales reales, 
        ejecuta la aplicación localmente con Google Earth Engine.
        """)
