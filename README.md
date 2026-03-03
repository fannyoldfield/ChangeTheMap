# Green Pixels Europe (TRL-5 Prototype)

Green Pixels Europe is a production-style web prototype that demonstrates **satellite-verified vegetation greening** and **urban heat anomaly** detection for a selected location in Europe using **real Copernicus Sentinel data**.

## What it does

- Lets users pick a location by map click or latitude/longitude input.
- Compares **baseline period NDVI** vs **current period NDVI**.
- Applies Sentinel-2 cloud masking using the **Scene Classification Layer (SCL)** and rejects scenes with >30% cloudy pixels in the sampled area.
- Computes NDVI from Sentinel-2 Level-2A surface reflectance:
  - NDVI = (B8 - B4) / (B8 + B4)
- Uses a local window (~100m x 100m) around the selected coordinate.
- Pulls Sentinel-3 SLSTR LST and calculates temperature anomaly against surrounding ~1km neighborhood.
- Returns analysis JSON payload and NDVI time-series plot.

## Data sources

- **NDVI:** Copernicus Sentinel-2 L2A (`sentinel-2-l2a`) via Microsoft Planetary Computer STAC API.
- **Thermal:** Copernicus Sentinel-3 SLSTR LST L2 (`sentinel-3-slstr-lst-l2-netcdf`) via Microsoft Planetary Computer STAC API.

## Architecture

- **Frontend:** React + Vite + React Leaflet + Chart.js
- **Backend:** FastAPI + rasterio + pystac-client + planetary-computer
- **Containerization:** Docker + docker-compose

## API response shape

`POST /analyze`

```json
{
  "location": {"latitude": 52.52, "longitude": 13.405},
  "baseline_ndvi": 0.42,
  "current_ndvi": 0.49,
  "ndvi_change": 16.6,
  "baseline_lst": 23.1,
  "current_lst": 25.4,
  "lst_anomaly": 1.2
}
```

Additional fields include:
- `seasonal_normalized_ndvi_change`
- `baseline_lst_anomaly`
- `time_series` (baseline/current observations)
- `data_sources`

## Seasonal normalization logic

This prototype performs basic seasonal normalization by comparing equivalent seasonal windows selected by users (e.g., June vs June) and includes a stabilized normalized NDVI delta:

- `seasonal_normalized_ndvi_change = (current_ndvi - baseline_ndvi) / max(|baseline_ndvi|, 0.05)`

## Local deployment

### Option A: Docker Compose

```bash
docker compose up --build
```

- Frontend: `http://localhost:5173`
- Backend API docs: `http://localhost:8000/docs`

### Option B: Manual

Backend:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:
```bash
cd appfrontend
npm install
npm run dev
```

## Spatial/temporal resolution limitations

- Sentinel-2 NDVI calculated from 10m bands, but result is aggregated over a small local window (~100m x 100m).
- Sentinel-3 SLSTR LST has coarser thermal resolution than Sentinel-2 optical bands, so heat anomaly is less spatially granular.
- Temporal revisit and cloud availability can reduce usable observations.

## Known limitations

- Cloud/snow contamination can still affect observations despite SCL masking.
- Date windows with persistent cloud may return no results.
- Thermal and NDVI products have different spatial footprints and acquisition dynamics.
- LST anomaly uses a simple local 1km neighborhood baseline, not a full urban climatology model.

