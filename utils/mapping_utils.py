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
        
        # Add satellite layer if available
        if image_s2 is not None:
            try:
                # Add NDVI layer
                vis_params_ndvi = {'min': -0.2, 'max': 0.8, 'palette': ['blue', 'white', 'green']}
                
                # For demonstration, we'll add a simple tile layer
                ndvi_layer = folium.TileLayer(
                    tiles='',  # You'd add actual tile URL here
                    name='NDVI Sentinel-2',
                    attr='Sentinel-2',
                    overlay=True,
                    opacity=0.6
                )
                
            except Exception as e:
                st.warning(f"Capas satelitales no disponibles: {str(e)}")
        
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
                        NDVI: {analysis_results[idx]['ndvi']}<br>
                        Tipo: {analysis_results[idx]['tipo_superficie']}
                        """,
                        tooltip=f'S{sub_lot_id} - {biomass} kg MS/ha',
                        color=color,
                        fill_color=color,
                        fill_opacity=0.3,
                        weight=2
                    ).add_to(m)
        
        # Add layer control
        folium.LayerControl().add_to(m)
        
        return m
        
    except Exception as e:
        st.error(f"Error creando mapa: {str(e)}")
        # Return a simple map as fallback
        return folium.Map(location=[-34.0, -64.0], zoom_start=4)
