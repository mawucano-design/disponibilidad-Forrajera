import folium
import geopandas as gpd

def create_interactive_map(gdf, image_s2, pasture_type, analysis_results):
    """Create interactive map with Google Satellite"""
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
                    popup=f"Sub-Lote {sub_lot_id}<br>Biomasa: {biomass:.0f} kg/ha<br>NDVI: {ndvi:.3f}",
                    color=color,
                    fill_color=color,
                    fill_opacity=0.5,
                    weight=2
                ).add_to(m)
        
        return m
    except Exception as e:
        return folium.Map(location=[-34.0, -64.0], zoom_start=4)
