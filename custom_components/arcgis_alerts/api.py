"""A small client for the ArcGIS REST API feature layer endpoints."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

REQUEST_TIMEOUT = 30
# Pages fetched in one update before giving up on a layer that keeps
# reporting exceededTransferLimit; at the usual maxRecordCount of 1000-2000
# this is tens of thousands of features, more than local mode suits.
MAX_PAGES = 10


class ArcGISError(Exception):
    """The layer answered, but with an error or an unusable body."""


class ArcGISConnectionError(ArcGISError):
    """The layer could not be reached."""


class ArcGISClient:
    """Read one ArcGIS feature layer."""

    def __init__(self, session: aiohttp.ClientSession, layer_url: str) -> None:
        """Initialize the client."""
        self._session = session
        self.layer_url = layer_url.rstrip("/")

    async def _get(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        """GET a URL with f=json and return the decoded body.

        ArcGIS answers many errors with HTTP 200 and an `error` object, so
        the body is checked as well as the status.
        """
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.get(url, params={**params, "f": "json"})
                response.raise_for_status()
                body = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ArcGISConnectionError(f"Error reaching {url}: {err}") from err
        except ValueError as err:
            raise ArcGISError(f"{url} did not return JSON") from err
        if not isinstance(body, dict):
            raise ArcGISError(f"{url} returned an unexpected body")
        if "error" in body:
            error = body["error"] or {}
            raise ArcGISError(
                f"ArcGIS error {error.get('code')}: {error.get('message')} "
                f"{error.get('details') or ''}".strip()
            )
        return body

    async def async_get_layer_info(self) -> dict[str, Any]:
        """Return the layer's metadata."""
        return await self._get(self.layer_url, {})

    async def async_query(
        self,
        where: str,
        out_fields: str,
        *,
        point: tuple[float, float] | None = None,
        return_geometry: bool = False,
    ) -> dict[str, Any]:
        """Query the layer and return the body with every page's features.

        `point` is (longitude, latitude) in WGS 84; when given, the server
        filters to features that intersect it.
        """
        params: dict[str, str] = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true" if return_geometry else "false",
            "outSR": "4326",
        }
        if return_geometry:
            params["geometryPrecision"] = "6"
        if point is not None:
            params.update(
                {
                    "geometry": f"{point[0]},{point[1]}",
                    "geometryType": "esriGeometryPoint",
                    "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                }
            )

        url = f"{self.layer_url}/query"
        first = await self._get(url, params)
        features = list(first.get("features") or [])
        page = first
        pages = 1
        while page.get("exceededTransferLimit") and pages < MAX_PAGES:
            page = await self._get(url, {**params, "resultOffset": str(len(features))})
            if not page.get("features"):
                break
            features.extend(page["features"])
            pages += 1
        if page.get("exceededTransferLimit"):
            raise ArcGISError(
                f"{self.layer_url} returned more than {len(features)} features; "
                "narrow the where clause or use the server query mode"
            )
        first["features"] = features
        return first
