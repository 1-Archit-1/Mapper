
import pandas as pd
import geopandas as gpd
import folium
from folium import plugins
from streamlit_folium import st_folium
import branca.colormap as cm
from branca.element import MacroElement, Template
from typing import List, Optional, Tuple
import numpy as np
import logging
from folium.utilities import JsCode
import traceback
from ..Config import Config
import streamlit as st
import matplotlib.cm as mpl_cm
from matplotlib.colors import Normalize
import base64
import io

color_scheme = {
	'light_mode': {
		'background': '#F8F9FA',
		'shape_fill': '#E8F4F8',
		'shape_border': '#4A90E2',
		'point_color': '#FF6B6B',
		'point_edge': '#2C3E50',
		'title_color': '#2C3E50'
	}
}
def create_marker_cluster_custom(lats, lons, popups, colors, disable_clustering=False):
	# Creates colored marker clusters for Raster files
	callback = f"""
		function (row) {{
			var marker = L.circleMarker([row[0], row[1]], {{
				radius: 6,
				color: 'white',
				fillColor: row[3],
				fillOpacity: 1.0,
				weight: 1.5,
				customColor: row[3]
			}});
			marker.bindPopup(row[2], {{maxWidth: 300, maxHeight: 220}});
			return marker;
		}}
	"""

	cluster_data = list(zip(lats.tolist(), lons.tolist(), popups.tolist(), colors.tolist()))

	return plugins.FastMarkerCluster(
		data=cluster_data,
		callback=callback,
		iconCreateFunction=get_icon_create_func(),
		maxClusterRadius=40,
		disableClusteringAtZoom=1 if disable_clustering else 13
	)

def create_marker_cluster(lats, lons, popups, color_scheme, disable_clustering=False):
	callback = f"""
		function (row) {{
			var marker = L.circleMarker([row[0], row[1]], {{
				radius: 6,
				color: '{color_scheme["light_mode"]["point_edge"]}',
				fillColor: '{color_scheme["light_mode"]["point_color"]}',
				fillOpacity: 0.85,
				weight: 1.5
			}});
			marker.bindPopup(row[2], {{maxWidth: 300, maxHeight: 220}});
			return marker;
		}}
		"""

	cluster_data = list(zip(lats.tolist(), lons.tolist(), popups.tolist()))

	return plugins.FastMarkerCluster(
		data=cluster_data,
		callback=callback,
		maxClusterRadius=40,
		disableClusteringAtZoom=1 if disable_clustering else 13
	)



def create_legend(colormap):
	"""Currently unused"""
	# Create custom MacroElement for styled legend (prevents persistence issues)
	colormap_html = colormap._repr_html_()
	legend_template = Template(f"""
	{{% macro html(this, kwargs) %}}
	<div style="
		position: fixed;
		bottom: 50px;
		left: 50px;
		width: auto;
		background-color: rgba(255, 255, 255, 0.9);
		border: 2px solid black;
		border-radius: 5px;
		padding: 10px;
		box-shadow: 0 2px 6px rgba(0,0,0,0.3);
		z-index: 9999;
	">
		{colormap_html}
	</div>
	{{% endmacro %}}
	""")

	legend_element = MacroElement()
	legend_element._template = legend_template
	return legend_element

def get_popup(row, popup_cols):
	""" Currently unused in favor of vectorized build_popup_series, but kept for reference. """
	rows_html = ''.join([
		f'<tr><td style="padding:2px 6px;font-weight:bold;white-space:nowrap">{col}</td>'
		f'<td style="padding:2px 6px;word-break:break-word">{row[col]}</td></tr>'
		for col in popup_cols if col in row
	])
	return (
		'<div style="max-height:200px;overflow-y:auto;width:280px">'
		f'<table style="border-collapse:collapse;font-size:12px;width:100%">{rows_html}</table>'
		'</div>'
	)


def build_popup_series(df: pd.DataFrame, popup_cols: List[str]) -> pd.Series:
	"""Vectorized popup HTML generation. Returns a Series of popup strings."""
	cols = [c for c in popup_cols if c in df.columns]
	if not cols:
		return pd.Series([''] * len(df), index=df.index)

	prefix = '<div style="max-height:200px;overflow-y:auto;width:280px"><table style="border-collapse:collapse;font-size:12px;width:100%">'
	suffix = '</table></div>'

	# Build per-column HTML row fragments, then sum them column-wise
	parts = None
	for col in cols:
		# Convert to string and HTML-escape unsafe characters in both header and value
		vals = (
			df[col].astype(str)
			.str.replace('&', '&amp;', regex=False)
			.str.replace('<', '&lt;', regex=False)
			.str.replace('>', '&gt;', regex=False)
			.str.replace('"', '&quot;', regex=False)
		)
		safe_col = (
			str(col)
			.replace('&', '&amp;')
			.replace('<', '&lt;')
			.replace('>', '&gt;')
			.replace('"', '&quot;')
		)
		fragment = (
			f'<tr><td style="padding:2px 6px;font-weight:bold;white-space:nowrap">{safe_col}</td>'
			'<td style="padding:2px 6px;word-break:break-word">' + vals + '</td></tr>'
		)
		parts = fragment if parts is None else parts + fragment

	return prefix + parts + suffix

# def get_circle_marker(
# 	lat_col,
# 	lon_col,
# 	popup_html,
# 	edge_color : str = color_scheme['light_mode']['point_edge'],
# 	fill_color : str = color_scheme['light_mode']['point_color']
# ):
# 	return folium.CircleMarker(
# 		location=[lat_col, lon_col],
# 		radius=6,
# 		popup=folium.Popup(popup_html, max_width=300),
# 		color=edge_color,
# 		fill=True,
# 		fillColor=fill_color,
# 		fillOpacity=0.85,
# 		weight=1.5
# 	)


def _warp_band_to_mercator(raster, band: int, max_size: int):
	"""Warp a single raster band to EPSG:3857, downsampled to max_size.
	Returns (data_2d, wgs84_bounds) where bounds = (left, bottom, right, top)."""
	from rasterio.crs import CRS
	from rasterio.transform import from_bounds, array_bounds
	from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_bounds
	import rasterio as _rio

	# We need mercator projection because Folium's ImageOverlay expects pixel coordinates in EPSG:3857.
	# We need wgs84 bounds because Folium's ImageOverlay is georeferenced using lat/lon coordinates.
	mercator = CRS.from_epsg(3857)
	wgs84   = CRS.from_epsg(4326)
	src_crs = raster.crs

	if src_crs and src_crs.to_epsg() == 3857:
		# Just downsample
		scale  = min(max_size / max(raster.height, raster.width), 1.0)
		out_h  = max(1, int(raster.height * scale))
		out_w  = max(1, int(raster.width  * scale))
		data   = raster.read(band, out_shape=(out_h, out_w), resampling=Resampling.average).astype(float)
		bounds = transform_bounds(src_crs, wgs84, *raster.bounds)
	else:
		# Reproject to mercator and downsample
		t, out_w_full, out_h_full = calculate_default_transform(
			src_crs, mercator, raster.width, raster.height, *raster.bounds
		)
		bounds_3857 = array_bounds(out_h_full, out_w_full, t)
		scale  = min(max_size / max(out_h_full, out_w_full), 1.0)
		out_h  = max(1, int(out_h_full * scale))
		out_w  = max(1, int(out_w_full * scale))
		data   = np.empty((out_h, out_w), dtype=float)
		reproject(
			source=_rio.band(raster, band), destination=data,
			src_transform=raster.transform, src_crs=src_crs,
			dst_transform=from_bounds(*bounds_3857, out_w, out_h),
			dst_crs=mercator, resampling=Resampling.average, dst_nodata=np.nan,
		)
		bounds = transform_bounds(mercator, wgs84, *bounds_3857)

	return data, bounds  # bounds = (left, bottom, right, top)


def capture_raster_overlay(raster, band: int = 1, max_size: int = 512) -> Optional[dict]:
	"""Warp a raster band to EPSG:3857 and encode it as a base64 PNG for Folium's
	ImageOverlay. Returns a dict with 'png_b64', WGS84 'bounds', 'vmin', 'vmax',
	or None if the band contains no valid data."""
	try:
		from PIL import Image

		# Downsample and warp the raster band to Web Mercator for efficient display
		data, (left, bottom, right, top) = _warp_band_to_mercator(raster, band, max_size)

		# Create mask of valid data (finite and not nodata value) for proper transparency handling
		nodata = raster.nodata
		valid_mask = np.isfinite(data) & (data != nodata) if nodata is not None else np.isfinite(data)
		if not valid_mask.any():
			return None

		# vmin/vmax from file metadata so point colours and overlay share the same
		# scale even though the overlay is downsampled (averaging compresses extremes).
		try:
			stats = raster.stats(band)
			vmin  = float(stats.min) if nodata is None or stats.min != nodata else float(data[valid_mask].min())
			vmax  = float(stats.max) if nodata is None or stats.max != nodata else float(data[valid_mask].max())
		except Exception:
			vmin, vmax = float(data[valid_mask].min()), float(data[valid_mask].max())

		# Normalize data to 0-1 range based on vmin/vmax, then apply colormap and convert to RGBA
		norm  = np.zeros_like(data) if vmax == vmin else np.clip((data - vmin) / (vmax - vmin), 0.0, 1.0)
		lut   = (mpl_cm.get_cmap('viridis')(np.linspace(0, 1, 256)) * 255).astype(np.uint8)
		rgba  = lut[(np.nan_to_num(norm, nan=0.0) * 255).astype(np.uint8)]
		rgba[~valid_mask, 3] = 0

		# Encode RGBA array as PNG in memory, then base64 for embedding in HTML
		buf = io.BytesIO()
		Image.fromarray(rgba, mode='RGBA').save(buf, format='PNG')

		return {
			'png_b64': base64.b64encode(buf.getvalue()).decode('utf-8'),
			'bounds': [[float(bottom), float(left)], [float(top), float(right)]],
			'vmin': vmin,
			'vmax': vmax,
		}
	except Exception:
		logging.warning("Failed to capture raster overlay; layer will be skipped.")
		logging.warning(traceback.format_exc())
		return None


def get_raster_overlay_layer(overlay_data: dict, name: str = 'Raster Layer') -> folium.raster_layers.ImageOverlay:
	"""Create a folium ImageOverlay from captured raster overlay data."""
	return folium.raster_layers.ImageOverlay(
		image=f"data:image/png;base64,{overlay_data['png_b64']}",
		bounds=overlay_data['bounds'],
		name=name,
		opacity=0.6,
		interactive=False,
		cross_origin=False,
		zindex=1,
	)


def get_shapefile_layer(shapefile_gdf: gpd.GeoDataFrame, color_scheme: dict):
	"""Create a shapefile layer with styled appearance."""
	return folium.GeoJson(
		shapefile_gdf,
		name='Boundary Area',
		style_function=lambda feature: {
		'fillColor': color_scheme["light_mode"]["shape_fill"],
		'color': color_scheme["light_mode"]["shape_border"],
		'weight': 2.5,
		'fillOpacity': 0.7
		},
		highlight_function=lambda feature: {
		'fillColor': color_scheme["light_mode"]["shape_fill"],
		'color': color_scheme["light_mode"]["shape_border"],
		'weight': 3.5,
		'fillOpacity': 0.9
		}
	)

def get_icon_create_func(simple=True):
	if simple:
		return JsCode("""
		function(cluster) {
			var count = cluster.getChildCount();
			var size = 30
			if (count > 100) {
				size = 40;
			}
			if (count > 500) {
				size = 50;
			}

			return L.divIcon({
				html: '<div style="background-color: gray; width: ' + size + 'px; height: ' + size + 'px; border-radius: 50%; display: flex; justify-content: center; align-items: center; color: white; font-weight: bold; border: 2px solid white;">' + count + '</div>',
				className: 'custom-cluster-icon',
				iconSize: L.point(size, size)
			});
		}
		""")
	icon_create_function = JsCode("""
		function(cluster) {
			var children = cluster.getAllChildMarkers();
			var r = 0, g = 0, b = 0;
			var count = children.length;

			// Loop through all markers in the cluster to sum the RGB values
			for (var i = 0; i < count; i++) {
				var hex = children[i].options.customColor;
				if (hex && hex.length === 7) {
					r += parseInt(hex.slice(1, 3), 16);
					g += parseInt(hex.slice(3, 5), 16);
					b += parseInt(hex.slice(5, 7), 16);
				}
			}

			// Calculate the average color
			r = Math.floor(r / count);
			g = Math.floor(g / count);
			b = Math.floor(b / count);

			// Convert back to a hex code
			var hexColor = "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);

			// Determine if the text should be black or white based on background luminance
			var luminance = 0.299 * r + 0.587 * g + 0.114 * b;
			var textColor = luminance > 128 ? 'black' : 'white';

			// Build the HTML for the cluster icon
			var html = '<div style="background-color: ' + hexColor + '; ' +
					'width: 40px; height: 40px; border-radius: 50%; ' +
					'display: flex; justify-content: center; align-items: center; ' +
					'color: ' + textColor + '; font-weight: bold; ' +
					'border: 2px solid white; box-shadow: 0 0 4px rgba(0,0,0,0.5);">' +
					count + '</div>';

			return L.divIcon({
				html: html,
				className: 'custom-cluster-icon',
				iconSize: L.point(40, 40)
			});
		}
		""")
	return icon_create_function

#@st.cache_resource(show_spinner=False)
def display_map(
	df: pd.DataFrame,
	lat_col: str,
	lon_col: str,
	_shapefile_gdf: Optional[gpd.GeoDataFrame] = None,
	_raster_overlay: Optional[dict] = None,
	selected_band: Optional[str] = None,
	popup_cols: Optional[List[str]] = None,
	high_res_shape_map: bool = False,
	use_clustering: str = 'auto',
	clustering_threshold: int = 500
):
	"""
	Display an interactive Folium map with points and optional shapefile boundaries.

	Args:
		df: DataFrame with coordinates
		lat_col: Name of latitude column
		lon_col: Name of longitude column
		_shapefile_gdf: Optional GeoDataFrame with shapefile boundaries to overlay
		_raster_overlay: Optional dict from capture_raster_overlay() to add a raster image layer
		popup_cols: Optional list of column names to show in marker popups
		use_clustering: 'auto' (default), 'always', or 'never'. Auto uses FastMarkerCluster for 500+ points.
		clustering_threshold: Number of points above which to use clustering when use_clustering='auto'

	Returns:
		Folium map object wrapped in streamlit_folium component
	"""

	# Determine if clustering should be used
	num_points = len(df)
	if use_clustering == 'never':
		should_cluster = False
	elif use_clustering == 'always' or (use_clustering == 'auto' and num_points > clustering_threshold):
		should_cluster = True
	else:
		should_cluster = False

	# Pre-filter rows missing coordinates
	df = df.dropna(subset=[lat_col, lon_col])

	# Create base map
	m = folium.Map(
		location=[df[lat_col].mean(), df[lon_col].mean()],
		zoom_start=10,
		tiles='OpenStreetMap'
	)

	# Add alternative tile layers
	folium.TileLayer('CartoDB dark_matter', name='Dark Map').add_to(m)
	folium.TileLayer('CartoDB positron', name='Light Map').add_to(m)

	# If shapefile provided, add it as a layer (simplify geometry to reduce payload).
	# Tolerance is scaled to the bounding box diagonal so small areas keep detail
	# and very large polygons get aggressive simplification.
	if _shapefile_gdf is not None and not _shapefile_gdf.empty:
		if high_res_shape_map:
			simplified = _shapefile_gdf
		else:
			try:
				# Scale tolerance to median feature size, not overall bbox, so small
				# grid cells aren't collapsed (a bbox-based tolerance can exceed cell size).
				bounds = _shapefile_gdf.geometry.bounds
				feature_diags = np.hypot(
					(bounds['maxx'] - bounds['minx']).to_numpy(),
				(bounds['maxy'] - bounds['miny']).to_numpy()
				)
				# Use 5th percentile of feature diagonals — protects the smallest real
				# features without being skewed by degenerate near-zero geometries.
				median_diag = float(np.percentile(feature_diags[feature_diags > 0], 5))
				tolerance = max(median_diag * 0.001, 1e-6)
				simplified = _shapefile_gdf.copy()
				simplified['geometry'] = simplified.geometry.simplify(
					tolerance=tolerance, preserve_topology=True
				)
			except Exception:
				simplified = _shapefile_gdf
		shapefile_layer = get_shapefile_layer(simplified, color_scheme)
		shapefile_layer.add_to(m)

	# Raster image overlay — sits beneath the point markers
	if _raster_overlay is not None:
		try:
			raster_layer = get_raster_overlay_layer(_raster_overlay)
			raster_layer.add_to(m)
		except Exception:
			logging.warning("Failed to add raster overlay layer to map")

	# Prepare popup columns
	if popup_cols is None:
		popup_cols = [lat_col, lon_col]

	# Vectorized popup generation (one pass over the DataFrame)
	popups = build_popup_series(df, popup_cols).to_numpy()
	lats = df[lat_col].to_numpy()
	lons = df[lon_col].to_numpy()

	if selected_band is not None:
		band_values = df[selected_band].to_numpy()
		valid_mask = ~pd.isna(band_values)
		valid_vals = band_values[valid_mask]

		# Use the raster overlay's global min/max if available so point colors
		# match the overlay colormap exactly. Fall back to point-range normalization.
		if _raster_overlay is not None:
			min_val = float(_raster_overlay['vmin'])
			max_val = float(_raster_overlay['vmax'])
			print('Using raster overlay min/max for point color normalization')
		elif valid_vals.size > 0:
			min_val = float(valid_vals.min())
			max_val = float(valid_vals.max())
		else:
			min_val, max_val = 0.0, 1.0

		norm = Normalize(vmin=min_val, vmax=max_val)
		cmap = mpl_cm.get_cmap('viridis')

		# Vectorized color computation: compute RGBA for all valid values at once
		colors = np.full(len(df), 'gray', dtype=object)
		if valid_vals.size > 0:
			rgba = cmap(norm(valid_vals))  # shape (n_valid, 4)
			r = (rgba[:, 0] * 255).astype(np.uint8)
			g = (rgba[:, 1] * 255).astype(np.uint8)
			b = (rgba[:, 2] * 255).astype(np.uint8)
			hex_colors = np.array([f'#{ri:02x}{gi:02x}{bi:02x}' for ri, gi, bi in zip(r, g, b)], dtype=object)
			colors[valid_mask] = hex_colors

		marker_cluster = create_marker_cluster_custom(lats, lons, popups, colors, disable_clustering=not should_cluster)
		marker_cluster.add_to(m)

		colormap = cm.linear.viridis.scale(min_val, max_val)
		ticks = list(np.linspace(min_val, max_val, 5))
		colormap.tick_labels = [f"{round(t, 2)}" for t in ticks]
		colormap.add_to(m)

	else:
		marker_cluster = create_marker_cluster(lats, lons, popups, color_scheme, disable_clustering=not should_cluster)
		marker_cluster.add_to(m)

	# Add layer control
	folium.LayerControl().add_to(m)

	if len(df) > 0:
		bounds = [
			[float(lats.min()), float(lons.min())],
			[float(lats.max()), float(lons.max())]
		]
		m.fit_bounds(bounds, padding=[50, 50])
	map_html = m._repr_html_()
	return m, map_html



def create_and_save_map(
	shape: gpd.GeoDataFrame,
	joined: gpd.GeoDataFrame,
	config: Config
):
	"""
	Create and optionally save a map visualization.
	Only used for CLI mode since Streamlit version has interactive map display and download options.
	"""
	save_to_map = config.get_bool('save_map_image', prompt="Do you want to save a map of the joined data? (y/n): ")
	if save_to_map:
		map_path = config.get_env(
			'output_map',
			prompt="Enter the full path to save the map image (including extension):\n",
			case_sensitive=True
		)
		import matplotlib
		matplotlib.use('Agg')  # Use non-interactive backend to avoid Tkinter issues
		import matplotlib.pyplot as plt
		import contextily as ctx
		from matplotlib.patches import Rectangle

		BACKGROUND_COLOR = '#F8F9FA'  # Soft white
		SHAPE_FILL = '#E8F4F8'  # Soft blue
		SHAPE_BORDER = '#4A90E2'  # Modern blue
		POINT_COLOR = '#FF6B6B'  # coral red
		POINT_EDGE = '#2C3E50'  # Dark blue-grey
		TITLE_COLOR = '#2C3E50'  # Dark blue-grey

		shape_proj = shape.to_crs(epsg=4326)
		joined_proj = joined.to_crs(shape_proj.crs)

		# Calculate bounds and aspect ratio
		minx, miny, maxx, maxy = shape_proj.total_bounds
		x_pad = (maxx - minx) * 0.15
		y_pad = (maxy - miny) * 0.15

		# Calculate aspect ratio from actual data bounds
		width = (maxx - minx) + 2 * x_pad
		height = (maxy - miny) + 2 * y_pad
		aspect_ratio = width / height

		# Set figure size based on aspect ratio (base height of 10 inches)
		base_height = 10
		fig_width = base_height * aspect_ratio
		# Limit width to reasonable range
		fig_width = max(8, min(fig_width, 16))

		# Create figure with dynamic sizing
		fig, ax = plt.subplots(figsize=(fig_width, base_height), facecolor=BACKGROUND_COLOR)
		ax.set_facecolor(BACKGROUND_COLOR)
		ax.set_aspect('equal')  # Maintain geographic proportions

		ax.set_xlim(minx - x_pad, maxx + x_pad)
		ax.set_ylim(miny - y_pad, maxy + y_pad)

		# Use modern, clean basemap
		try:
			basemap, extent = ctx.bounds2img(
				minx - x_pad, miny - y_pad, maxx + x_pad, maxy + y_pad,
				zoom=11,
				source=ctx.providers.CartoDB.Positron
			)
			ax.imshow(basemap, extent=extent, zorder=0, alpha=0.6)
		except Exception as e:
			# Fallback if basemap fails - just use solid background
			logging.warning(f"Basemap loading failed: {str(e)}")
			print(f"Note: Using simplified map without basemap tiles")

		# Plot shape
		shape_proj.plot(
			ax=ax,
			facecolor=SHAPE_FILL,
			edgecolor=SHAPE_BORDER,
			linewidth=2.5,
			alpha=0.7,
			zorder=1
		)

		# Add sshadow for shapes
		shape_proj.plot(
			ax=ax,
			facecolor='none',
			edgecolor=SHAPE_BORDER,
			linewidth=4,
			alpha=0.2,
			zorder=0.9
		)

		# Plot points
		joined_proj.plot(
			ax=ax,
			color=POINT_COLOR,
			markersize=80,
			edgecolor=POINT_EDGE,
			linewidth=1.5,
			alpha=0.85,
			zorder=3
		)

		# Add glow effect for points
		joined_proj.plot(
			ax=ax,
			color=POINT_COLOR,
			markersize=120,
			edgecolor='none',
			alpha=0.15,
			zorder=2.9
		)

		# Add title
		plt.title(
			f'Location Mapping Results\n{len(joined_proj)} points within boundary',
			fontsize=18,
			fontweight='bold',
			color=TITLE_COLOR,
			pad=20,
			family='sans-serif'
		)

		# Create custom legend with modern styling
		from matplotlib.lines import Line2D
		legend_elements = [
			Line2D([0], [0], marker='o', color='w',
				   markerfacecolor=POINT_COLOR, markeredgecolor=POINT_EDGE,
				   markersize=10, linewidth=0, label='Matched Locations'),
			Line2D([0], [0], color=SHAPE_BORDER, linewidth=2.5,
				   label='Boundary Area')
		]
		legend = ax.legend(
			handles=legend_elements,
			loc='upper right',
			fontsize=11,
			frameon=True,
			fancybox=True,
			shadow=True,
			framealpha=0.95,
			edgecolor=SHAPE_BORDER,
			facecolor='white'
		)

		# Remove axes for cleaner look
		ax.set_axis_off()

		# Tight layout to remove extra whitespace
		plt.tight_layout(pad=0.5)

		try:
			fig.savefig(map_path, bbox_inches='tight', dpi=300, facecolor=BACKGROUND_COLOR, pad_inches=0.3)
			print(f"Map image saved to {map_path}")
		except Exception as e:
			logging.error(f"Failed to save map image to '{map_path}'")
			logging.error(traceback.format_exc())
			print(f"\n❌ Error: Failed to save map image to '{map_path}'")
			print(f"   Reason: {str(e)}")
