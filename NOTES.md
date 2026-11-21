# Notes

What is real, what is not, how heavy the page is, what does not work yet, and what to do next. Written for the snapshot of 21 Nov 2026.

## The one thing to know first

**Shared storage across devices is not implemented.** An inspection saved on a phone stays in that phone's browser. The laptop does not see it, and neither does the daily data script. The Dashboard can copy records out as text and paste them in on another device, and that is all. A shared store is the first thing to add.

## What is real

| What | Source | Date |
|---|---|---|
| Locations of 11 parks | NParks, Parks | 21 Nov 2026 |
| Locations of 4 park facilities: a toilet, a drinking fountain, a BBQ pit, an allotment garden | NParks, Park Facilities | 21 Nov 2026 |
| Locations of 17 community gardens | NParks, Community in Bloom | file dated 21 Nov 2024 |
| Locations of 2 storm drains | PUB, Water Level Sensors (the sensor sites) | file dated 13 Apr 2026 |
| Dengue clusters: outline, locality, case count, breeding habitats found | NEA, Dengue Clusters | 21 Nov 2026 |
| Areas with more Aedes aegypti | NEA, Areas with High Aedes Population | file dated 5 Nov 2026 |
| Rainfall, 5-minute readings at gauges S08 and S109 | NEA real-time API | four periods, listed below |
| Park outlines, subzone boundaries, water bodies, major roads | NParks and URA | see the Dashboard |
| Air temperature and humidity at S109, PUB flood alerts | NEA and PUB real-time APIs | 21 Nov 2026, shown as context only |

The Dashboard lists every dataset with its snapshot date and the date its publisher last updated it. Dataset IDs and what each file really contains are in `data/REPORT.md`.

## What is simulated

- **19 assets:** 6 roadside drains, 4 pot trays, 4 planter boxes, 3 rain barrels and 2 roof gardens, in `data/demo/simulated_assets.json`. Open data has no register of small items like these. Their positions were placed by hand and describe nothing real. They are marked SIMULATED on the map (diamond shape), in every list, on the checklist, on the printed task sheet and on the QR labels.
- **Every past inspection.** Nobody has inspected anything. The histories come from a repeatable generator in `scripts/build_snapshot.py`, with a hand-written storyline for nine assets in `data/demo/story.json`.
- **One rule kept throughout:** a real place only ever gets made-up visit *dates*, each recorded as "no standing water" with no note. Made-up *problems*, meaning standing water or larvae, are attached to simulated assets and to nothing else. So no real garden, school or park is shown as having had a problem.
- **The two storm drains at PUB sensor sites** are real locations with simulated inspection dates. PUB publishes where the sensors are, not what they read.

## What is assumed

- **Whether an asset holds water and how long it takes to drain.** No dataset records this. Each asset type has an assumption in `config/risk_config.toml`, and the site labels it "assumed for this asset type, not measured".
- **Every threshold and weight in the score.** All placeholders, all in that one file, each with a comment. None is validated.
- **Rain at the asset equals rain at the nearest gauge.** The gauges are 0.2 to 1.5 km from the assets.

## What the score is

A sum of four parts, capped at 100:

| Part | Points | From |
|---|---|---|
| Holds water | 0 to 25 | assumed drain time of the asset |
| Last inspection | 0 to 35 | days since the last record, against a mosquito life cycle of about 7 days |
| Rain and standing water | 0 to 25 | a day-by-day estimate from 14 days of rain at the nearest gauge |
| Location | 0 to 15 | inside or within 150 m of a dengue cluster, inside a high-Aedes area |

60 or more is shown as "Inspect first", 40 to 59 as "Inspect this week", lower as "Routine".

Rain is not "more is worse". Light or moderate rain leaves water that keeps standing. A heavy storm (30 mm in an hour or 50 mm in a day) is taken to flush drains, which then score 0 for three days. After rain stops, an asset counts as wet until its drain time has passed. Assets that are watered by hand or hold stored water get a fixed value, because rain does not change them.

**The rain part counts unbroken days of standing water, not days since the last shower.** A drain that empties in 4 days, wet on the 16th and rained on again on the 17th, 18th and 19th, has held water for 5 days on the 21st, because each shower arrived before it could drain. The drain time runs from the last rain. A reviewer read "drains in 4 days" next to "water for 5 days" as a contradiction, so the on-screen explanation now spells this out, and a unit test holds the case. The calculation itself was right and has not changed.

The flushing rule rests on Seidahmed and Eltahir (2016) and Benedum et al. (2018). Neither paper gives a single rainfall cut-off: the first says a threshold still has to be determined, the second predicts flushing from many rainfall measures over several weeks. The cut-offs here are set high on purpose, so that when in doubt a drain stays on the list.

**It is a way to prioritise inspections. It is not an outbreak prediction**, and the interface says so on every screen and on the printed sheet.

## Scenarios

All four replay real rain at the same two gauges. No rainfall is invented.

| Scenario | Period | What it shows |
|---|---|---|
| Real: last 14 days | 7 to 20 Nov 2026 | A flushing storm on 16 Nov, light showers since |
| Light to moderate rain | 6 to 19 Aug 2025 | Showers on 8 of 14 days, none counted as a flush |
| Heavy rain | 4 to 17 Nov 2026 | The 16 Nov storm, two days before |
| Dry spell | 18 to 31 Jan 2026 | One day of 2.8 mm at S08, no day reaching 1 mm at S109 |

A scenario changes the rainfall only. The assets, the inspection dates and the dengue layers stay as they are in the snapshot. A banner says so whenever a replay is active.

## The day-by-day replay on the map

The strip under the map shows the rain of each of the 14 days. Dragging its day marker, or pressing Play, changes the markers to the scores as they stood after that day's rain.

- **The scores are worked out by the data script, not in the browser.** `daily_replay` in `scripts/build_snapshot.py` runs the ordinary calculation once for each day, with that day's own 14-day look-back. The snapshot stores the result and the browser only looks it up. The build stops if a replay does not end on the asset's normal score, and the Dashboard's self-check tests the same thing.
- **What is real in it:** the rain. **What is simulated:** the inspections. On each day the replay knows only the visits made by then, so a marker also dips on the day of a made-up visit. **What is fixed:** the dengue clusters and high-Aedes areas are today's on every day, because NEA publishes no history of them.
- **The strip's bars are the mean of the gauges in use** (S08 and S109 here). A day is marked "flush" if either gauge counted it as a flushing storm. The Scenarios screen has each gauge separately.
- **It needs more rain data than the scores do:** 13 days before each window. For the August 2025 period those days were not cached, so 8 more day files (24 to 31 Jul 2025) were downloaded on 21 Nov 2026: 96 requests, 215 KB. No new dataset is involved. If such days are missing, the replay counts them as unknown and says so in the strip and on the Dashboard.
- **An inspection saved on this device** is left out of earlier days and counted on the last one.
- `#/map/<asset id>/<day 1 to 14>` opens the map on a given day, for example `#/map/dr-ews045/10` for the real drain at Thomson Walk after the storm of 16 Nov.

## Page weight

Everything `index.html` loads, uncompressed: **253 KB**. Before the visual redesign of 21 Nov 2026 it was 183 KB.

| File | Before | After | What it is |
|---|---|---|---|
| `index.html` | 1.3 KB | 1.3 KB | page shell |
| `style.css` | 17.7 KB | 25.6 KB | styles |
| `app.js` | 57.9 KB | 91.3 KB | the app: map, tasks, checklist, dashboard, scenarios |
| `qr.js` | 9.2 KB | 9.2 KB | QR code generator |
| `data/snapshot.js` | 97.1 KB | 125.8 KB | the day's data: assets, scores, rainfall, map shapes, sources |
| **Total** | **183.3 KB** | **253.1 KB** | 187,673 and 259,178 bytes |

- The 70 KB went to: the map rewrite, rainfall strip and inspection feedback (33 KB of script), the new styles (8 KB), 14 days of precomputed scores for 4 scenarios (about 21 KB), the outline of Singapore (1.7 KB) and longer rain explanations (about 6 KB).
- That still includes the map. There are no map tiles, no web fonts, no images and no libraries.
- A web host that compresses text would send about 61 KB (44 KB before).
- After loading, the page makes no network requests at all. Switching screens, scenarios and days happens in the browser.
- The two printable pages are separate and are loaded only when opened: the task sheet (25 KB, no script) and the QR sheet.
- The data script runs once a day and then nothing runs. A normal day's refresh made 18 requests, received 62 KB and took 31 seconds (measured on 21 Nov 2026 with the cache in place, before the replay was added; the replay adds nothing to a normal day, because the earlier days it reads are already cached). A first run from an empty cache made 573 requests, received 26 MB and took 20 minutes when it needed 45 days of rain. **It now needs 84 days, so expect about 35 minutes. That is an estimate from the rate limit: the clean start has not been run again.** Most of the bytes are five large map and facility files that are fetched again only weekly or monthly, and most of the time is the public rate limit on rainfall requests.

## Decisions I made without asking

Small choices, as the brief asked. Any of them can be reversed.

1. **Demo area:** the three URA subzones you confirmed as "Ang Mo Kio west", with 700 m of map around them so the neighbouring clusters stay visible.
2. **Community gardens stand in for skyrise greenery**, whose dataset has been withdrawn. Two simulated roof gardens are included and marked.
3. **Which park facilities count as assets:** toilet, drinking fountain, shelter, BBQ pit, allotment garden, therapeutic garden, campsite, dog run. Car parks, notice boards, fitness areas and playground equipment are left out. This is a judgement, in `FACILITY_TYPES` in `scripts/build_snapshot.py`.
4. **Scenarios replay real periods** instead of invented rain. The dry spell and the light-rain period were found from NEA's monthly statistics and then downloaded day by day.
5. **Only complete days of rain are used.** The snapshot for a day uses rain up to the previous midnight, so the same date always rebuilds to the same result.
6. **Priority is one colour scale in five steps, pale to dark, and the marker grows with the score. No green.** A red, amber and green set failed a colour-blindness check, and green would have suggested "safe", which a low score does not mean. The steps are `#ef99ab`, `#e46981`, `#d32c4d`, `#9c0e32`, `#5c0820`: one hue, lightness falling at every step, checked with a validator and by simulating red-green and blue-yellow colour blindness on a screenshot. The two palest steps carry a fine dark edge so they hold on green and tinted ground. I first tried a neutral grey for "Routine" and dropped it, because you asked for one scale.
7. **Inspection records can be imported as well as exported.** The brief asked for export only. Without import the exported text had nowhere to go.
8. **No names of people anywhere.** The checklist does not ask who inspected, and the note field asks for no names. Staff contact e-mails that data.gov.sg includes in its metadata are stripped before anything is saved.
9. **Community garden names are hidden**, and each garden is shown as "Community garden" with its number in the NParks list. They were shown until the site was published on 21 Nov 2026. The names are of real organisations, among them preschools and a charity, and on a public page they would stand next to made-up inspection dates. You were asked and did not say either way, so I took the choice that can be undone: `show_garden_names = true` in `config/demo_config.toml` brings the names back. Ranks among assets with equal scores go by name, so this moved a few: Pot tray A is 6th, not 5th.
10. **Road names are not on the map.** The published road-name layer stores every word as a separate fragment, and stitching them back together was not worth the risk of mislabelling a street.
11. **Temperature, humidity and flood alerts are context only.** Singapore is warm all year, so temperature would not move the score, and no flood alert appeared in any period sampled.
12. **A gauge is followed by its ID.** S08 was named "Upper Thomson Road" in 2025 and is "Lower Peirce Reservoir" now, at the same coordinates. The site shows today's name.
13. **Two assets at the same published point are drawn 26 m apart** so both can be tapped. Distances and the score use the published coordinates.
14. **Light theme only.** No dark mode.

Added with the visual redesign of 21 Nov 2026:

15. **Markers that would cover each other are nudged apart on screen**, by at most 22 pixels, and kept off the three subzone names, the cluster badges and the rain gauges. A nudged marker keeps a thin line back to a dot on its true spot, and returns there as you zoom in. Only the drawing moves. A tap picks the nearest marker, so every one can be chosen.
16. **The map opens on the neighbourhood**, not on the whole 700 m margin. Zooming out still shows the margin.
17. **Subzone names sit on the freest ground inside their own outline**, found once per page load. A park name or a neighbouring subzone's name that a marker, the key or the locator would cover is hidden until there is room. All names carry a white halo.
18. **"That day's score" means the full score as the script would have given it that day**, including the simulated inspections made by then. The alternative, holding inspections at today's state and moving only the rain, would have shown scores that never existed. The cost is that a marker also dips on a made-up visit, so DEMO.md tells the presenter which dip is rain.
19. **The outline of Singapore is made from the subzone file already in the cache**, by painting its 332 polygons onto a 150 m grid and tracing the edge. Islets under 1.5 km² are left out. No new dataset.
20. **The palette:** warm paper, leaf green for what you act on, sky blue for rain and links, a sun-yellow banner. Body text is 16.8:1 on the page, muted text 6.2:1, white on the green buttons 6.1:1. The "not a forecast" banner went from 6.9:1 on beige to 15.2:1 on yellow. The SIMULATED badge is unchanged: black on white.
21. **The demo opens a real place first** and the presenter says that inspection dates are simulated. The "Last inspection" part now carries a "simulated history" label wherever it is shown, and the Dashboard has a table of how much of the list's points rest on what: 37% on the simulated history.
22. **Rain gauges are labelled with their ID only.** The key explains the triangle.
23. **A link can open the map on a given day** (`#/map/<asset id>/<day>`). Dragging the day marker does not change the address.
24. **The QR sheet starts with one code for the site itself**, reached from the Dashboard as "QR code that opens this site". It carries whatever address the page was opened from, like the asset labels, and warns when that address is a local one.

## Known limitations

- **No shared storage**, as above. A side effect: the data script cannot see device records, so the printed sheet and the snapshot never reflect them.
- **The score is not validated.** It has not been compared with any field data.
- **Asset properties are guesses by type.** A real register would record drain time per asset.
- **The dengue layer is one day.** NEA publishes current clusters only. Keeping "recent" clusters would mean saving a snapshot every day, which the script does, but only from the day it starts running.
- **The community garden list is two years old.** A garden may have closed or moved.
- **Rain is by calendar day at a gauge up to 1.5 km away.** Tropical showers are local, and rain that fell this morning is not counted until tomorrow's run.
- **The inspection route is straight lines** between points. There is no road network in the data.
- **The map has no street names** and its road layer is from the 2019 Master Plan.
- **Map markers cannot be reached by keyboard.** The Tasks screen lists the same assets as text. The day marker and Play can be: arrow keys move the day.
- **A marker is not always exactly on its spot** when zoomed out (see decision 15). At 1366 by 768, 27 of the 53 are nudged, by at most 13 pixels. At 375 by 812, 36 are, by at most 17.
- **The replay mixes real rain with simulated inspections**, and uses today's clusters for every day.
- **A just-inspected asset can still read 30 to 40.** What the asset is and where it is carry up to 40 points that an inspection does not remove, and an asset watered by hand or holding stored water keeps 10 more. One rain barrel sits at exactly 40, "inspect this week", straight after a clean inspection. That is the placeholder weighting, not a bug, and it is for an expert to change.
- **QR codes need an address the phone can reach.** Opened from a file, they only work on that computer, and the page says so.
- **`data/raw/` grows** by roughly 10 MB a week if the refresh runs daily. Old dated copies can be deleted. Keep 2026-11-21 for the demo.
- **Singapore time throughout.** Dates are Singapore dates whatever the device's clock says.

## What was checked, and what was not

Checked on 21 Nov 2026, after the visual redesign:

- **The scores did not change.** All 212 scores, and each of their four parts, are identical in the snapshots built before and after. So are the map shapes.
- **36 unit tests pass.** Seven are new: two on showers that keep an asset wet without a break, five on the day-by-day replay.
- **The browser's self-check** agrees with the data script on all 212 scores, and now also checks that each replay ends on the score.
- **The map at 1366 by 768 and at 375 by 812.** At both sizes no marker covers another, measured from the drawn positions with a diamond counted as the circle inside it. The phone size does not scroll sideways. All three subzone names are shown. No errors in the console.
- **The rainfall strip.** Play ran through the 14 days in 13 seconds and stopped on today. The real drain at Thomson Walk showed 43, 43, 59, 59, 33, 33, 41, 41, 59, 43, 43, 43, 74, 74, which is what the data script stored. Moving the day marker changed the markers, the counts in the key and the open asset's panel. Keys 1 to 4 still switch scenario while the day marker has the focus.
- **Inspection feedback.** Saving Pot tray A showed "Rank 6 → 38 of 53" (5 → 38 before the garden names were hidden). On the map its marker was drawn at 73, then changed to 38 with the label "73 → 38" beside it. In the task list its row read "Down 32 places" and was scrolled into view.
- **Map gestures, by events sent from a script:** tapping a marker and a cluster badge selects each, dragging pans without selecting anything, the wheel zooms, both layers switch off and on from the key, and the key folds and unfolds.
- **Behaviour that should not have changed, run again:** an empty checklist is refused, HTML typed into a note is shown as text and not run, Undo removes the record, import adds a new record and rejects a malformed one, the QR button draws a code.
- **All five screens open straight from the folder** in headless Microsoft Edge at 1366 wide, and the map also at 500 wide.
- **Colours.** The five-step scale passes the validator's checks for an ordered scale on the map's main ground: one hue, lightness falling at every step, palest step at 2.1:1. On park green and on tinted ground the palest step falls under 2:1, which is why it has a dark edge. On a screenshot with deuteranopia, protanopia and tritanopia simulated, the steps stay in order and stay apart from the clusters.
- **Reduced motion.** With the setting forced on, the page renders the same. The code that skips the glide, the pulse and the smooth scroll was read, not exercised.

Checked earlier the same day, before the redesign, and not repeated since:

- **Clean start.** I moved the whole cache out of the project and ran `python scripts/refresh.py`. It fetched 10 dataset files and 45 days of rainfall in 20 minutes: 573 requests, none failed. Every score, every map layer and all the rainfall it produced were identical to the build from the earlier cache.
- **A normal day.** With the cache in place and only one day's worth removed, the same command took 31 seconds.
- **Offline.** `--as-of 2026-11-21 --offline` rebuilds the demo snapshot with no network.
- **A source that is down.** In a copy of the project I blocked the network and deleted some cached files. The run finished in 37 seconds. It fell back to the previous day's dengue file and flagged that on the Dashboard, counted the rainfall day it could not fetch as unknown, and left out the layers it had no copy of.
- **QR codes.** The generator passes 8 checks against values published in the QR specification. OpenCV, an independent reader that was already installed, decoded 4 generated codes of three different sizes exactly, and read 4 of the 9 codes in a small JPEG screenshot of the QR sheet, each to the right asset address.
- **A phone scan.** One QR label was scanned with a phone camera and that asset's checklist opened. Nothing further was confirmed on the phone: not which phone or browser it was, and not whether saving the checklist there works.
- **Printing.** The task sheet comes out as exactly one A4 page in Edge's print-to-PDF. The QR sheet is six pages. Neither page was restyled.

Not checked:

- **The clean start since the replay was added.** It now downloads 84 days of rain instead of 45. Only the 8 new days were fetched, with no failures.
- **The new map in Firefox or Safari.** The day marker is a restyled slider, and each browser styles sliders its own way. It carries rules for both families, but only Chromium was run.
- **Dragging the day marker with a finger, and the new map on a real phone.** The phone size was checked in a desktop browser's phone view only.
- **The new palette on a projector.** Contrast was measured, not looked at on one.
- **The marker animations by eye.** I could not take a screenshot mid-animation, so I checked the marker's size, colour and label before and after from the page itself.
- **Saving an inspection on a phone.** The scan opened the checklist, and that is as far as the check went. Before the demo, run the whole 2:15 step from [DEMO.md](DEMO.md) once on the phone you will use.
- Safari and Firefox on a laptop. Everything on the laptop was run in Chromium-based browsers (Edge, and the Claude desktop app's browser). The phone's browser was not recorded.
- Printing on paper. The two printable pages were printed to PDF only, and I could count their pages but not look at them.
- Pinch-zoom on a real touch screen. Zoom was tested with the buttons and the mouse wheel.
- The other screens on a real phone, and the connection for the day. The phone reached the site once, but whether through a hosted copy or the laptop's hotspot was not recorded, so check the one you will use.

## What I would do next

1. **Shared storage.** The smallest thing that works: one small endpoint, or even a shared file, that devices append records to and the daily script reads. The record format is already plain: asset, time, standing water, larvae, actions, note.
2. **Put the thresholds in front of someone who does vector control**, and compare the ranking with real inspection findings.
3. **A real register of small assets**, walked and recorded with a drain time each, to replace the simulated ones and the per-type guesses.
4. **Real inspection records**, so the "simulated" label can come off the history.
5. **Finer rain:** hourly instead of daily, and the weather radar product for rain at the asset instead of at a gauge.
6. **Keep the daily cluster snapshots** to show clusters that closed recently, not only today's.
7. **Make the site installable for offline use on phones** (a service worker), so a scan works with no signal.
8. **Street names, keyboard access to the map, and the four official languages.**
9. **Move it into a real system when there is one.** The data model is three plain things: an asset, an inspection task (an asset plus today's score and reasons), and an inspection record.
