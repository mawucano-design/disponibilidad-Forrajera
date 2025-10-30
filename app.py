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

# Import st_folium
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

    # Botón para limpiar análisis
    if st.button("🔄 Limpiar Análisis"):
        st.session_state.analysis_done = False
        st.session_state.gdf_dividido = None
        st.session_state.analysis_results = None
        st.rerun()

# Función para simular análisis forrajero (temporal)
def simular_analisis_forrajero(gdf_dividido, tipo_pastura):
    """Simula el análisis forrajero - reemplazar con tu lógica real"""
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
                    
                    # Solo ejecutar análisis si no se ha hecho antes o si se solicita explícitamente
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
                            None,  # No image for now
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
                            st.metric("Sub-lotes Analizados", len(st.session_state.gdf_dividido))
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
                            'Cobertura': [r['cobertura_vegetal'] for r in st.session_state.analysis_results],
                            'Tipo Superficie': [r['tipo_superficie'] for r in st.session_state.analysis_results],
                            'Crecimiento (kg/día)': [r['crecimiento_diario'] for r in st.session_state.analysis_results]
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
                        
                        # Información adicional
                        st.subheader("🔍 INFORMACIÓN TÉCNICA")
                        with st.expander("Ver detalles técnicos"):
                            st.markdown(f"""
                            **Parámetros utilizados:**
                            - Tipo de pastura: {tipo_pastura}
                            - Período de análisis: {fecha_inicio} a {fecha_fin}
                            - Nubosidad máxima: {nubosidad_maxima}%
                            - Peso promedio animal: {peso_promedio} kg
                            - Carga animal: {carga_animal} cabezas
                            
                            **Métricas calculadas:**
                            - Biomasa disponible (kg MS/ha)
                            - Índices de vegetación (NDVI, EVI, SAVI)
                            - Cobertura vegetal (%)
                            - Tipo de superficie
                            - Crecimiento diario estimado
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
        - 🗺️ Visualización interactiva de potreros
        - 📊 Análisis de biomasa y productividad
        - 🌿 Cálculo de índices de vegetación
        - 🐄 Estimación de capacidad ganadera
        - 🛰️ Preparado para integración con Sentinel-2
        
        **Características técnicas:**
        - Mapa interactivo con Google Satellite
        - División automática en sub-lotes
        - Análisis espacial detallado
        - Exportación de resultados
        
        **Instrucciones de uso:**
        1. **Prepara tu shapefile** (.shp, .shx, .dbf, .prj) en un ZIP
        2. **Configura los parámetros** en la barra lateral
        3. **Ejecuta el análisis** y visualiza los resultados
        4. **Explora el mapa interactivo** y las métricas calculadas
        
        **Próximas funcionalidades:**
        - Integración con Google Earth Engine
        - Datos satelitales en tiempo real
        - Análisis histórico de productividad
        - Recomendaciones de manejo automatizadas
        """)
