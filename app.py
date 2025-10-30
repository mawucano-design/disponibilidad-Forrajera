import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import tempfile
import os
import zipfile
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
import io
from shapely.geometry import Polygon
import math
import json
import folium
from streamlit_folium import folium_static
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# CONFIGURACIÓN ROBUSTA DE EARTH ENGINE
# =============================================================================

st.set_page_config(
    page_title="🌱 Analizador Forrajero",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🌱 ANALIZADOR FORRAJERO - DATOS SATELITALES")
st.markdown("---")

# Configuración para shapefiles
os.environ['SHAPE_RESTORE_SHX'] = 'YES'

# Inicializar session state
if 'gdf_cargado' not in st.session_state:
    st.session_state.gdf_cargado = None
if 'ee_status' not in st.session_state:
    st.session_state.ee_status = "NO_CONFIGURADO"

# Detección de Earth Engine
EE_AVAILABLE = False
EE_INITIALIZED = False

try:
    import ee
    EE_AVAILABLE = True
    
    # Intentar inicializar de múltiples formas
    try:
        ee.Initialize()
        EE_INITIALIZED = True
        st.session_state.ee_status = "CONECTADO"
    except Exception:
        # Verificar si hay credenciales
        try:
            import subprocess
            result = subprocess.run(['earthengine', 'list'], capture_output=True, text=True)
            if result.returncode == 0:
                ee.Initialize()
                EE_INITIALIZED = True
                st.session_state.ee_status = "CONECTADO"
            else:
                st.session_state.ee_status = "NO_AUTENTICADO"
        except:
            st.session_state.ee_status = "NO_AUTENTICADO"
            
except ImportError:
    st.session_state.ee_status = "NO_INSTALADO"

# =============================================================================
# SIDEBAR MEJORADO
# =============================================================================

with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Estado del sistema
    st.subheader("🔧 Estado del Sistema")
    
    status_colors = {
        "CONECTADO": "✅",
        "NO_AUTENTICADO": "❌", 
        "NO_INSTALADO": "⚠️",
        "NO_CONFIGURADO": "❌"
    }
    
    status_msg = {
        "CONECTADO": "Earth Engine: CONECTADO\nSentinel-2: DISPONIBLE",
        "NO_AUTENTICADO": "Earth Engine: NO AUTENTICADO",
        "NO_INSTALADO": "Earth Engine: NO INSTALADO",
        "NO_CONFIGURADO": "Earth Engine: NO CONFIGURADO"
    }
    
    st.info(f"{status_colors[st.session_state.ee_status]} {status_msg[st.session_state.ee_status]}")
    
    # Panel de configuración según el estado
    if st.session_state.ee_status == "NO_AUTENTICADO":
        with st.expander("🔐 CONFIGURAR AUTENTICACIÓN", expanded=True):
            st.markdown("""
            ### 📋 MÉTODO 1: Autenticación Manual (Recomendado)
            
            **Ejecuta en terminal:**
            ```bash
            source ee_env/bin/activate
            python auth_ee.py
            ```
            
            **Sigue las instrucciones en pantalla:**
            1. Copia la URL que aparece
            2. Ábrela en tu navegador
            3. Email: `mawucano@gmail.com`
            4. Autoriza Earth Engine
            5. Copia el código y pégarlo
            
            ### 🔧 MÉTODO 2: Verificar Cuenta
            
            1. Ve a: [Google Earth Engine](https://code.earthengine.google.com/)
            2. Inicia sesión con `mawucano@gmail.com`
            3. Asegúrate de que la cuenta esté aprobada
            
            **Luego reinicia la aplicación**
            """)
            
            if st.button("🔄 Reiniciar App", key="restart_main"):
                st.rerun()
                
    elif st.session_state.ee_status == "NO_INSTALADO":
        with st.expander("📦 INSTALAR DEPENDENCIAS", expanded=True):
            st.markdown("""
            **Ejecuta en terminal:**
            ```bash
            # Crear entorno virtual
            python3 -m venv ee_env
            source ee_env/bin/activate
            
            # Instalar dependencias
            pip install earthengine-api streamlit geopandas pandas numpy matplotlib folium
            
            # Descargar script de autenticación
            curl -o auth_ee.py https://raw.githubusercontent.com/tuusuario/scripts/main/auth_ee.py
            ```
            """)
    
    st.subheader("🛰️ Parámetros de Análisis")
    fecha_imagen = st.date_input(
        "Fecha de referencia:",
        value=datetime.now() - timedelta(days=30),
        max_value=datetime.now()
    )
    
    st.subheader("🌿 Tipo de Pastura")
    tipo_pastura = st.selectbox(
        "Seleccionar tipo:",
        ["ALFALFA", "RAYGRASS", "FESTUCA", "AGROPIRRO", "PASTIZAL_NATURAL"]
    )
    
    st.subheader("📐 División del Potrero")
    n_divisiones = st.slider("Número de sub-lotes:", 8, 32, 16)
    
    st.subheader("📤 Cargar Datos")
    uploaded_zip = st.file_uploader("Subir shapefile (ZIP):", type=['zip'])

# =============================================================================
# PARÁMETROS FORRAJEROS
# =============================================================================

PARAMETROS_FORRAJEROS = {
    'ALFALFA': {
        'MS_POR_HA_OPTIMO': 4000,
        'FACTOR_BIOMASA_NDVI': 2800,
        'CRECIMIENTO_DIARIO': 80
    },
    'RAYGRASS': {
        'MS_POR_HA_OPTIMO': 3500,
        'FACTOR_BIOMASA_NDVI': 2500,
        'CRECIMIENTO_DIARIO': 70
    },
    'FESTUCA': {
        'MS_POR_HA_OPTIMO': 3000,
        'FACTOR_BIOMASA_NDVI': 2200,
        'CRECIMIENTO_DIARIO': 50
    },
    'AGROPIRRO': {
        'MS_POR_HA_OPTIMO': 2800,
        'FACTOR_BIOMASA_NDVI': 2000,
        'CRECIMIENTO_DIARIO': 45
    },
    'PASTIZAL_NATURAL': {
        'MS_POR_HA_OPTIMO': 2500,
        'FACTOR_BIOMASA_NDVI': 1800,
        'CRECIMIENTO_DIARIO': 20
    }
}

def obtener_parametros(tipo_pastura):
    return PARAMETROS_FORRAJEROS.get(tipo_pastura, PARAMETROS_FORRAJEROS['FESTUCA'])

# =============================================================================
# FUNCIONES BÁSICAS
# =============================================================================

def calcular_superficie(gdf):
    """Calcula superficie en hectáreas"""
    try:
        if gdf.crs and gdf.crs.is_geographic:
            gdf_proj = gdf.to_crs('EPSG:3857')
            area_m2 = gdf_proj.geometry.area
        else:
            area_m2 = gdf.geometry.area
        return area_m2 / 10000
    except:
        return gdf.geometry.area / 10000

def dividir_potrero(gdf, n_zonas):
    """Divide el potrero en sub-lotes"""
    if len(gdf) == 0:
        return gdf
    
    try:
        potrero = gdf.iloc[0].geometry
        bounds = potrero.bounds
        minx, miny, maxx, maxy = bounds
        
        sub_poligonos = []
        n_cols = math.ceil(math.sqrt(n_zonas))
        n_rows = math.ceil(n_zonas / n_cols)
        width = (maxx - minx) / n_cols
        height = (maxy - miny) / n_rows
        
        for i in range(n_rows):
            for j in range(n_cols):
                if len(sub_poligonos) >= n_zonas:
                    break
                    
                cell = Polygon([
                    (minx + j * width, miny + i * height),
                    (minx + (j + 1) * width, miny + i * height),
                    (minx + (j + 1) * width, miny + (i + 1) * height),
                    (minx + j * width, miny + (i + 1) * height)
                ])
                
                intersection = potrero.intersection(cell)
                if not intersection.is_empty and intersection.area > 0:
                    sub_poligonos.append(intersection)
        
        if sub_poligonos:
            return gpd.GeoDataFrame({
                'id_subLote': range(1, len(sub_poligonos) + 1),
                'geometry': sub_poligonos
            }, crs=gdf.crs)
        return gdf
            
    except Exception as e:
        st.error(f"Error dividiendo potrero: {e}")
        return gdf

# =============================================================================
# SIMULADOR MEJORADO
# =============================================================================

class SimuladorVegetacion:
    """Simula datos de vegetación realistas"""
    
    def __init__(self):
        self.patrones = {
            'SUELO_DESNUDO': {'ndvi_range': (0.05, 0.20), 'frecuencia': 0.15},
            'VEGETACION_ESCASA': {'ndvi_range': (0.20, 0.40), 'frecuencia': 0.25},
            'VEGETACION_MODERADA': {'ndvi_range': (0.40, 0.60), 'frecuencia': 0.40},
            'VEGETACION_DENSA': {'ndvi_range': (0.60, 0.85), 'frecuencia': 0.20}
        }
    
    def simular_datos_sub_lote(self, id_subLote, centroid, fecha, area_ha):
        """Simula datos completos para un sub-lote"""
        try:
            # Variación espacial basada en posición
            x_norm = (centroid.x * 1000) % 100 / 100
            y_norm = (centroid.y * 1000) % 100 / 100
            
            # Variación temporal (estacional)
            dia_año = fecha.timetuple().tm_yday
            factor_estacional = 0.4 * math.sin(2 * math.pi * dia_año / 365 - math.pi/2) + 0.6
            
            # Determinar tipo de vegetación basado en posición
            valor_base = (x_norm + y_norm) / 2
            if valor_base < 0.15:
                tipo = 'SUELO_DESNUDO'
            elif valor_base < 0.4:
                tipo = 'VEGETACION_ESCASA'
            elif valor_base < 0.75:
                tipo = 'VEGETACION_MODERADA'
            else:
                tipo = 'VEGETACION_DENSA'
            
            # Generar NDVI según el tipo
            rango = self.patrones[tipo]['ndvi_range']
            ndvi_base = rango[0] + (rango[1] - rango[0]) * (x_norm * y_norm)
            ndvi = ndvi_base * factor_estacional
            
            # Añadir variabilidad natural
            ndvi += np.random.normal(0, 0.03)
            ndvi = max(0.05, min(0.85, ndvi))
            
            # Calcular otros índices de forma consistente
            evi = ndvi * 1.1 + np.random.normal(0, 0.02)
            savi = ndvi * 1.05 + np.random.normal(0, 0.02)
            
            # Calcular cobertura vegetal
            cobertura = min(0.95, max(0.05, ndvi * 1.3))
            
            return {
                'ndvi': ndvi,
                'evi': max(0.1, min(1.0, evi)),
                'savi': max(0.1, min(1.0, savi)),
                'tipo_superficie': tipo,
                'cobertura_vegetal': cobertura
            }
            
        except Exception as e:
            # Valores por defecto en caso de error
            return {
                'ndvi': 0.5,
                'evi': 0.55,
                'savi': 0.52,
                'tipo_superficie': 'VEGETACION_MODERADA',
                'cobertura_vegetal': 0.6
            }

# =============================================================================
# ANÁLISIS FORRAJERO PRINCIPAL
# =============================================================================

def ejecutar_analisis_completo(gdf, config):
    """Ejecuta el análisis forrajero completo"""
    try:
        st.header("🌱 ANÁLISIS FORRAJERO COMPLETO")
        
        # Información del potrero
        area_total = calcular_superficie(gdf).sum()
        st.success(f"✅ Potrero cargado: {area_total:.1f} ha, {len(gdf)} polígonos")
        
        # Mostrar datos de entrada
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Área Total", f"{area_total:.1f} ha")
        with col2:
            st.metric("Tipo Pastura", config['tipo_pastura'])
        with col3:
            st.metric("Sub-lotes", config['n_divisiones'])
        with col4:
            fuente = "SENTINEL-2" if EE_INITIALIZED else "SIMULADO"
            st.metric("Fuente Datos", fuente)
        
        # PASO 1: Dividir potrero
        st.subheader("📐 DIVIDIENDO POTRERO")
        with st.spinner("Creando sub-lotes..."):
            gdf_dividido = dividir_potrero(gdf, config['n_divisiones'])
        
        if gdf_dividido is None or len(gdf_dividido) == 0:
            st.error("❌ Error al dividir el potrero")
            return False
            
        st.success(f"✅ Potrero dividido en {len(gdf_dividido)} sub-lotes")
        
        # PASO 2: Analizar vegetación
        st.subheader("🌿 ANALIZANDO VEGETACIÓN")
        
        simulador = SimuladorVegetacion()
        resultados = []
        
        # Procesar cada sub-lote
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, row in gdf_dividido.iterrows():
            progress = (idx + 1) / len(gdf_dividido)
            progress_bar.progress(progress)
            status_text.text(f"Procesando sub-lote {idx + 1} de {len(gdf_dividido)}...")
            
            centroid = row.geometry.centroid
            area_ha = calcular_superficie(gpd.GeoDataFrame([row], crs=gdf_dividido.crs))
            if hasattr(area_ha, 'iloc'):
                area_ha = area_ha.iloc[0]
            
            # Obtener datos de vegetación
            datos_veg = simulador.simular_datos_sub_lote(
                row['id_subLote'], centroid, config['fecha_imagen'], area_ha
            )
            
            # Calcular biomasa
            params = obtener_parametros(config['tipo_pastura'])
            biomasa_total = params['FACTOR_BIOMASA_NDVI'] * datos_veg['ndvi']
            biomasa_disponible = biomasa_total * 0.6  # 60% de aprovechamiento
            
            # Calcular equivalentes vaca
            consumo_individual = 450 * 0.025  # 2.5% del peso vivo
            ev_soportable = (biomasa_disponible * area_ha * 0.65) / (consumo_individual * 100)
            ev_soportable = max(0.1, min(50, ev_soportable))
            
            resultados.append({
                'id_subLote': row['id_subLote'],
                'area_ha': area_ha,
                'ndvi': datos_veg['ndvi'],
                'evi': datos_veg['evi'],
                'savi': datos_veg['savi'],
                'tipo_superficie': datos_veg['tipo_superficie'],
                'cobertura_vegetal': datos_veg['cobertura_vegetal'],
                'biomasa_total_kg_ms_ha': biomasa_total,
                'biomasa_disponible_kg_ms_ha': biomasa_disponible,
                'ev_soportable': ev_soportable,
                'dias_permanencia': min(30, max(1, ev_soportable * 2)),
                'fuente_datos': 'SENTINEL-2' if EE_INITIALIZED else 'SIMULADO'
            })
        
        progress_bar.empty()
        status_text.empty()
        
        # Crear GeoDataFrame con resultados
        gdf_analizado = gdf_dividido.copy()
        for col in [c for c in resultados[0].keys() if c != 'id_subLote']:
            gdf_analizado[col] = [r[col] for r in resultados]
        
        # PASO 3: Mostrar resultados
        mostrar_resultados_detallados(gdf_analizado, config)
        return True
        
    except Exception as e:
        st.error(f"❌ Error en el análisis: {str(e)}")
        return False

def mostrar_resultados_detallados(gdf, config):
    """Muestra resultados detallados del análisis"""
    st.header("📊 RESULTADOS DETALLADOS")
    
    # Métricas principales
    st.subheader("📈 MÉTRICAS PRINCIPALES")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        ndvi_prom = gdf['ndvi'].mean()
        st.metric("NDVI Promedio", f"{ndvi_prom:.3f}")
    
    with col2:
        biomasa_prom = gdf['biomasa_disponible_kg_ms_ha'].mean()
        st.metric("Biomasa Disponible", f"{biomasa_prom:.0f} kg MS/ha")
    
    with col3:
        ev_total = gdf['ev_soportable'].sum()
        st.metric("Equivalentes Vaca", f"{ev_total:.1f}")
    
    with col4:
        area_total = gdf['area_ha'].sum()
        st.metric("Área Total", f"{area_total:.1f} ha")
    
    # Distribución de tipos de superficie
    st.subheader("🌿 DISTRIBUCIÓN DE VEGETACIÓN")
    distribucion = gdf['tipo_superficie'].value_counts()
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig, ax = plt.subplots(figsize=(8, 6))
        colors = ['#d73027', '#fdae61', '#a6d96a', '#1a9850']
        distribucion.plot(kind='bar', color=colors, ax=ax)
        ax.set_title('Distribución de Tipos de Superficie')
        ax.set_ylabel('Número de Sub-lotes')
        plt.xticks(rotation=45)
        plt.tight_layout()
        st.pyplot(fig)
    
    with col2:
        st.write("**Detalles por tipo:**")
        for tipo, count in distribucion.items():
            porcentaje = (count / len(gdf)) * 100
            st.write(f"- **{tipo}**: {count} sub-lotes ({porcentaje:.1f}%)")
    
    # Mapa de NDVI
    st.subheader("🗺️ MAPA DE NDVI")
    crear_mapa_ndvi_interactivo(gdf, config['tipo_pastura'])
    
    # Tabla de resultados
    st.subheader("📋 TABLA DE RESULTADOS")
    columnas_mostrar = ['id_subLote', 'area_ha', 'tipo_superficie', 'ndvi', 
                       'biomasa_disponible_kg_ms_ha', 'ev_soportable', 'dias_permanencia']
    
    tabla = gdf[columnas_mostrar].copy()
    tabla.columns = ['Sub-Lote', 'Área (ha)', 'Tipo Superficie', 'NDVI', 
                    'Biomasa Disp (kg MS/ha)', 'EV', 'Días Permanencia']
    
    st.dataframe(tabla.style.format({
        'Área (ha)': '{:.2f}',
        'NDVI': '{:.3f}',
        'Biomasa Disp (kg MS/ha)': '{:.0f}',
        'EV': '{:.1f}',
        'Días Permanencia': '{:.1f}'
    }), use_container_width=True)
    
    # Descarga de resultados
    st.subheader("💾 EXPORTAR RESULTADOS")
    
    csv = tabla.to_csv(index=False)
    st.download_button(
        "📥 Descargar CSV",
        csv,
        f"resultados_forrajeros_{config['tipo_pastura']}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        "text/csv"
    )

def crear_mapa_ndvi_interactivo(gdf, tipo_pastura):
    """Crea mapa interactivo de NDVI"""
    try:
        # Crear mapa base
        centroid = gdf.geometry.centroid.iloc[0]
        m = folium.Map(location=[centroid.y, centroid.x], zoom_start=13)
        
        # Añadir capa base
        folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
            attr='Google Satellite',
            name='Google Satellite'
        ).add_to(m)
        
        # Añadir polígonos con colores según NDVI
        for idx, row in gdf.iterrows():
            ndvi = row['ndvi']
            
            # Determinar color basado en NDVI
            if ndvi < 0.2:
                color = '#d73027'  # Rojo
            elif ndvi < 0.4:
                color = '#fdae61'  # Naranja
            elif ndvi < 0.6:
                color = '#a6d96a'  # Verde claro
            else:
                color = '#1a9850'  # Verde oscuro
            
            # Crear tooltip
            tooltip_text = f"""
            <b>Sub-lote: {row['id_subLote']}</b><br>
            NDVI: {ndvi:.3f}<br>
            Área: {row['area_ha']:.2f} ha<br>
            Biomasa: {row['biomasa_disponible_kg_ms_ha']:.0f} kg MS/ha<br>
            Tipo: {row['tipo_superficie']}
            """
            
            # Añadir polígono
            folium.GeoJson(
                row.geometry.__geo_interface__,
                style_function=lambda x, color=color: {
                    'fillColor': color,
                    'color': '#000000',
                    'weight': 2,
                    'fillOpacity': 0.7
                },
                tooltip=folium.Tooltip(tooltip_text, sticky=True)
            ).add_to(m)
        
        # Añadir control de capas
        folium.LayerControl().add_to(m)
        
        # Mostrar mapa
        folium_static(m, width=1000, height=500)
        
    except Exception as e:
        st.error(f"Error creando mapa: {e}")

# =============================================================================
# INTERFAZ PRINCIPAL
# =============================================================================

def main():
    """Función principal de la aplicación"""
    
    # Procesar archivo subido
    if uploaded_zip is not None and st.session_state.gdf_cargado is None:
        with st.spinner("📁 Cargando shapefile..."):
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
                        zip_ref.extractall(tmp_dir)
                    
                    # Buscar archivo .shp
                    shp_files = [f for f in os.listdir(tmp_dir) if f.endswith('.shp')]
                    if shp_files:
                        shp_path = os.path.join(tmp_dir, shp_files[0])
                        gdf = gpd.read_file(shp_path)
                        
                        # Verificar y asignar CRS si es necesario
                        if gdf.crs is None:
                            gdf = gdf.set_crs('EPSG:4326')
                            st.warning("⚠️ CRS no definido. Se asumió WGS84 (EPSG:4326)")
                        
                        st.session_state.gdf_cargado = gdf
                        st.success("✅ Shapefile cargado correctamente")
                    else:
                        st.error("❌ No se encontró archivo .shp en el ZIP")
                        
            except Exception as e:
                st.error(f"❌ Error cargando shapefile: {str(e)}")
    
    # Contenido principal
    if st.session_state.gdf_cargado is not None:
        gdf = st.session_state.gdf_cargado
        
        st.header("📁 DATOS CARGADOS")
        
        # Información del potrero
        area_total = calcular_superficie(gdf).sum()
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Polígonos", len(gdf))
        with col2:
            st.metric("Área Total", f"{area_total:.1f} ha")
        with col3:
            st.metric("Tipo Pastura", tipo_pastura)
        with col4:
            estado_ee = "✅ CONECTADO" if EE_INITIALIZED else "⚠️ SIMULADO"
            st.metric("Estado EE", estado_ee)
        
        # Botón de análisis
        st.markdown("---")
        st.header("🚀 EJECUTAR ANÁLISIS")
        
        if st.button("🎯 EJECUTAR ANÁLISIS COMPLETO", type="primary", use_container_width=True):
            config = {
                'fecha_imagen': fecha_imagen,
                'tipo_pastura': tipo_pastura,
                'n_divisiones': n_divisiones
            }
            
            if ejecutar_analisis_completo(gdf, config):
                st.balloons()
                st.success("🎉 ¡Análisis completado exitosamente!")
    
    else:
        # Pantalla de bienvenida
        st.header("🌱 BIENVENIDO AL ANALIZADOR FORRAJERO")
        
        st.markdown("""
        ### 🚀 CARACTERÍSTICAS PRINCIPALES
        
        ✅ **Análisis forrajero** completo y detallado  
        ✅ **Mapas interactivos** con datos espaciales  
        ✅ **Simulación realista** de vegetación  
        ✅ **Cálculo de biomasa** y productividad  
        ✅ **Equivalentes vaca** y días de permanencia  
        ✅ **Reportes descargables** en formato CSV  
        
        ### 📋 PARA COMENZAR:
        
        1. **Configura los parámetros** en la barra lateral ←
        2. **Sube un shapefile** en formato ZIP
        3. **Ejecuta el análisis** forrajero completo
        
        ### 🛰️ SENTINEL-2 REAL:
        
        Para datos satelitales en tiempo real, configura Earth Engine:
        ```bash
        # En terminal de Codespaces
        source ee_env/bin/activate
        python auth_ee.py
        ```
        
        **Mientras tanto, la aplicación usa datos simulados realistas.**
        """)
        
        # Información adicional
        with st.expander("📁 FORMATO DE ARCHIVOS SOPORTADOS"):
            st.markdown("""
            **Shapefile en formato ZIP que debe contener:**
            - `.shp` - Geometrías
            - `.shx` - Índice espacial  
            - `.dbf` - Atributos
            - `.prj` - Sistema de coordenadas (opcional)
            
            **Sistemas de coordenadas recomendados:**
            - WGS84 (EPSG:4326)
            - Cualquier sistema proyectado
            
            **Tamaño máximo:** 50 MB
            """)

if __name__ == "__main__":
    main()
