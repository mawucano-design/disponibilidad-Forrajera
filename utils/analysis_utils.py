import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Polygon
import math

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
        spatial_variation = (centroide.x + centroide.y) % 1
        
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
