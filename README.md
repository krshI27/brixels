# Brixels

A Streamlit web app that visualizes global elevation data as LEGO-style brick maps. Each brick's height and color represents the terrain elevation at that location, turning the world into an interactive LEGO model.

## Features

- Interactive map with zoom levels 1-10, loading pre-computed elevation grids from Cloudflare R2
- Isometric 3D brick rendering via dynamically generated SVGs
- Multiple scientific colormaps (GMT, SCM) for elevation styling
- Switchable basemaps (OpenStreetMap, CartoDB, Stamen Terrain)
- Water/land toggle and color mode selection (absolute elevation vs. quantized height)
- Sidebar with a LEGO brick scale diagram showing real-world dimensions per zoom level

## Setup

### Prerequisites

- [Conda](https://docs.conda.io/) or [Mamba](https://mamba.readthedocs.io/)
- Cloudflare R2 credentials (see `.streamlit/secrets.toml.template`)

### Install

```bash
mamba env create -f environment.yml
mamba activate brixels
```

Copy the secrets template and fill in your R2 credentials:

```bash
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
```

### Run

```bash
streamlit run app.py
```

### Docker

```bash
docker compose up --build
```

The app will be available at `http://localhost:8502`.

## Project Structure

```
app.py                  # Main Streamlit application
src/
  r2_storage.py         # Cloudflare R2 tile loading with local fallback
  cog_sampler.py        # On-demand elevation sampling from COG
cmaptools/              # Custom colormap parsing (CPT format)
cpt/                    # Scientific colormap files (GMT, SCM, etc.)
static/                 # CSS and brick assets
scripts/                # Data preparation utilities
  convert_to_parquet.py # GeoPackage to GeoParquet conversion
  prepare_r2_data.py    # R2 upload pipeline
  create_cog.py         # NASADEM to Cloud-Optimized GeoTIFF
```
