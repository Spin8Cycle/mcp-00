 
from typing import Any
import httpx
from datetime import datetime, timezone, timedelta
from fastmcp import FastMCP

# %%
USGS_API_BASE = 'https://earthquake.usgs.gov/fdsnws/event/1/query'
USER_AGENT = 'earthquake-app/1.0'

mcp = FastMCP('earthquake_server')

async def make_usgs_request(url : str, params: dict[str, Any]) -> dict[str, Any] | None:
    """
    Make a request on the USGS Earthquake API w/ proper error handling.
    """

    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'application/geo+json',
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            print(f"Network error while requesting {e.request.url!r}: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
    
    return None

async def make_geocoding_request(location_name: str) -> dict[str, Any] | None:
    """
    Make a request to the Nominatim Geocoding API.
    """

    geocode_url = "https://nominatim.openstreetmap.org/search"
    params_geo = {
        "q": location_name,
        "format": "json",
        "limit": 1,
    }

    async with httpx.AsyncClient() as client:
        try:
            geo_resp = await client.get(geocode_url, params=params_geo, timeout=15.0)
            geo_resp.raise_for_status()
            results = geo_resp.json()
            if not results:
                return (" Could not find location for '{location_name}'.")
            loc = results[0]
            latitude = float(loc["lat"])
            longitude = float(loc["lon"])
            return {"lat": latitude, "lon": longitude}
        except Exception as e:
            err_msg = f"Geocoding failed for '{location_name}': {e}"
            return err_msg

def format_usgs_request(feature: dict[str, Any]) -> str:
    """
    Format a USGS earthquake feature into a readable string with timestamp and coordinates.
    """
    props = feature["properties"]
    geom = feature.get("geometry", {})

    mag = props.get("mag", "N/A")
    place = props.get("place", "Unknown location")
    time_ms = props.get("time")
    url = props.get("url", "No URL available")

    # Convert timestamp (in milliseconds) to readable UTC time
    time_str = (
        datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if time_ms
        else "Unknown time"
    )

    # Coordinates: [longitude, latitude, depth]
    coords = geom.get("coordinates", [None, None, None])
    lon, lat, depth = coords if len(coords) == 3 else (None, None, None)

    return f"""
    🌎 Earthquake Report
    --------------------
    📍 Location: {place}
    💥 Magnitude: {mag}
    ⏱  Time: {time_str}
    📏 Depth: {depth} km
    🌐 Coordinates: lat={lat}, lon={lon}
    🔗 More info: {url}
    """

@mcp.tool()
async def get_earthquakes(
    start_time: str,
    end_time: str | None = None,
    min_magnitude: float | None = 3.0,
    max_results: int | None = 4,
) -> str:
    """
    Fetch recent earthquake data from the USGS API.
    Args:
        start_time: Start time (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        end_time: End time (optional). If not provided, uses current UTC time.
        min_magnitude: Minimum magnitude filter.
        max_results: Maximum number of earthquakes to include in output.
    Returns:
        A formatted string summary of recent earthquakes.
    """
    if not end_time:
        end_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    params = {
        "format": "geojson",
        "starttime": start_time,
        "endtime": end_time,
        "minmagnitude": min_magnitude,
        "orderby": "time",
        "limit": max_results,
    }
    
    data = await make_usgs_request(USGS_API_BASE, params)
    if not data or not data.get("features"):
        return "No recent earthquakes found for the given filters."

    features = data['features'][:max_results]
    results = []
    for feature in features:
        results.append(format_usgs_request(feature))

    return "\n".join(results)

@mcp.tool()
async def get_earthquake_stats(
    start_time: str,
    end_time: str | None = None,
    min_magnitude: float | None = 4.0
) -> dict[str, Any]:
    """
    Compute earthquake statistics (count, average magnitude, largest quake).
    Args:
        start_time: ISO start date (e.g., '2025-10-01')
        end_time: ISO end date (defaults to now)
        min_magnitude: Filter threshold
    Returns:
        JSON with aggregate statistics.
    """

    if not end_time:
        end_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    params = {
        "format": "geojson",
        "starttime": start_time,
        "endtime": end_time,
        "minmagnitude": min_magnitude,
        "orderby": "time",
    }

    data = await make_usgs_request(USGS_API_BASE, params)
    if not data or not data.get("features"):
        return {"count": 0, "average_magnitude": 0, "largest_magnitude": 0, "message": "No earthquakes found."}
    
    mags = [f["properties"].get("mag") for f in data["features"] if f["properties"].get("mag") is not None]
    if not mags:
        return {"count": 0, "average_magnitude": 0, "largest_magnitude": 0}
    
    avg_mag = round(sum(mags) / len(mags), 2)
    max_mag = max(mags)

    return {
        "num_events": len(mags),
        "average_magnitude": avg_mag,
        "largest_magnitude": max_mag,
        "start_time": start_time,
        "end_time": end_time,
        "source": "USGS Earthquake API"
    }

@mcp.tool()
async def search_earthquake_by_place(
    #latitude: float,
    #longitude: float,
    location: str,
    radius_km: float = 300,
    start_time: str | None = None,
    end_time: str | None = None,
    min_magnitude: float | None = None,
    max_results: int = 10
) -> dict[str, Any] | str:
    """
    Search earthquakes within a circular region around (latitude, longitude).

    Args:
        location: Location name to geocode (e.g., "San Francisco, CA")
        radius_km: Search radius in kilometers (USGS param: maxradiuskm).
        start_time: ISO 8601 start time (e.g., '2025-10-01' or '2025-10-01T00:00:00').
                    Defaults to 7 days ago (UTC) if not provided.
        end_time: ISO 8601 end time, defaults to now (UTC).
        min_magnitude: Optional minimum magnitude filter.
        max_results: Max number of features to return (USGS 'limit').
    Returns:
        Either a formatted string of reports or a JSON dict with metadata + features.
    """
     # Defaults for time window
     
    if end_time is None:
        end_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    if start_time is None:
        start_time = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")

    geo_data = await make_geocoding_request(location)
    if not geo_data:    
        return f"Unable to geocode location: {location}" 
    
    latitude = geo_data['lat']
    longitude = geo_data['lon']

    # Build USGS params for circular/region search
    params: dict[str, Any] = {
        "format": "geojson",
        "latitude": latitude,
        "longitude": longitude,
        "maxradiuskm": radius_km,
        "starttime": start_time,
        "endtime": end_time,
        "orderby": "time",
        "limit": max_results,
    }

    if min_magnitude is not None:
        params["minmagnitude"] = min_magnitude

    data = await make_usgs_request(USGS_API_BASE, params)
    if not data or not data.get("features"):
        return ("No earthquakes found for the given region/time window.")

    features = data['features'][:max_results]
    results = []
    for feature in features:
        results.append(format_usgs_request(feature))

    return "\n".join(results)


def main():
    # Initialize and run the server
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()