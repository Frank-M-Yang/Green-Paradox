# Canopy Care

A management system for the green and water-holding assets of one neighbourhood. It keeps a register of assets, works out once a day which ones most need an inspection for standing water, and records what inspectors find.

The idea behind it: greenery by itself does not cause more mosquitoes. Unmanaged water-holding assets do, and managed green infrastructure can be safe. This is a hackathon demo for Ang Mo Kio west, Singapore, built on open data from data.gov.sg.

It is a static site plus one data script. There is no server, no database and no accounts.

**The score ranks inspections. It does not predict dengue cases.** Every threshold in it is a placeholder awaiting expert review. Read [NOTES.md](NOTES.md) for what is real and what is simulated before showing this to anyone.

## Run it

You need Python 3.11 or newer and a web browser. There is nothing to install.

**1. Refresh the data.** One command, once a day:

```
python scripts/refresh.py
```

It fetches what is new, computes the priorities, writes `site/data/snapshot.js` and `site/task-sheet.html`, and stops. With the cache that ships in `data/raw/` this takes about half a minute. If a source is down, the newest cached copy is used and the site shows that source's older date.

**2. Open the site.** Double-click `site/index.html`. It works straight from the folder.

### Other ways to run the refresh

| Command | What it does |
|---|---|
| `python scripts/refresh.py --offline` | Rebuilds from `data/raw/` without touching the network. |
| `python scripts/refresh.py --as-of 2026-11-21 --offline` | Rebuilds the snapshot for one past day exactly. **Use this before the demo**: [DEMO.md](DEMO.md) is written for 21 Nov 2026. |
| `python scripts/refresh.py --force` | Downloads every source again. From an empty cache this takes about 35 minutes (estimated, see NOTES.md), because the public rate limit allows one rainfall request every two seconds and the day-by-day replay needs 84 days of rain. |

On macOS or Linux the command may be `python3`.

### Using it on a phone, and the QR codes

A phone cannot open a file on your laptop, so the site has to be reachable at a web address. Either works:

- **Host it.** Copy the `site` folder to any static host. Nothing needs configuring.
- **Serve it from the laptop.** From the project folder run the command below, connect the phone to the same Wi-Fi or to the laptop's hotspot, and open `http://<laptop address>:8000/site/`.

```
python -m http.server 8000 --bind 0.0.0.0
```

The first time, Windows may ask whether to let Python through the firewall. Allow it on private networks, or the phone will not connect.

Then open `qr-sheet.html` **from that same address** and print it. The codes carry whatever address the page was opened from, so they are right automatically. Click one label to get a single large one for the demo object.

Inspection records stay in the browser of the device that made them. Phones and laptops do not share them. See [NOTES.md](NOTES.md).

### Letting other people open it

Other people can open the site only at a public web address. The address of your own laptop works for devices on the same network and for nobody else.

**The site is public at <https://frank-m-yang.github.io/Green-Paradox/>.** It is served by GitHub Pages from the `main` branch of <https://github.com/Frank-M-Yang/Green-Paradox>. That address forwards to `site/`, where the site itself lives.

- **To share it:** open that address, go to the Dashboard and press **QR code that opens this site**. Show the code on a screen, or send the address. A phone scans the code. A computer opens the address.
- **The QR labels for the assets** follow the same address: open `site/qr-sheet.html` there and print.
- **To update what the public sees:** refresh the data or change the files, then commit and push. The public site follows about a minute later.

  ```
  git add -A
  git commit -m "Refresh the snapshot"
  git push
  ```

- **Visitors cannot change anything for anyone else.** Each visitor's inspection records stay in their own browser.
- **Organisation names of community gardens are hidden** in the public build (see "Changing things" below).
- To host it somewhere else instead, copy the contents of the `site` folder to any static host. Nothing needs configuring.

### Running it every day

Any scheduler will do. The publishers update at about 10:06 Singapore time, so run after 10:15.

- Windows Task Scheduler: a daily task that runs `python` with the argument `scripts\refresh.py`, starting in the project folder.
- cron, on a machine whose clock is on Singapore time: `20 10 * * * cd /path/to/project && python3 scripts/refresh.py`

## What is in the folder

| Path | What it is |
|---|---|
| `site/` | The whole site. `index.html`, `app.js`, `style.css`, `qr.js`, the generated `data/snapshot.js`, and two printable pages: `task-sheet.html` and `qr-sheet.html`. The snapshot is one file: JSON wrapped as a script so that the page can load it from a folder. |
| `scripts/refresh.py` | The one command. Fetches, then builds. |
| `scripts/fetch_sources.py`, `sources.py` | Downloading, rate limits, the list of datasets and their IDs. |
| `scripts/build_snapshot.py` | Assembles assets, scores, scenarios and map into the snapshot. |
| `scripts/risk.py` | The score. Four parts, added up. |
| `scripts/task_sheet.py` | The printable daily sheet and its route. |
| `scripts/rainfall.py`, `mapdata.py`, `geo.py`, `xlsx_reader.py` | Helpers: daily rain totals, map shapes, distances and coordinates, reading the PUB spreadsheet. |
| `config/risk_config.toml` | **Every threshold and weight in the score, with comments.** Also the assumptions per asset type. |
| `config/demo_config.toml` | The neighbourhood, the scenarios, how many tasks go on the printed sheet. |
| `data/raw/` | Dated copies of every source, exactly as downloaded, plus `manifest.json`. |
| `data/demo/` | The simulated assets and the simulated inspection history for the walkthrough. |
| `data/REPORT.md` | Phase 1: what each dataset really contains. |
| `tests/` | `test_risk.py` checks the score. `test_replay.py` checks the day-by-day replay. `qr_selftest.html` checks the QR generator. |
| `screenshots/` | The map before and after the visual redesign of 21 Nov 2026, at laptop and phone widths. |
| `scripts/inspect_sources.py`, `phase1_*.py` | Phase 1 tools that produced the report. Not needed to run the demo. |

## The five screens

1. **Map.** A marker grows and darkens with its priority, on one colour scale. Circles are real places and diamonds are simulated. A key on the map explains every mark, and a small outline of Singapore shows where the neighbourhood is. Dengue clusters and high-Aedes areas can be switched off. Tap an asset to see the four parts of its score. Tap a cluster to see what NEA found there. Drawn from the open data itself, with no map tiles.

   Under the map is a strip with the rain of each day in the window. Drag the day marker or press Play, and the markers change to the scores as they stood after that day's rain. Those scores are worked out in advance by the data script; the browser only looks them up. A link ending `#/map/<asset id>/<day 1 to 14>` opens the map on a given day.
2. **Tasks.** Every asset, ranked, each with its reasons. After an inspection is saved, the asset's row shows how far it moved.
3. **Checklist.** Reached from a task or by scanning an asset's QR code. Four questions. Saving it lowers the asset's score at once, and on the map its marker shrinks and pales to match.
4. **Dashboard.** Share inspected on time, overdue items, repeat problem sites, export and import of records, every data source with its date.
5. **Scenarios.** Replays real rainfall from other periods so the list visibly reorders. Keys 1 to 4 switch scenario on any screen.

## The data model

Three plain things, so that it can be moved into another system later.

| Thing | Fields | Where it lives |
|---|---|---|
| **Asset** | `id`, `name`, `type`, `lon`, `lat`, `simulated`, `source`, `holds_water`, `drain_time_h`, `water_source`, `flushable`, `last_inspection`, `inspections` | `assets` in `site/data/snapshot.js` |
| **Inspection task** | an asset plus its score for today, the four parts of that score and its rank | worked out when needed, never stored |
| **Inspection record** | `id`, `asset_id`, `recorded_at`, `standing_water`, `larvae`, `actions`, `note` | the browser's local storage on the device that made it, and the exported text |

The snapshot file is JSON with `window.CANOPY_SNAPSHOT=` in front and `;` behind. Strip those and any JSON reader will take it.

## Changing things

- **Thresholds and weights:** `config/risk_config.toml`. Run the refresh afterwards. The site reads the values from the snapshot, so there is no second place to edit.
- **A different neighbourhood:** change `subzones` in `config/demo_config.toml` to other URA subzone names, replace `data/demo/simulated_assets.json`, and run the refresh.
- **Show the organisation names of community gardens:** set `show_garden_names = true` in `config/demo_config.toml`. They are hidden by default because the site is public and the inspection dates beside them are made up.

## Checks

- The Dashboard ends with a self-check: the browser recomputes every score and compares it with the data script's.
- `python -m unittest discover tests` runs 36 checks: a dry spell scores nothing, light rain builds up, a heavy storm flushes a drain but fills a container, showers that arrive before an asset has drained count as one unbroken spell, and the day-by-day replay ends on the score itself.
- `tests/qr_selftest.html` checks the QR generator against values published in the QR specification and reads every code back. Open it from the project folder.

## Data and licence

Contains information from data.gov.sg accessed under the [Singapore Open Data Licence](https://data.gov.sg/open-data-licence), from the National Environment Agency, the National Parks Board, PUB and the Urban Redevelopment Authority. Each dataset, its ID and its date are listed on the Dashboard and in `data/REPORT.md`.
