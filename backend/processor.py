from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import planetary_computer
import rasterio
from pyproj import Transformer
from pystac_client import Client
from rasterio.windows import from_bounds
from shapely.geometry import Point
from shapely.ops import transform as shapely_transform

EARTH_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
S2_COLLECTION = "sentinel-2-l2a"
S3_LST_COLLECTION = "sentinel-3-slstr-lst-l2-netcdf"

WGS84_TO_WEBM = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
WEBM_TO_WGS84 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)


@dataclass
class NdviResult:
    mean_ndvi: float
    observations: list[dict[str, Any]]


class DataProcessingError(Exception):
    pass


def _bbox_from_point(lat: float, lon: float, meters: float) -> tuple[float, float, float, float]:
    center = Point(lon, lat)
    point_m = shapely_transform(WGS84_TO_WEBM.transform, center)
    buffered = point_m.buffer(meters)
    return shapely_transform(WEBM_TO_WGS84.transform, buffered).bounds


def _read_window_mean(href: str, bbox: tuple[float, float, float, float]) -> tuple[np.ndarray, rasterio.Affine]:
    with rasterio.open(href) as src:
        win = from_bounds(*bbox, transform=src.transform)
        data = src.read(1, window=win, masked=True)
        transform = src.window_transform(win)
        return np.ma.array(data), transform


def _compute_ndvi_for_item(item: Any, bbox: tuple[float, float, float, float]) -> float | None:
    red_href = planetary_computer.sign(item.assets["B04"].href)
    nir_href = planetary_computer.sign(item.assets["B08"].href)
    scl_href = planetary_computer.sign(item.assets["SCL"].href)

    red, _ = _read_window_mean(red_href, bbox)
    nir, _ = _read_window_mean(nir_href, bbox)
    scl, _ = _read_window_mean(scl_href, bbox)

    cloud_mask = np.isin(scl.filled(0), [3, 8, 9, 10, 11])  # cloud shadow, cloud probs, cirrus, snow
    valid = (~cloud_mask) & (~red.mask) & (~nir.mask) & (red + nir > 0)
    if valid.size == 0:
        return None

    cloud_fraction = cloud_mask.sum() / cloud_mask.size
    if cloud_fraction > 0.3:
        return None

    red_arr = red.filled(np.nan).astype(np.float32)
    nir_arr = nir.filled(np.nan).astype(np.float32)
    ndvi = (nir_arr - red_arr) / (nir_arr + red_arr)
    ndvi[~valid] = np.nan

    if np.isnan(ndvi).all():
        return None
    return float(np.nanmean(ndvi))


def compute_ndvi_series(
    lat: float,
    lon: float,
    start_date: date,
    end_date: date,
    box_size_m: float = 50,
) -> NdviResult:
    bbox = _bbox_from_point(lat, lon, box_size_m)
    catalog = Client.open(EARTH_SEARCH_URL)

    search = catalog.search(
        collections=[S2_COLLECTION],
        bbox=list(bbox),
        datetime=f"{start_date.isoformat()}/{end_date.isoformat()}",
        query={"eo:cloud_cover": {"lt": 30}},
    )

    observations = []
    for item in search.items():
        ndvi = _compute_ndvi_for_item(item, bbox)
        if ndvi is None:
            continue
        observations.append({"date": item.datetime.date().isoformat(), "ndvi": ndvi})

    if not observations:
        raise DataProcessingError("No cloud-free Sentinel-2 observations found for the requested period.")

    observations.sort(key=lambda x: x["date"])
    mean_ndvi = float(np.mean([o["ndvi"] for o in observations]))
    return NdviResult(mean_ndvi=mean_ndvi, observations=observations)


def _compute_lst_for_item(item: Any, lat: float, lon: float) -> tuple[float, float] | None:
    if "LST" not in item.assets:
        return None

    href = planetary_computer.sign(item.assets["LST"].href)
    with rasterio.open(href) as src:
        row, col = src.index(lon, lat)
        if row < 0 or col < 0 or row >= src.height or col >= src.width:
            return None

        point_window = rasterio.windows.Window(col, row, 1, 1)
        point_temp = src.read(1, window=point_window, masked=True).astype(np.float32)
        if point_temp.mask.all():
            return None

        res_deg = max(abs(src.transform.a), abs(src.transform.e))
        radius_px = max(1, int((1000 / 111320) / res_deg))
        buf_window = rasterio.windows.Window(
            max(0, col - radius_px),
            max(0, row - radius_px),
            min(src.width - max(0, col - radius_px), radius_px * 2 + 1),
            min(src.height - max(0, row - radius_px), radius_px * 2 + 1),
        )
        buf_arr = src.read(1, window=buf_window, masked=True).astype(np.float32)
        if buf_arr.mask.all():
            return None

        point_c = float(point_temp.filled(np.nan)[0, 0] - 273.15)
        surrounding_c = float(np.nanmean(buf_arr.filled(np.nan) - 273.15))
        return point_c, surrounding_c


def compute_lst_average(lat: float, lon: float, start_date: date, end_date: date) -> tuple[float, float]:
    bbox = _bbox_from_point(lat, lon, 500)
    catalog = Client.open(EARTH_SEARCH_URL)
    search = catalog.search(
        collections=[S3_LST_COLLECTION],
        bbox=list(bbox),
        datetime=f"{start_date.isoformat()}/{end_date.isoformat()}",
    )

    points = []
    surroundings = []
    for item in search.items():
        result = _compute_lst_for_item(item, lat, lon)
        if result is None:
            continue
        p, s = result
        points.append(p)
        surroundings.append(s)

    if not points:
        raise DataProcessingError("No Sentinel-3 SLSTR LST observations found for requested period.")

    return float(np.mean(points)), float(np.mean(surroundings))


def seasonal_normalized_change(baseline: float, current: float) -> float:
    # Basic seasonal normalization: denominator stabilizes differences in low-vegetation periods.
    denom = max(abs(baseline), 0.05)
    return float((current - baseline) / denom)


def month_window(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end
