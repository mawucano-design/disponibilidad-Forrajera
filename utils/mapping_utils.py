import folium
import streamlit as st
import geopandas as gpd

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
                coverage = analysis_results[idx]['cobertura_vegetal']
                
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
                            <b>Cobertura:</b> {coverage:.1%}
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
