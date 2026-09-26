"""Location mapper UI tab package."""

from .shapefile_tab import render_shapefile_tab
from .raster_tab import render_raster_tab

__all__ = [
    "render_shapefile_tab",
    "render_raster_tab",
]
