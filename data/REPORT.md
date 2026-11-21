# Phase 1 data report

Checked on **2026-11-21 (Singapore time)** against the live data.gov.sg API. All sources are published under the Singapore Open Data Licence. Snapshots are in `data/raw/`, and `data/raw/manifest.json` records every file with its size, SHA-256, fetch time and request URL.

Nothing in this phase is simulated or invented. Where a source failed or disappointed, it says so below.

## 1. Verdict

| Purpose | Dataset | Verdict | In one line |
|---|---|---|---|
| Active dengue clusters | Dengue Clusters (GEOJSON), NEA | **Usable** | 12 clusters, updated today, plain fields. Current clusters only, no history. |
| High-Aedes areas | Areas with High Aedes Population (GEOJSON), NEA | **Usable**, label with care | 113 areas, file updated 2026-11-05. The portal description still says "April to June 2019". |
| Rainfall | Rainfall across Singapore, NEA real-time API | **Usable** | 87 stations, 5-minute totals, any day back to 2016-12-02, no key needed. |
| Rainfall archive | Historical Rainfall (collection 2279), NEA | **Not practical** | Nine yearly CSVs, eight of them around 1 GB each, ending 2024-12-31. The real-time API serves the same readings by date. |
| Temperature, humidity | Air Temperature and Relative Humidity, NEA real-time API | **Usable** | 17 stations only. |
| Drain sensor locations | PUB Water Level Sensors, PUB | **Usable after two fixes** | The ID in the brief is dead. The live file is a spreadsheet in SVY21 coordinates, not GeoJSON. |
| Flood alerts | Flood Alerts across Singapore, PUB real-time API | **Reachable but empty** | No alert in any sample, including during three of the month's heaviest storms. |
| Rooftop and vertical greenery | NParks Skyrise Greenery | **Not available** | Unpublished from data.gov.sg. Needs a decision: see section 5. |
| Parks | Parks, NParks | **Usable** | 462 points, updated today. |
| Park facilities | Park Facilities, NParks | **Usable**, thinner than it looks | 14,754 points, but 81% are car parks and notice boards, and no class describes water. |

## 2. Access patterns that worked

| What | URL | Result |
|---|---|---|
| Collection metadata | `https://api-production.data.gov.sg/v2/public/api/collections/{collection_id}/metadata` | 200 |
| Dataset metadata | `https://api-production.data.gov.sg/v2/public/api/datasets/{dataset_id}/metadata` | 200 |
| Dataset file | `https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download` | 201, returns a one-hour signed link to `https://s3.ap-southeast-1.amazonaws.com/blobs.data.gov.sg/{dataset_id}.{ext}` |
| Latest reading | `https://api-open.data.gov.sg/v2/real-time/api/rainfall` (also `/air-temperature`, `/relative-humidity`, `/weather/flood-alerts`) | 200 |
| One past day | `https://api-open.data.gov.sg/v2/real-time/api/rainfall?date=YYYY-MM-DD`, then `&paginationToken=...` until no token is returned | 200, 25 readings per page, 12 pages per day |

Both patterns in the brief are correct. The developer guide confirms that non-CSV files skip `initiate-download`.

**No API key is needed.** Without one, the developer guide gives these limits: real-time API 6 calls per 10 seconds, dataset downloads 2 per 10 seconds (another page of the same guide says 5 per minute). I hit HTTP 429 on five file downloads: one straight after a burst of manual test calls, and four while a rainfall download was running in parallel. All five succeeded when retried alone. My reading is that the limits are counted per IP address and shared between the two kinds of call, so the data script makes one request at a time and leaves 13 seconds between file downloads. `DATA_GOV_SG_API_KEY` is honoured if set, but is optional.

To reproduce everything in this report:

```
python scripts/fetch_sources.py          # about 15 minutes, mostly waiting on rate limits
python -I scripts/inspect_sources.py     # prints the facts quoted below
python -I scripts/phase1_neighbourhoods.py
```

## 3. Where the brief and the data disagree

| The brief said | What the data says |
|---|---|
| PUB sensors are `d_ea075550f96f7bcc1c87f8cdc2527156` | That ID returns `404 DATASET_DOES_NOT_EXIST`. The live dataset in collection 1541 is `d_31333fa5cf0834f012d840365b336610`, format XLSX. |
| NParks Skyrise Greenery is collection 1487 | The collection record exists (last updated 2024-06-06) but holds no live dataset. Its former child `d_45869177b47cfa0929f3f75b672f09eb` returns 404, and the collection page on data.gov.sg reads "Dataset not found ... this dataset has been unpublished". A crawl of all 4,677 active datasets found none with "skyrise" or "greenery" in its name. |
| Rainfall is "collections 1459 and 2279" | 1459 is the real-time collection and the rainfall ID is right. 2279 is a separate archive of yearly CSVs. |
| Temperature and humidity are "collection 1459" | Correct. The datasets are `d_66b77726bbae1b33f218db60ff5861f0` (air temperature) and `d_2d3b0c4da128a9a59efca806441e1429` (relative humidity). |
| Dengue clusters carry "breeding habitat types found" | True, as three free-text fields, but they are filled for only 1 of today's 12 clusters. |
| Attributes may be packed into an HTML description | Not in any dataset the demo will use. All have plain typed fields. One stale dataset I tested and rejected does have this problem (section 6). |
| Some datasets looked stale, last updated mid-2024 | 2024-06-06 is a bulk timestamp, not a content date: 797 of 4,677 datasets and 708 of 1,370 collections carry it. Of the brief's sources only the dead Skyrise collection does. Every dataset from the brief that still exists is current. The one older file is the community gardens list I propose to add, dated 2024-11-21. |
| The real-time rainfall API has had outages | No outage today: every one of the 364 pages needed for the cached period came back. Two days in the last 30 are short a few readings (section 4.3). |

One API quirk probably explains how the dead IDs reached a web search: the collection *listing* endpoint (`/collections?page=N`) still shows child datasets that no longer exist, while the per-collection metadata endpoint shows only live ones.

## 4. The datasets in the brief

No GeoJSON file here has a `crs` member, so the GeoJSON default applies: longitude and latitude in WGS84. I confirmed it from the value ranges (longitude 103.6 to 104.1, latitude 1.16 to 1.47). No file has Z values.

`FMEL_UPD_D` is the date an individual record was last edited, as `YYYYMMDDhhmmss`. `INC_CRC` is a checksum. Neither is useful on screen.

### 4.1 Dengue Clusters (GEOJSON), NEA

- **Downloaded:** yes. `https://api-open.data.gov.sg/v1/public/api/datasets/d_dbfabf16158d1b0e1c420627c0819168/poll-download` → `data/raw/dengue_clusters/2026-11-21.geojson` (21,180 bytes)
- **Source last updated:** 2026-11-21 10:06 SGT. Refreshed daily.
- **Dates actually covered:** the clusters active on the day of publication. Records were last edited between 2026-11-16 and 2026-11-18. There is no history in the file.
- **Records:** 12 clusters, 63 cases in total, from 2 to 29 cases per cluster.
- **Geometry:** 10 Polygon, 2 MultiPolygon. WGS84.
- **Fields:** `OBJECTID`, `LOCALITY` (road names, sometimes block numbers), `CASE_SIZE` (number), `NAME` (always "Dengue_Cluster"), `HYPERLINK`, `HOMES`, `PUBLIC_PLACES`, `CONSTRUCTION_SITES` (free text: breeding habitats found, by type of premises), `INC_CRC`, `FMEL_UPD_D`, `SHAPE.AREA` (m²), `SHAPE.LEN` (m)
- **Example:**
  ```json
  {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": "[103.83295, 1.38407, ...]"},
   "properties": {"OBJECTID": 532802,
    "LOCALITY": "Lentor Gdns / Munshi Abdullah Ave / Tagore Ave / Tung Po Ave / Yio Chu Kang Dr",
    "CASE_SIZE": 29, "NAME": "Dengue_Cluster",
    "HYPERLINK": "https://www.nea.gov.sg/dengue-zika/dengue/dengue-clusters",
    "HOMES": "Domestic Container, Flowerpot, Pail, Ceramic Tray, Plastic Sheet, Cabinet Top Surface, Badminton set bag, Dish Tray Rack, Overturned basin rim, Ornamental container, Earthen jar ",
    "PUBLIC_PLACES": "Flowerpot, Safety barner, Plant structure, Water valve chamber, Canvas sheet, Closed drain, Water puddle, Keyhole",
    "CONSTRUCTION_SITES": "Closed Perimeter Drain, Water Puddle, Pot hole, Bamboo pole holder, Toilet bowl, Sink Water trap, Gully trap, Discarded item, Discarded container, Metal pole, Open drain",
    "INC_CRC": "CFF4E86D9C605CFB", "FMEL_UPD_D": "20261118153447",
    "SHAPE.AREA": 171277.468931465, "SHAPE.LEN": 2246.69091528947}}
  ```
- **Surprises:**
  - It is a picture of today only. A cluster that closes disappears from the file, so "recent clusters" exist only if we keep our own daily snapshots. Today's snapshot is cached and should stay the demo snapshot.
  - The habitat fields are filled for one cluster, the largest. They cannot drive a score. They are still the best evidence for the thesis in any dataset here: NEA's own list for that cluster names flowerpots, plant structures and drains.
  - `LOCALITY` sometimes names housing blocks ("Blk 602, 604"). That is the source's own precision, so showing it is within the brief's rule, and the demo should show nothing finer.
  - The metadata field `coverageStart` reads 2025-11-07, which does not describe the content.

### 4.2 Areas with High Aedes Population (GEOJSON), NEA

- **Downloaded:** yes. `https://api-open.data.gov.sg/v1/public/api/datasets/d_5d060d8b7838a15e8906fb22c50dbf51/poll-download` → `data/raw/high_aedes_areas/2026-11-21.geojson` (358,397 bytes)
- **Source last updated:** 2026-11-05 10:06 SGT.
- **Dates actually covered:** records last edited 2026-08-27 (45 areas), 2026-09-29 (15) and 2026-11-03 (53). The file states no observation period.
- **Records:** 113 areas, from 1.5 to 35 hectares, median 9 hectares.
- **Geometry:** 112 Polygon, 1 MultiPolygon. WGS84.
- **Fields:** `OBJECTID`, `DESCRIPTION` (an area code and road names), `NAME` (the same slogan on every record), `HYPERLINK`, `INC_CRC`, `FMEL_UPD_D`, `SHAPE.AREA`, `SHAPE.LEN`
- **Example:**
  ```json
  {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": "[103.83356, 1.30894, ...]"},
   "properties": {"OBJECTID": 68187,
    "DESCRIPTION": "CO53 - Balmoral Cres / Balmoral Rd / Bt Timah Rd / Goodwood Hill / Sarkies Rd / Scotts Rd / Stevens Rd",
    "NAME": "High Aedes Mosquitoes Population Area. Let's fight Dengue together. Do the Mozzie Wipe-out today",
    "HYPERLINK": "https://www.nea.gov.sg/dengue-zika/Aedes",
    "INC_CRC": "22CBBA4FB4D194B6", "FMEL_UPD_D": "20261103003818",
    "SHAPE.AREA": 351305.21268355, "SHAPE.LEN": 2793.14654540257}}
  ```
- **Surprises:**
  - This is the case the brief predicted. The portal description says the areas are "from April to June 2019", while the records were edited between August and November 2026. The description is stale, not the data. On screen the layer should carry the file's update date and say that the source does not state which trapping period it reflects.
  - Area codes start with `CO` (63 areas) or `FL` (50). The dataset does not explain them, so the demo should not interpret them.
  - No trap counts or thresholds. An asset is inside one of these areas or it is not.

### 4.3 Rainfall across Singapore, NEA real-time API

- **Downloaded:** yes.
  - Latest reading: `https://api-open.data.gov.sg/v2/real-time/api/rainfall` → `data/raw/rainfall/2026-11-21_latest.json`
  - One day: `https://api-open.data.gov.sg/v2/real-time/api/rainfall?date=2026-11-20` plus 11 `paginationToken` pages → `data/raw/rainfall/day_2026-11-20.json.gz`. Pages are merged into one file per day with nothing dropped.
- **Source last updated:** real time. Latest reading 2026-11-21 10:10 SGT. (The dataset record itself says 2025-12-16, which plainly does not refer to the readings.)
- **Dates actually covered:** the API answers for any date from 2016-12-02; 2016-12-01 returns `404 Data not found`. Cached here: 30 full calendar days, 2026-10-22 to 2026-11-20, and part of 2026-11-21. That is 8,734 readings in 31 files, 316 KB gzipped.
- **Records:** 87 stations in the latest reading, 90 distinct over the 30 days. A complete day has 288 readings per station.
- **Geometry:** each station is a point given as `location.latitude` and `location.longitude`, WGS84.
- **Fields:** `stations[]` (`id`, `deviceId`, `name`, `location`), `readings[]` (`timestamp`, `data[]` of `stationId` and `value`), `readingType` ("TB1 Rainfall 5 Minute Total F"), `readingUnit` ("mm"), `paginationToken`
- **Example:**
  ```json
  {"stations": [{"id": "S216", "deviceId": "S216", "name": "Ang Mo Kio Avenue 10",
                 "location": {"latitude": 1.36019, "longitude": 103.85335}}],
   "readings": [{"timestamp": "2026-11-16T17:00:00+08:00",
                 "data": [{"stationId": "S08", "value": 0.2}, {"stationId": "S109", "value": 0.2}]}],
   "readingType": "TB1 Rainfall 5 Minute Total F", "readingUnit": "mm"}
  ```
- **Surprises:**
  - Past days are paginated at 25 readings, so one day costs 12 requests and 30 days cost 360. At the rate limit that is about 12 minutes on the first run. After that, only yesterday is new each day.
  - Two days are short: 2026-10-30 has 266 of 288 time steps and 2026-11-02 has 280. Individual stations miss a few more (S109 is absent from 49 of the 8,734 time steps). The score must treat a missing reading as unknown, not as zero rain.
  - The station network changes: 55 stations in December 2016, 56 on the page I sampled for 2025-06-15, 87 today. "Nearest station" has to be worked out from the stations that report in the cached period.
  - The last 30 days were wet. At S109 it rained on 16 of 30 days and the longest dry run was 2 days. The cached period therefore contains real heavy-rain and light-rain days but **no real dry spell** (section 8).

### 4.4 Historical Rainfall across Singapore, NEA, collection 2279

- **Downloaded:** only the smallest file, to learn the layout. `https://api-open.data.gov.sg/v1/public/api/datasets/d_79a6f0fb898996d415b207bb26ed0fa6/poll-download` → `data/raw/historical_rainfall_2016/2026-11-21.csv` (930,062 bytes)
- **Source last updated:** 2025-05-06.
- **Dates actually covered:** the collection runs from 2016-12-02 to 2024-12-31. The 2016 file holds 2016-12-02 21:49 to 2016-12-03 06:14.
- **Records:** 5,543 rows for 55 stations in the 2016 file. No geometry: longitude and latitude are columns.
- **Fields:** `date`, `timestamp`, `update_timestamp`, `station_id`, `station_name`, `station_device_id`, `location_longitude`, `location_latitude`, `reading_update_timestamp`, `reading_value`, `reading_type`, `reading_unit`
- **Example:** `2016-12-02,2016-12-02T21:49:59+08:00,2016-12-09T22:01:28+08:00,S109,Ang Mo Kio Avenue 5,S109,103.8492,1.3764,2016-12-09T22:01:28+08:00,0.0,TB1 Rainfall 5 Minute Total F,mm`
- **Surprises:** the yearly files for 2017 to 2024 are between 0.88 and 1.34 GB each (sizes from the metadata; I did not download them) and the archive stops at the end of 2024. **Not used.** The real-time API returns the same readings for any chosen date in a few small requests.

### 4.5 Air Temperature and Relative Humidity, NEA real-time API

- **Downloaded:** yes. `https://api-open.data.gov.sg/v2/real-time/api/air-temperature` and `.../relative-humidity` → `data/raw/air_temperature/2026-11-21_latest.json`, `data/raw/relative_humidity/2026-11-21_latest.json`
- **Source last updated:** real time. Latest reading 2026-11-21 10:13 SGT.
- **Dates actually covered:** metadata says from 2016. I checked one past moment (`?date=2026-11-20T14:00:00` returned 31.9 °C at S109).
- **Records:** 17 stations, one value each per minute.
- **Geometry:** station points, WGS84.
- **Fields:** the same shape as rainfall. `readingType` is "DBT 1M F" in "deg C" for temperature and "RH 1M F" in "percentage" for humidity.
- **Example:** `{"timestamp": "2026-11-21T10:13:00+08:00", "data": [{"stationId": "S109", "value": 28.6}]}` and, for humidity, `{"stationId": "S109", "value": 86}`
- **Surprises:**
  - Only 17 stations against 87 for rainfall, so the nearest one can be several kilometres away.
  - A whole past day is 1,440 one-minute readings at 25 per page, which is 58 requests. A date-and-time query returns a single reading, so a daily figure is better built from a few samples.
  - Singapore is warm every day of the year, so temperature will not move the score. I propose showing it only as context for the "life cycle of roughly a week" assumption.

### 4.6 PUB Water Level Sensors, PUB

- **Downloaded:** yes, with the corrected ID. `https://api-open.data.gov.sg/v1/public/api/datasets/d_31333fa5cf0834f012d840365b336610/poll-download` → `data/raw/pub_water_level_sensors/2026-11-21.xlsx` (37,846 bytes)
- **Source last updated:** 2026-04-13. The collection is refreshed half-yearly.
- **Dates actually covered:** not stated. There are no dates in the file.
- **Records:** 328 sensor sites, on one worksheet.
- **Geometry:** none. Columns `X` and `Y` are SVY21 easting and northing in metres (EPSG:3414), not longitude and latitude.
- **Fields:** `Station ID`, `Station Name`, `X`, `Y`
- **Example:** `{"Station ID": "CWS186", "Station Name": "Eng Neo Ave OD (Vanda Lk u/s culvert)", "X": "24084.322517376098", "Y": "34974.364755337803"}`
- **Surprises:**
  - The format is a spreadsheet although the metadata describes GeoJSON-style properties. The script reads it with the standard library.
  - Coordinates need converting. `scripts/geo.py` does this, and I checked it against the Parks dataset, which carries both systems: across 462 points the largest error is under 1 mm.
  - These are locations only. There are no water levels, and I found no open API for the readings.
  - ID prefixes are `WWS` (128), `CWS` (114) and `EWS` (86). They look like west, central and east, but the file does not say so.

### 4.7 Flood Alerts across Singapore, PUB real-time API

- **Downloaded:** yes. `https://api-open.data.gov.sg/v2/real-time/api/weather/flood-alerts` → `data/raw/flood_alerts/2026-11-21_latest.json` (3,928 bytes)
- **Source last updated:** real time, one record about every 2 minutes. The dataset was created on 2025-09-03 and belongs to no collection.
- **Dates actually covered:** the latest file holds 25 records from 09:24 to 10:12 SGT today. The `date` parameter reaches earlier days.
- **Records:** 25 per page. **None contains an alert.**
- **Geometry:** per the published specification, each alert has an `area.circle` (latitude, longitude, radius in km). I could not observe one.
- **Fields seen:** `records[]` with `datetime`, `updatedTimestamp` and `item` (`type` "observation", `isStationData`, `readings[]`). Per the specification, an alert in `readings[]` has `area`, `headline`, `description`, `instruction`, `severity`, `urgency`, `certainty`, `event` ("Flood"), `msgType` and `senderName` ("PUB").
- **Example:** `{"datetime": "2026-11-21T10:12:40+08:00", "item": {"type": "observation", "readings": [], "isStationData": false}, "updatedTimestamp": "2026-11-21T10:16:04+08:00"}`
- **Surprises:** for three of the heaviest storms in the cached month I queried the 50 minutes up to the end of the peak hour (82 mm in an hour at Woodlands on 2026-11-06, 72 mm at Mandai on 2026-11-16, 69 mm at MacRitchie on 2026-11-02). All three were empty. The dataset description says flood warning notices are excluded, so alerts appear to be rare. **I have not seen a real alert record, and the demo should not depend on one.**

### 4.8 NParks Skyrise Greenery: not available

- **Downloaded:** no. `https://api-production.data.gov.sg/v2/public/api/collections/1487/metadata` returns the collection with `"childDatasets": []`. The former child `d_45869177b47cfa0929f3f75b672f09eb` returns `404 DATASET_DOES_NOT_EXIST` on both the metadata and download endpoints.
- **Source last updated:** the collection record says 2024-06-06, which is the bulk timestamp, not a content date.
- **Elsewhere:** OneMap has a theme service that may still carry this layer, but `https://www.onemap.gov.sg/api/public/themesvc/retrieveTheme?queryName=skyrisegreenery` returns `401 Unauthorized` without an account token. I did not create an account, so that route is unverified.
- **Fallback:** see section 5.

### 4.9 Parks, NParks

- **Downloaded:** yes. `https://api-open.data.gov.sg/v1/public/api/datasets/d_0542d48f0991541706b58059381a6eca/poll-download` → `data/raw/parks/2026-11-21.geojson` (168,423 bytes)
- **Source last updated:** 2026-11-21 10:06 SGT. Republished daily.
- **Dates actually covered:** records last edited between 2026-01-15 and 2026-09-03 (410 of them on 2026-04-22).
- **Records:** 462 parks.
- **Geometry:** Point, WGS84. `X` and `Y` repeat the position in SVY21.
- **Fields:** `OBJECTID`, `NAME`, `X`, `Y`, `INC_CRC`, `FMEL_UPD_D`
- **Example:** `{"type": "Feature", "geometry": {"type": "Point", "coordinates": [103.7842062105903, 1.3137632887404946]}, "properties": {"OBJECTID": 120001, "NAME": "GROVE LANE PG", "X": 22534.26299996, "Y": 32894.84093008, "INC_CRC": "F924179FF6F83455", "FMEL_UPD_D": "20260422000138"}}`
- **Surprises:** a name and a point, nothing else. No size, no type, nothing about water. "PG" in a name means playground. The same 462 parks exist as outlines in a separate dataset (section 6), which the map needs.

### 4.10 Park Facilities, NParks

- **Downloaded:** yes. `https://api-open.data.gov.sg/v1/public/api/datasets/d_14d807e20158338fd578c2913953516e/poll-download` → `data/raw/park_facilities/2026-11-21.geojson` (6,091,834 bytes)
- **Source last updated:** 2026-11-21 10:06 SGT. Republished daily.
- **Dates actually covered:** records last edited between 2026-01-15 and 2026-09-09.
- **Records:** 14,754 facilities in 24 classes.
- **Geometry:** Point, WGS84.
- **Fields:** `OBJECTID`, `UNIQUEID`, `NAME` (filled for only 1,582 records), `CLASS`, `ADDITIONAL_INFO` (always empty), `INC_CRC`, `FMEL_UPD_D`
- **Example:** `{"type": "Feature", "geometry": {"type": "Point", "coordinates": [103.79105, 1.3023]}, "properties": {"OBJECTID": 479030, "UNIQUEID": "94b22ecd-958b-ee11-be36-6045bd1d36d9", "NAME": null, "CLASS": "DRINKING FOUNTAIN", "ADDITIONAL_INFO": null, "INC_CRC": "31CB66FDFDD57AB8", "FMEL_UPD_D": "20260115000214"}}`
- **Class counts:** CARPARK 9,285 · NOTICEBOARD 2,619 · ACCESS POINT 601 · MAPBOARD 528 · FITNESS AREA 475 · PLAYGROUND 387 · BBQ PIT 225 · FOOT RELAX 164 · TOILET 132 · DRINKING FOUNTAIN 113 · SHELTER 47 · ALLOTMENT GARDEN 34 · JETTY 25 · BICYCLE PARKING 21 · THERAPEUTIC GARDEN 21 · MULTIPURPOSE COURT 16 · BICYCLE RENTAL SHOP 16 · F&B 15 · CAMPSITE 8 · LOOKOUT POINT 7 · AMPHITHEATRE 7 · DOG-AREA 3 · DROP-OFF/PICK-UP POINT 3 · BABY 2
- **Surprises:**
  - 81% of the file is car parks and notice boards.
  - **There is no pond, planter, water feature or drain class.** Real NParks data gives us locations and a facility type, never whether something holds water or how fast it drains. Those two properties will have to be assumptions set per asset type, and the interface must say so.
  - Which classes count as inspection targets is therefore my judgement. I kept the ones with a roof gutter, trap, tray, basin or containers: ALLOTMENT GARDEN, THERAPEUTIC GARDEN, TOILET, DRINKING FOUNTAIN, SHELTER, BBQ PIT, CAMPSITE and DOG-AREA. That is 583 records island-wide. I left out fitness areas, foot-reflexology paths and courts, and also playground equipment, because every playground sits inside a park that is already counted. The list is one constant in `scripts/phase1_neighbourhoods.py` and is easy to change.

## 5. The missing skyrise greenery data

I tested the closest substitutes on data.gov.sg:

| Candidate | Result |
|---|---|
| URA "Master Plan 2025 SDCP Landscaped Rooftop layer" (`d_acea213d30ae77866e42365777bc0291`) | Downloads, but holds 6 polygons, all around Marina Bay. Not a register of green roofs. **Rejected.** |
| NParks "Community in Bloom (CIB)" community gardens (`d_f91a8b057cfb2bebf2e531ad8061e1c1`) | 1,772 real garden locations island-wide. **Proposed.** |
| PUB "ABC Waters Completed" (`d_b5f239cc954bb7920245a7b8ad95dde8`) | 75 real water-sensitive landscape projects. None falls in the candidate neighbourhoods. Usable elsewhere. |

**Proposal:** use community gardens as the real small-scale green assets in place of skyrise greenery. They are where planters, water storage and pot trays are actually found, so they suit the thesis better than rooftops would. If the story needs a rooftop garden, add one or two as simulated assets, marked simulated like the rest. I will not show any location as real skyrise greenery.

If real skyrise locations matter to you, the options are a OneMap account (free, token needed, unverified) or asking NParks.

## 6. Datasets I added

These were not in the brief. All are on data.gov.sg under the same licence, and all were downloaded and inspected like the others.

| Key in `data/raw/` | Dataset and ID | Why | Facts |
|---|---|---|---|
| `community_gardens` | Community in Bloom (CIB), NParks, `d_f91a8b057cfb2bebf2e531ad8061e1c1` | Stands in for skyrise greenery | 1,772 points, WGS84. Fields `OBJECTID`, `GARDENID`, `GARDEN_NAME`, `LATITUDE`, `LONGITUDE`. **Last updated 2024-11-21**, so it is two years old and a garden may have closed since. Names are organisations (residents' committees, schools, charities), not people. |
| `park_polygons` | NParks Parks and Nature Reserves, `d_77d7ec97be83d44f61b85454f844382f` | Park outlines for an offline map | 462 polygons matching the 462 park points. Fields `L_CODE`, `NAME`, `N_RESERVE`, `SHAPE_1.AREA`. Updated daily. |
| `subzone_boundaries` | Master Plan 2019 Subzone Boundary (No Sea), URA, `d_8594ae9ff96d0c708bc2af633048edfb` | Defines "a neighbourhood" and frames the map | 332 subzones in 55 planning areas. Fields `SUBZONE_N`, `PLN_AREA_N`, `REGION_N`. Updated 2025-12-03. No 2025 subzone layer is published. |
| `waterbodies` | Master Plan 2025 SDCP Waterbody layer, URA, `d_7e2ac2f82f751cea2402c1e3e775f702` | Canals and major drains for the map | 1,020 polygons with no descriptive attributes. Updated 2026-10-23. |
| `abc_waters_completed` | ABC Waters Completed, PUB, `d_b5f239cc954bb7920245a7b8ad95dde8` | Tested as a green-asset source | 75 polygons, field `PROJECT_TITLE`. Not needed for the recommended neighbourhood. |
| `landscaped_rooftops` | see section 5 | Tested and rejected | 6 polygons. |
| `aedes_breeding_habitats_central` | Aedes Mosquito Breeding Habitats - Central, NEA, `d_68d66612ee0b79bb49bf63730134aa68` | Tested as a source of habitat data | **Rejected as stale.** 99 grid squares whose attributes are packed into an HTML table inside `Description`, with 3D coordinates and record dates of February and March 2023. Not used. |

The last three, and `historical_rainfall_2016` from section 4.4, can be deleted from `data/raw/` once you have read this. I kept them so the findings can be checked.

## 7. Neighbourhood recommendation

I scored all 332 URA subzones by counting the real assets inside each and testing them against today's dengue clusters and high-Aedes areas. Six of today's twelve clusters, holding 46 of the 63 cases, sit together on the west side of Ang Mo Kio. The figures below come from:

```
python -I scripts/phase1_neighbourhoods.py --frame "KEBUN BAHRU,YIO CHU KANG WEST,SEMBAWANG HILLS" "TAMAN JURONG"
```

"Real assets" are parks, the park facility classes listed in section 4.10, community gardens and PUB drain sensor sites.

| | **A. Ang Mo Kio west** (recommended) | B. Taman Jurong |
|---|---|---|
| URA subzones | Kebun Bahru, Yio Chu Kang West, Sembawang Hills | Taman Jurong |
| Size | 2.79 km², about 2.1 by 2.2 km | 1.48 km², about 1.1 by 2.4 km |
| NParks parks | 11, including Ang Mo Kio Town Garden West | 4 |
| Park facilities counted | 4: a toilet, a drinking fountain, a BBQ pit, an allotment garden | 0 |
| Community gardens | 17 | 20 |
| PUB drain sensor sites | 2 | 3 |
| **Real assets in total** | **34** | **27** |
| Dengue clusters inside the area | 3, with 11 cases | 1, with 5 cases |
| Dengue clusters on its boundary | 2, with 33 cases, one of them the largest in Singapore (29) | none |
| High-Aedes areas overlapping | 17 | 1 |
| Real assets inside a cluster | 3: two parks and a drain sensor site | 4: all community gardens |
| Real assets within 150 m of a cluster | 8 | 6 |
| Real assets inside a high-Aedes area | 22 | 3 |
| Real assets in neither | 11 | 18 |
| Nearest rainfall station | S08 Lower Peirce Reservoir for 20 assets (0.4 to 1.4 km away), S109 Ang Mo Kio Avenue 5 for 14 (0.9 to 1.5 km) | S180 Taman Jurong Greens for all 27 (0.1 to 1.4 km) |
| Nearest temperature and humidity station | S109, 0.9 to 2.4 km | S121 Old Choa Chu Kang Road, 3.5 to 5.2 km |

Maps drawn from the snapshots alone, with no basemap: `data/phase1_map_ang_mo_kio.svg` and `data/phase1_map_taman_jurong.svg`.

**Why A.** The west side of Ang Mo Kio is where dengue is concentrated today. Three clusters lie wholly inside the area and two more share its boundary, one of them the largest active cluster in Singapore. That 29-case cluster is the only one for which NEA lists the breeding habitats found, and the list names flowerpots, plant structures and drains. Those are unmanaged water-holding items, which is the project's thesis in NEA's own words. Seventeen high-Aedes areas overlap the area. The real assets spread usefully across the location factor: 8 within 150 m of a cluster, 22 in a high-Aedes area and 11 in neither. Two rain gauges are in play, and they recorded different totals in the same storm (79 mm at S08 and 47 mm at S109 on 2026-11-16), so "rain at the nearest station" visibly differs between assets.

**What A costs.**

- The rain gauges are 0.4 to 1.5 km from the assets, and tropical showers are local.
- The largest cluster is beside the area, not in it. It lies in the Tagore subzone and 1% of it falls inside. The map will show it, but no asset will sit inside it.
- The cluster picture is today's and will have changed by demo day. The demo should run from the cached 2026-11-21 snapshot and say so on screen.
- Only four park facilities qualify, so the real assets are mostly parks (11) and community gardens (17).

**Why not B.** Taman Jurong is more compact, its rain gauge sits inside it, and it has more community gardens. But the dengue signal is one 5-case cluster and a single high-Aedes area, and the nearest temperature station is more than 3.5 km away.

**Also considered.** Ang Mo Kio without Sembawang Hills: 22 real assets, of which one is inside a cluster. Lorong Ah Soo in Hougang: 25 real assets and a rain gauge inside the area, but its one 3-case cluster only partly overlaps.

## 8. What this means for Phase 2

Decisions I would take unless told otherwise:

1. **Real assets** are parks, the park facility classes listed in section 4.10, community gardens and PUB drain sensor sites. Each carries its source and that source's date.
2. **"Holds water" and "drain time"** are not in any real dataset. They become assumptions per asset type, kept in the configuration file and labelled as assumptions on screen, for real and simulated assets alike.
3. **Storm drains:** the real PUB sensor sites give real drain locations (two in area A). Their inspection data would still be simulated and marked so. Further drains would be fully simulated.
4. **Rainfall scenarios:** the cached month has heavy-rain and light-rain days at both stations but no dry spell. I propose taking each scenario from a real period in the station's own record (the API reaches back to 2016) and labelling it with its real dates, in place of invented rainfall. The cost is a few dozen extra requests, once.
5. **Flood alerts and temperature** are shown as context at most. Neither enters the score.
6. **Dengue clusters** stay pinned to the 2026-11-21 snapshot for the demo. A refresh adds a new dated snapshot and does not replace it.
7. **Refresh timing:** NEA and NParks republish at about 10:06 SGT, so the daily run belongs after 10:15 SGT.

## 9. Not verified

- A real flood alert record. None occurred in any period I sampled.
- Whether the "High Aedes" areas reflect a stated trapping period. The file does not say.
- Whether each community garden still exists. The file is from November 2024.
- The meaning of the `CO`/`FL` and `WWS`/`CWS`/`EWS` code prefixes.
- OneMap as a source of skyrise greenery. It needs an account.
- Yearly rainfall archives for 2017 to 2024. I read their metadata but did not download them.
- Anything on the ground. The assets are points in a file, and nobody has visited them.

## 10. Addendum from Phase 2

Three more things were fetched while building the demo. Same site, same licence, same checks.

| Dataset and ID | Why | Facts |
|---|---|---|
| Master Plan 2019 Road Graphic layer, URA, `d_95a29fbb10cf94a3c263d33861d7b6c6` | Major roads for the offline map. **Used**, as `road_lines`. | 5,016 line features (4,784 LineString, 232 MultiLineString), WGS84. One useful field, `TYPE`: ABOVEGROUND 4,774, UNDERGROUND 242. These are kerb and divider lines of major roads, not every street. 5.9 MB, updated 2025-12-05. 83 features touch the demo map. |
| Master Plan 2019 Road Name layer, URA, `d_93f8f9b3a463fc491b25d9a49f1dc654` | Street names for the map. **Tested and rejected.** | 12,232 two-point lines, each carrying one *word* of a name in `TEXTSTRING` ("ANG", "MO", "KIO", "AVENUE") with its own angle. Rebuilding whole street names from 460 fragments in the map view risked mislabelling streets, so the map has no street names. The 11.8 MB file was deleted. |
| Rainfall - Monthly Number of Rain Days, Monthly Highest Daily Total, Monthly Total, NEA, `d_134857f63c76d227b6fa045f31ce59c1`, `d_53ffdaa97e48ce934cf92799d381f3b1`, `d_b16d06b83473fdfcc92ed9d37b66ba58` | To find a real dry spell and a real light-rain month for the scenarios. Not stored and not used by the site. | Small CSVs, one value per month for the Changi climate station, 1982 to October 2026. January 2026 had 4 rain days and 9.4 mm in the month; August 2025 had 14 rain days and no day above 18.8 mm. |

The rainfall cache also grew: all of January 2026 and August 2025 were downloaded day by day from the real-time API to choose the scenario periods. The daily refresh only needs 45 of those days (6 to 19 Aug 2025, 18 to 31 Jan 2026, 4 to 20 Nov 2026).

One more surprise from those months: station **S08** is named "Upper Thomson Road" in the 2025 and January 2026 files and "Lower Peirce Reservoir" in November 2026, at the same coordinates. Station **S109** kept its name but its coordinates moved about 330 m. A gauge has to be followed by its ID, not its name.
