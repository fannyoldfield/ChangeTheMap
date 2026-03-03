from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from processor import (
    DataProcessingError,
    compute_lst_average,
    compute_ndvi_series,
    seasonal_normalized_change,
)

app = FastAPI(title="Green Pixels Europe API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    baseline_start: date
    baseline_end: date
    current_start: date
    current_end: date


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze")
def analyze(req: AnalysisRequest) -> dict:
    try:
        baseline_ndvi = compute_ndvi_series(
            req.latitude, req.longitude, req.baseline_start, req.baseline_end
        )
        current_ndvi = compute_ndvi_series(
            req.latitude, req.longitude, req.current_start, req.current_end
        )

        baseline_lst, baseline_surrounding = compute_lst_average(
            req.latitude, req.longitude, req.baseline_start, req.baseline_end
        )
        current_lst, current_surrounding = compute_lst_average(
            req.latitude, req.longitude, req.current_start, req.current_end
        )

        ndvi_change = ((current_ndvi.mean_ndvi - baseline_ndvi.mean_ndvi) / baseline_ndvi.mean_ndvi) * 100 if baseline_ndvi.mean_ndvi != 0 else 0
        seasonal_change = seasonal_normalized_change(
            baseline_ndvi.mean_ndvi, current_ndvi.mean_ndvi
        )
        lst_anomaly = current_lst - current_surrounding

        return {
            "location": {"latitude": req.latitude, "longitude": req.longitude},
            "baseline_ndvi": baseline_ndvi.mean_ndvi,
            "current_ndvi": current_ndvi.mean_ndvi,
            "ndvi_change": ndvi_change,
            "seasonal_normalized_ndvi_change": seasonal_change,
            "baseline_lst": baseline_lst,
            "current_lst": current_lst,
            "lst_anomaly": lst_anomaly,
            "baseline_lst_anomaly": baseline_lst - baseline_surrounding,
            "time_series": {
                "baseline": baseline_ndvi.observations,
                "current": current_ndvi.observations,
            },
            "data_sources": {
                "ndvi": "Copernicus Sentinel-2 L2A via Microsoft Planetary Computer STAC",
                "temperature": "Copernicus Sentinel-3 SLSTR LST L2 via Microsoft Planetary Computer STAC",
            },
        }
    except DataProcessingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected processing error: {exc}") from exc
