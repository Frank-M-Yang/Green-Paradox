# Canopy Care: 5-minute walkthrough

Written for the snapshot of **21 Nov 2026**. The names, ranks and scores below are only right for that day, so rebuild it before you present (step 1).

The first asset you open is a **real** place, and you say out loud that the inspection dates are simulated. Both are deliberate: the top row of the task list is a simulated drain, and the largest part of the score rests on the simulated history. Judges will notice either way, so say it first.

## Before you go on stage

1. Rebuild the demo day. This uses the cached data and needs no network.

   ```
   python scripts/refresh.py --as-of 2026-11-21 --offline
   ```

2. Make the site reachable from the phone. Host the `site` folder, or serve the project folder from the laptop and join the phone to the laptop's hotspot:

   ```
   python -m http.server 8000 --bind 0.0.0.0
   ```

3. On the laptop, open the site **at that address** (not from the file), so the laptop and the QR code agree.
4. Open `qr-sheet.html` at the same address, click the label **Pot tray A**, print it, and stick it on a real plant saucer. Scan it once with the phone to be sure it opens the checklist.
5. On both the laptop and the phone: Dashboard, then **Delete records on this device**. Otherwise yesterday's rehearsal is still in the list.
6. Leave the laptop on the **Map** screen with **Rainfall** set to "Real: last 14 days" and the day marker at the right-hand end. Have `task-sheet.html` printed, or open in a second tab.

If the phone cannot reach the laptop on the day, skip the scan at 2:15 and go straight to 2:55, where the same checklist is filled in on the laptop. Everything else works from the folder with no network at all.

## The walkthrough

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00 | Map | Point at the key, top left. | "Most greening plans stop at planting. In the humid tropics, what nobody maintains holds water, and standing water breeds mosquitoes. This is Ang Mo Kio west in Singapore: 34 real places from open data, plus 19 small assets we simulated, drawn as diamonds. A marker grows and darkens with its priority for inspection. Small pale ones have nothing due." |
| 0:20 | Map | Click the violet badge **29**. | "Violet marks the active dengue clusters on the snapshot day, from the environment agency's open data. For this one the agency lists the breeding habitats it found: flowerpots, pails, trays, a closed drain. Standing water that nobody removed. Greenery by itself does not breed mosquitoes. Unmanaged water does." |
| 0:45 | Map | Click the dark circle **78** just above the violet badge 5 (Serenade Walk Playground). | "A real playground from the parks board's list. Its priority is a sum of four things you can read. Two rest on real data: it has held water for about five days without a break, and it sits inside a cluster. One is an assumption about parks. And one is simulated: '26 days since an inspection' is a made-up date, and the label says so. In real use the inspections themselves fill that in. 78 out of 100. No trained model, and it does not predict cases. It tells a small team where to walk first." |
| 1:20 | Map | Click the dark circle **74** below and left of the violet badge 5 (Storm drain at Thomson Walk). Press **Play** under the map. It takes 13 seconds. | "Now the part people get wrong: more rain does not simply mean more risk. This is the real rain of the last fourteen days, and a real drain site from the water agency. Watch it. Showers: it climbs. A visit on the 12th, simulated: it drops. Then the storm of 16 November. Research in Singapore found storms like that flush larvae out of drains, so its rain part falls to zero. Three days later water is standing again and it is back near the top." |
| 1:55 | Tasks | Click **Tasks**. Scroll a little. Hold up the printed sheet. | "The same ranking as a task list, each with its reasons. The top row is one of our simulated drains, and it says SIMULATED. It also prints as one page with a walking route, because the lowest-tech version of this is a clipboard." |
| 2:15 | Phone | Scan the QR sticker on the saucer. Answer: standing water **Yes**, larvae **No**, action **Emptied**. **Save inspection**. Show the phone. | "Each asset has a QR code. Scanning it opens that asset's checklist. Four questions, general measures only. I found water, emptied the tray, saved. Priority drops from 73 to 38: from 'inspect first' to 'routine'." |
| 2:55 | Tasks | On the laptop, find **Pot tray A** (rank 6), click **Inspect**, give the same answers, **Save inspection**. Click **Show on map**, wait two seconds, then **Tasks**. | "Being honest about a limit: records stay on the device that made them. The phone and this laptop do not share storage yet, and that is the first thing we would add. Here is the same inspection on the laptop. On the map the marker shrinks and pales: 73 to 38. In the list it has gone from sixth to thirty-eighth. That is the whole idea: managed, it stops asking for attention." |
| 3:30 | Scenarios | Click **Scenarios**. Press **2**, then **4**, then **1**. | "The same rule over other real periods. August 2025: showers on most days, nothing strong enough to flush, and five more assets say 'inspect first'. January 2026, a dry spell: everything fed by rain has dried out, and what is left is water that people store or pour. One rule, and the list reorders itself. The thresholds are placeholders and we say so on every screen." |
| 4:05 | Dashboard | Click **Dashboard**. Scroll to "What is real and what is not". | "For whoever runs this: about half the assets inspected on time, more than twenty overdue. And what is real and what is not, spelled out, down to this table: 37 per cent of all the points on today's list come from the simulated inspection history. Locations, clusters and rain are real." |
| 4:35 | Dashboard | Scroll to "About this snapshot". | "Low-tech first. One script runs once a day and then nothing runs at all. The whole thing, map and fourteen days of scores included, is about 250 kilobytes: less than one phone photo. It opens from a folder with no internet." |
| 4:50 | Map | Click **Map**. | "Managed green infrastructure can be safe. This is how you manage it." |

## Numbers to have ready

All for the 21 Nov 2026 snapshot, before any inspection is recorded. Once Pot tray A has been inspected in the walkthrough it sits at 38, every "Inspect first" count below is one lower, and whatever ranked below it moves up a place.

| Rainfall | Period replayed | Inspect first | Top of the list |
|---|---|---|---|
| Real: last 14 days | 7 to 20 Nov 2026 | 15 | Roadside drain A 84, BBQ pit 78, Serenade Walk Playground 78 |
| Light to moderate rain | 6 to 19 Aug 2025 | 20 | Roadside drain A 93, Serenade Walk Playground 87, Storm drain at Thomson Walk 83 |
| Heavy rain | 4 to 17 Nov 2026 | 13 | BBQ pit 78, Community garden 1098 73, Pot tray A 73 |
| Dry spell | 18 to 31 Jan 2026 | 10 | Community garden 1098 73, Pot tray A 73, Rain barrel A 70 |

Today's scores run from 0 to 84: 15 inspect first, 21 this week, 17 routine.

The rainfall strip, real period. Each number is the score after that day's rain:

| Asset | 15 Nov | 16 Nov (storm) | 17 Nov | 18 Nov | 19 Nov | 20 Nov (today) |
|---|---|---|---|---|---|---|
| Storm drain at Thomson Walk, real PUB sensor site | 59 | 43 | 43 | 43 | 74 | 74 |
| Storm drain at Ang Mo Kio Ave 3 / Mayflower Ave, real PUB sensor site | 49 | 33 | 48 | 48 | 64 | 64 |
| Roadside drain A, simulated | 83 | 58 | 58 | 58 | 84 | 84 |
| BBQ pit in Ang Mo Kio Town Garden West, real: a container, so no drop | 78 | 78 | 78 | 78 | 78 | 78 |

- The drop on 16 Nov is the rain part alone, going to 0 (from 16 for the two real drains, from 25 for Roadside drain A). The rise afterwards is the rain part returning to 16 **and** the simulated inspection history ageing in the same days (+15 for each real drain, +10 for Roadside drain A). If asked, say both. Open an asset while the days play and the panel shows the two parts separately.
- Earlier in the window the drains also dip when a simulated visit falls on that day (Thomson Walk on 12 Nov). Those dips are made-up data; the one on 16 Nov is rain.
- "Inspect first" count by day, 7 to 20 Nov: 12, 12, 13, 12, 13, 10, 12, 12, 11, **9** (after the storm), 10, 12, 15, 15.
- Storm drain at Thomson Walk: rank 4 with real rain, 3 in light rain, 21 after heavy rain, 18 in the dry spell.
- BBQ pit in Ang Mo Kio Town Garden West, a real park facility: rank 2, 5, 1, 20.
- Two assets that stay at the bottom whatever the rain, for "managed can be safe": **Planter box C** (free-draining, score 0) and **Rain barrel B** (fitted lid, checked two days ago, score 35).
- Where today's points come from: last inspection 37% (simulated history), holds water 32% (assumed per asset type), rain 22% (real rainfall, assumed drain time), location 9% (real clusters and high-Aedes areas).

## Questions you may get

- **"Is this predicting dengue?"** No. It ranks inspections. The clusters on the map are where cases were already reported.
- **"Isn't the ranking driven by made-up inspection dates?"** Largely, yes: that part carries the most weight and its history is simulated, which the Dashboard quantifies. The rain, the clusters and the locations are real. On day one of real use every asset would read "never inspected" and score the same 35 for that part, so the order would come from water, rain and location alone. Each real inspection then replaces a made-up date.
- **"This drain empties in 4 days. How can it have held water for 5?"** The count is unbroken days of standing water, not days since the last shower. It was wet on the 16th and rained on again on the 17th, 18th and 19th, each time before it could drain. The 4 days run from the last rain.
- **"What does the day marker show?"** The score the same script would have given after each day's rain, worked out in advance: rain up to that day, the simulated inspections made by then, and today's clusters, because the agency publishes no history of them.
- **"Are the markers exactly where the assets are?"** Where two would cover each other the drawing nudges them apart, by at most a marker's width, and a thin line leads back to a dot on the true spot. Zoom in and they return. The data is not moved.
- **"Are the thresholds validated?"** No. They are placeholders in one file, `config/risk_config.toml`, with the reasoning written next to them. The two papers behind the flushing rule do not give a single cut-off, and the file says so.
- **"Which garden is 'Community garden 1098'?"** A real one, from the national list of community gardens, shown by its number in that list. The organisation names are hidden in this build because the site is public and the inspection dates beside them are made up. No made-up problem is attached to any real place. `show_garden_names = true` in `config/demo_config.toml` brings the names back.
- **"Why are the low ones still pink? Which ones are safe?"** The colour is one scale from pale to dark, and it means how soon to inspect. Nothing on this map is labelled safe, because the score cannot know that. Pale means nothing is due.
- **"Where is the rooftop greenery?"** The open dataset of skyrise greenery has been withdrawn. Community gardens stand in for it, and the two roof gardens shown are simulated.
- **"What happens when the data source is down?"** The script uses the last copy it saved and the site shows that copy's date.
