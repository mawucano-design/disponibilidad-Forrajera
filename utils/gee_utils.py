import ee
import streamlit as st
from datetime import datetime
import geemap

def initialize_earth_engine():
    """Initialize Earth Engine with authentication"""
    try:
        ee.Initialize()
        st.success("✅ Earth Engine inicializado")
        return True
    except Exception as e:
        try:
            ee.Authenticate()
            ee.Initialize()
            st.success("✅ Earth Engine autenticado e inicializado")
            return True
        except Exception as auth_error:
            st.warning("⚠️ Earth Engine no pudo inicializarse. Usando modo simulación.")
            st.info("Para usar datos satelitales reales, ejecuta en local y autentica con GEE")
            return False

def get_sentinel2_image(geometry, start_date, end_date, cloud_cover=20):
    """Get Sentinel-2 harmonized image collection"""
    try:
        # Convert dates
        start = ee.Date(start_date.strftime('%Y-%m-%d'))
        end = ee.Date(end_date.strftime('%Y-%m-%d'))
        
        # Filter Sentinel-2 collection
        collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                     .filterBounds(geometry)
                     .filterDate(start, end)
                     .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloud_cover))
                     .sort('CLOUDY_PIXEL_PERCENTAGE'))
        
        # Check if we have images
        count = collection.size().getInfo()
        if count == 0:
            st.warning("No se encontraron imágenes Sentinel-2 para los criterios seleccionados")
            return None, None
        
        # Create median composite
        image = collection.median()
        
        # Apply scale factor
        image = image.multiply(0.0001)
        
        # Calculate vegetation indices
        ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
        evi = image.expression(
            '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))', {
                'NIR': image.select('B8'),
                'RED': image.select('B4'),
                'BLUE': image.select('B2')
            }).rename('EVI')
        
        # Add indices to image
        image_with_indices = image.addBands([ndvi, evi])
        
        return image_with_indices, collection
        
    except Exception as e:
        st.error(f"Error obteniendo imagen Sentinel-2: {str(e)}")
        return None, None

def extract_satellite_values(gdf, image_s2):
    """Extract real satellite values for each sub-lot"""
    try:
        if image_s2 is None:
            return None
            
        resultados = []
        
        for idx, row in gdf.iterrows():
            geom = row.geometry
            ee_geom = ee.Geometry(geom.__geo_interface__)
            
            # Reduce region to get statistics
            stats = image_s2.select(['NDVI', 'EVI', 'B2', 'B3', 'B4', 'B8']).reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee_geom,
                scale=10,
                bestEffort=True
            )
            
            # Get values
            stats_info = stats.getInfo()
            
            resultados.append({
                'ndvi_real': stats_info.get('NDVI', 0),
                'evi_real': stats_info.get('EVI', 0),
                'blue_real': stats_info.get('B2', 0),
                'green_real': stats_info.get('B3', 0),
                'red_real': stats_info.get('B4', 0),
                'nir_real': stats_info.get('B8', 0)
            })
        
        return resultados
        
    except Exception as e:
        st.warning(f"No se pudieron extraer valores satelitales: {str(e)}")
        return None
