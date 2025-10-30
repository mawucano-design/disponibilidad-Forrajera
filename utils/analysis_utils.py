import geopandas as gpd
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
