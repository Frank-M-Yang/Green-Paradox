"""Registry of the open data sources Canopy Care uses.

All sources are published on data.gov.sg under the Singapore Open Data Licence.
Dataset IDs were confirmed against the live API on 2026-11-21 (see data/REPORT.md).

kind:
  "file"     a downloadable dataset file (GeoJSON, XLSX ...), fetched through the
             documented poll-download endpoint
  "realtime" a v2 real-time API endpoint that returns JSON readings

every_days:  how often scripts/refresh.py downloads the source again. Slow-changing
             files are checked through their metadata first and downloaded only when
             the publisher's "last updated" time has moved.
"""

API_META = "https://api-production.data.gov.sg/v2/public/api"
API_DOWNLOAD = "https://api-open.data.gov.sg/v1/public/api"
API_REALTIME = "https://api-open.data.gov.sg/v2/real-time/api"

LICENCE = "Singapore Open Data Licence v1.0"
LICENCE_URL = "https://data.gov.sg/open-data-licence"

# ---------------------------------------------------------------------------
# Sources the daily refresh uses.
# ---------------------------------------------------------------------------
SOURCES = [
    {
        "key": "dengue_clusters",
        "title": "Dengue Clusters (GEOJSON)",
        "agency": "National Environment Agency",
        "kind": "file",
        "dataset_id": "d_dbfabf16158d1b0e1c420627c0819168",
        "collection_id": "1441",
        "every_days": 1,
    },
    {
        "key": "high_aedes_areas",
        "title": "Areas with High Aedes Population (GEOJSON)",
        "agency": "National Environment Agency",
        "kind": "file",
        "dataset_id": "d_5d060d8b7838a15e8906fb22c50dbf51",
        "collection_id": "1431",
        "every_days": 1,
        "only_if_changed": True,
    },
    {
        "key": "parks",
        "title": "Parks",
        "agency": "National Parks Board",
        "kind": "file",
        "dataset_id": "d_0542d48f0991541706b58059381a6eca",
        "collection_id": "1491",
        "every_days": 7,
    },
    {
        "key": "park_facilities",
        "title": "Park Facilities",
        "agency": "National Parks Board",
        "kind": "file",
        "dataset_id": "d_14d807e20158338fd578c2913953516e",
        "collection_id": "1495",
        "every_days": 7,
    },
    {
        # Not in the brief. Park outlines for the offline map.
        "key": "park_polygons",
        "title": "NParks Parks and Nature Reserves",
        "agency": "National Parks Board",
        "kind": "file",
        "dataset_id": "d_77d7ec97be83d44f61b85454f844382f",
        "collection_id": "1489",
        "every_days": 7,
    },
    {
        # Not in the brief. Stands in for NParks Skyrise Greenery, which is unpublished.
        "key": "community_gardens",
        "title": "Community in Bloom (CIB)",
        "agency": "National Parks Board",
        "kind": "file",
        "dataset_id": "d_f91a8b057cfb2bebf2e531ad8061e1c1",
        "collection_id": "1479",
        "every_days": 30,
        "only_if_changed": True,
    },
    {
        # The brief listed d_ea075550f96f7bcc1c87f8cdc2527156, which no longer exists.
        "key": "pub_water_level_sensors",
        "title": "PUB Water Level Sensors",
        "agency": "PUB, Singapore's national water agency",
        "kind": "file",
        "dataset_id": "d_31333fa5cf0834f012d840365b336610",
        "collection_id": "1541",
        "every_days": 30,
        "only_if_changed": True,
    },
    {
        # Not in the brief. Defines the neighbourhood and frames the map.
        "key": "subzone_boundaries",
        "title": "Master Plan 2019 Subzone Boundary (No Sea) (GEOJSON)",
        "agency": "Urban Redevelopment Authority",
        "kind": "file",
        "dataset_id": "d_8594ae9ff96d0c708bc2af633048edfb",
        "collection_id": None,
        "every_days": 30,
        "only_if_changed": True,
    },
    {
        # Not in the brief. Canals and water bodies for the offline map.
        "key": "waterbodies",
        "title": "Master Plan 2025 SDCP Waterbody layer",
        "agency": "Urban Redevelopment Authority",
        "kind": "file",
        "dataset_id": "d_7e2ac2f82f751cea2402c1e3e775f702",
        "collection_id": None,
        "every_days": 30,
        "only_if_changed": True,
        "optional": True,
    },
    {
        # Not in the brief. Kerb lines of major roads for the offline map.
        "key": "road_lines",
        "title": "Master Plan 2019 Road Graphic layer",
        "agency": "Urban Redevelopment Authority",
        "kind": "file",
        "dataset_id": "d_95a29fbb10cf94a3c263d33861d7b6c6",
        "collection_id": None,
        "every_days": 30,
        "only_if_changed": True,
        "optional": True,
    },
    {
        "key": "rainfall",
        "title": "Rainfall across Singapore",
        "agency": "National Environment Agency",
        "kind": "realtime",
        "path": "/rainfall",
        "dataset_id": "d_6580738cdd7db79374ed3152159fbd69",
        "collection_id": "1459",
        "daily_history": True,
        "every_days": 1,
    },
    {
        "key": "air_temperature",
        "title": "Air Temperature across Singapore",
        "agency": "National Environment Agency",
        "kind": "realtime",
        "path": "/air-temperature",
        "dataset_id": "d_66b77726bbae1b33f218db60ff5861f0",
        "collection_id": "1459",
        "every_days": 1,
        "optional": True,
    },
    {
        "key": "relative_humidity",
        "title": "Relative Humidity across Singapore",
        "agency": "National Environment Agency",
        "kind": "realtime",
        "path": "/relative-humidity",
        "dataset_id": "d_2d3b0c4da128a9a59efca806441e1429",
        "collection_id": "1459",
        "every_days": 1,
        "optional": True,
    },
    {
        "key": "flood_alerts",
        "title": "Flood Alerts across Singapore",
        "agency": "PUB, Singapore's national water agency",
        "kind": "realtime",
        "path": "/weather/flood-alerts",
        "dataset_id": "d_f1404e08587ce555b9ea3f565e2eb9a3",
        "collection_id": None,
        "every_days": 1,
        "optional": True,
    },
]

# ---------------------------------------------------------------------------
# Sources that were only downloaded to check them in Phase 1 (data/REPORT.md).
# The daily refresh never touches these. Fetch one by hand with
#   python scripts/fetch_sources.py --only <key>
# ---------------------------------------------------------------------------
PHASE1_ONLY = [
    {
        "key": "landscaped_rooftops",
        "title": "Master Plan 2025 SDCP Landscaped Rooftop layer",
        "agency": "Urban Redevelopment Authority",
        "kind": "file",
        "dataset_id": "d_acea213d30ae77866e42365777bc0291",
        "collection_id": None,
    },
    {
        "key": "abc_waters_completed",
        "title": "ABC Waters Completed",
        "agency": "PUB, Singapore's national water agency",
        "kind": "file",
        "dataset_id": "d_b5f239cc954bb7920245a7b8ad95dde8",
        "collection_id": "2014",
    },
    {
        "key": "historical_rainfall_2016",
        "title": "Historical Rainfall across Singapore (2016)",
        "agency": "National Environment Agency",
        "kind": "file",
        "dataset_id": "d_79a6f0fb898996d415b207bb26ed0fa6",
        "collection_id": "2279",
    },
    {
        "key": "aedes_breeding_habitats_central",
        "title": "Aedes Mosquito Breeding Habitats - Central (GEOJSON)",
        "agency": "National Environment Agency",
        "kind": "file",
        "dataset_id": "d_68d66612ee0b79bb49bf63730134aa68",
        "collection_id": "1425",
    },
]

ALL_SOURCES = SOURCES + PHASE1_ONLY
BY_KEY = {s["key"]: s for s in ALL_SOURCES}
