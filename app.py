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

# Configuración de la página
st.set_page_config(
    page_title="🌱 Analizador Forrajero",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("🌱 ANALIZADOR FORRAJERO")
st.markdown("---")

# Inicializar estado de la sesión
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False
if 'gdf_dividido' not in st.session_state:
    st.session_state.gdf_dividido = None
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None

# ===== FUNCIONES AUXILIARES =====

def calcular_superficie(gdf):
    """Calcula superficie en hectáreas"""
    try:
        if gdf.crs and gdf.crs.is_geographic:
            area_m2 = gdf.geometry.area * 10000000000
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000
    except:
        return gdf.geometry.area / 10000

def dividir_potrero(gdf, n_zonas):
    """Divide el potrero en sub-lotes"""
    if len(gdf) == 0:
        return gdf
    
    potrero_principal = gdf.iloc[0].geometry
    bounds = potrero_principal.bounds
    minx, miny, maxx, maxy = bounds
    
    sub_poligonos = []
    
    n_cols = math.ceil(math.sqrt(n_zonas))
    n_rows = math.ceil(n_zonas / n_cols)
    
    ancho_celda = (maxx - minx) / n_cols
    alto_celda = (maxy - miny) / n_rows
    
    for i in range(n_rows):
        for j in range(n_cols):
            if len(sub_poligonos) >= n_zonas:
                break
                
            celda_minx = minx + (j * ancho_celda)
            celda_maxx = minx + ((j + 1) * ancho_celda)
            celda_miny = miny + (i * alto_celda)
            celda_maxy = miny + ((i + 1) * alto_celda)
            
            celda_poly = Polygon([
                (celda_minx, celda_miny),
                (celda_maxx, celda_miny),
                (celda_maxx, celda_maxy),
                (celda_minx, celda_maxy)
            ])
            
            interseccion = potrero_principal.intersection(celda_poly)
            if not interseccion.is_empty and interseccion.area > 0:
                sub_poligonos.append(interseccion)
    
    if sub_poligonos:
        nuevo_gdf = gpd.GeoDataFrame({
            'id_subLote': range(1, len(sub_poligonos) + 1),
            'geometry': sub_poligonos
        }, crs=gdf.crs)
        return nuevo_gdf
    else:
        return gdf

def crear_mapa_interactivo(gdf, tipo_pastura, resultados_analisis):
    """Crea mapa interactivo con los resultados"""
    try:
        # Obtener centroide del área
        centroid = gdf.geometry.centroid.iloc[0]
        centro_lat, centro_lon = centroid.y, centroid.x
        
        # Crear mapa base
        mapa = folium.Map(
            location=[centro_lat, centro_lon],
            zoom_start=12
        )
        
        # Añadir polígonos de sub-lotes
        for idx, row in gdf.iterrows():
            id_sub_lote = row['id_subLote']
            biomasa = resultados_analisis[idx]['biomasa_disponible_kg_ms_ha']
            ndvi = resultados_analisis[idx]['ndvi']
            tipo_superficie = resultados_analisis[idx]['tipo_superficie']
            
            # Color según biomasa
            if biomasa < 200:
                color = 'red'
            elif biomasa < 400:
                color = 'orange'
            elif biomasa < 600:
                color = 'yellow'
            elif biomasa < 800:
                color = 'lightgreen'
            else:
                color = 'darkgreen'
            
            # Crear polígono
            geom = row.geometry
            if geom.geom_type == 'Polygon':
                coords = [[point[1], point[0]] for point in geom.exterior.coords]
                
                folium.Polygon(
                    locations=coords,
                    popup=f"""
                    <b>Sub-Lote S{id_sub_lote}</b><br>
                    Biomasa: {biomasa} kg MS/ha<br>
                    NDVI: {ndvi:.3f}<br>
                    Tipo: {tipo_superficie}
                    """,
                    tooltip=f'S{id_sub_lote} - {biomasa} kg MS/ha',
                    color=color,
                    fill_color=color,
                    fill_opacity=0.5,
                    weight=2
                ).add_to(mapa)
        
        return mapa
        
    except Exception as e:
        st.error(f"Error creando mapa: {str(e)}")
        return folium.Map(location=[-34.0, -64.0], zoom_start=4)

def simular_analisis_forrajero(gdf_dividido, tipo_pastura):
    """Simula el análisis forrajero con datos realistas"""
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

# ===== INTERFAZ PRINCIPAL =====

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración del Análisis")
    
    st.subheader("🌿 Tipo de Pastura")
    tipo_pastura = st.selectbox(
        "Selecciona el tipo de pastura:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL", "PERSONALIZADO"]
    )
    
    st.subheader("🐄 Parámetros Ganaderos")
    peso_promedio = st.slider("Peso promedio animal (kg):", 300, 600, 450)
    carga_animal = st.slider("Carga animal (cabezas):", 10, 500, 100)
    
    st.subheader("🎯 División del Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", 4, 36, 16, 4)
    
    st.subheader("📤 Cargar Shapefile")
    uploaded_zip = st.file_uploader(
        "Sube tu shapefile comprimido en ZIP:",
        type=['zip']
    )
    
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
                    
                    area_total = calcular_superficie(gdf).sum()
                    
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
                            gdf_dividido = dividir_potrero(gdf, n_divisiones)
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
                        mapa = crear_mapa_interactivo(
                            st.session_state.gdf_dividido,
                            tipo_pastura,
                            st.session_state.analysis_results
                        )
                        
                        # Mostrar mapa con st_folium
                        if mapa:
                            st_folium(mapa, width=1200, height=500, key="main_map")
                        
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
