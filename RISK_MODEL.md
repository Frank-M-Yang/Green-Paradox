# Risk model

Draft, 21 Nov 2026. Transparent rules, no trained model. **Every number below is a placeholder.** None is validated, and all need review by people who know vector control, drainage and solar maintenance. They live in one file, `src/modules/risk/risk.config.ts`.

**What a risk level is:** a way to decide which asset to attend to first. **What it is not:** a forecast of disease, cases or outbreaks. All inputs are simulated. The model holds no disease data at all.

## Score and level

Four parts are added up, to a maximum of 100. The app shows every part with its reason.

| Part | Points | Asks |
|---|---|---|
| Profile | 0 to 20 | How readily does this asset hold water or shelter pests? An assumption per asset |
| Inspection | 0 to 30 | How long since someone looked, against how often this type should be looked at? |
| Weather | 0 to 30 | What have rain and flooding on its grid cell left behind? |
| Reports | 0 to 20 | Is there an open complaint? |

Low is under 40, Medium is 40 to 59, High is 60 or more.

## The three asset types

| | Garden | Pond | Solar system |
|---|---|---|---|
| What goes wrong | Pots, trays and low ground hold water. Drains block. Overgrowth shelters pests | Water goes still when a pump or overflow fails. Debris collects | Water pools in mounts and trays. Birds and rodents nest under panels. Cables get damaged **(P)** |
| Profile points | Good drainage 8, poor drainage 16 | Pump running 8, still water 20 | Raised and meshed 4, trays or low clearance 14 |
| Inspect every | 7 days | 7 days | 30 days |
| Holds rain for | 3 days | Always holds water | 4 days |
| A heavy storm | Flushes its drains | May overflow it | Fills its trays |

Seven days is roughly one mosquito life cycle from egg to adult in warm weather.

## Inspection part

| Time since the last inspection | Points |
|---|---|
| Up to half the interval | 0 |
| Up to the interval | 10 |
| Up to twice the interval | 20 |
| Longer, or never | 30 |

If the last visit found a problem and only reported it, the part is at least 20 until someone returns.

## Weather part: more rain does not simply mean more risk

Events arrive on grid cells with an intensity **(P)**. Rain is measured in millimetres in its heaviest hour. A heavy storm is 30 mm or more. The model looks back 14 days.

| Case | Garden | Solar system | Pond |
|---|---|---|---|
| **Light or moderate rain** leaves still water. Showers that return before it drains keep the count running | Standing 1 to 2 days: 8. 3 to 6 days: 16. 7 days or more: 25 | The same steps | 0. It is water already |
| **A heavy storm** | Flushed: 0 for 3 days, and the count restarts | Trays are filled, not flushed: counts as rain, plus 10 until inspected | Overflow check: 20 until inspected |
| **After the rain stops** | Dry after 3 days: 0 | Dry after 4 days: 0 | No change |
| **Flood on the cell** | 30 until inspected after the water recedes | 30 until inspected | 30 until inspected |

- The count is of unbroken days of standing water, not days since the last shower.
- A flood is not treated as a flush. It leaves pools behind as it recedes.
- The part never exceeds 30.

**Where the flush rule comes from, and its limits.** A year of field surveys in Singapore found most Aedes breeding in storm drains gone after intense monsoon storms (Seidahmed and Eltahir 2016, PMC4961380), and dengue outbreak risk was lower for some weeks after flushing events (Benedum et al. 2018, PMC6283346). Both are about drains. Neither gives a single rainfall cut-off. None of our three asset types is a drain, so applying the rule to a garden's drains is our assumption, and the first thing an expert should check.

## Reports part

One open complaint: 12. Two or more: 20. A damage complaint on a solar system: 20.

## What lowers risk

Completing a task, at the moment it is marked done:

- Inspection returns to 0.
- Reports return to 0, because the linked complaints are resolved.
- Storm, overflow and flood checks are cleared.
- The standing-water count restarts, if the checklist says no water was left: none found, or it was drained, emptied, cleared, covered or repaired.

Profile does not change. An asset that holds water by its nature keeps those points.

## When weather creates a task

| Event | Garden | Pond | Solar system |
|---|---|---|---|
| Light or moderate rain | None now | None | None now |
| Heavy storm | None now: it was flushed | Check the overflow | Check trays, mounts and cables |
| Flood | Inspect once the water has receded | The same | The same. Damaged cables are reported, never handled |
| Days pass | A follow-up when water has stood 7 days or the level reaches High | When the level reaches High | The same as a garden |

## One storm, three assets

A heavy storm on day 0, with showers on days 2 and 5, so nothing dries out. Nobody visits. Each cell is the score at the end of that day.

| Asset | Day before | Storm day | Day 4 | Day 7 |
|---|---|---|---|---|
| Garden, poor drainage, last inspected 8 days before, water standing 4 days | 52 Medium | **36 Low**: flushed | 52 Medium: water is back | 71 High: follow-up task |
| Pond, still water, inspected 2 days before | 20 Low | 40 Medium: overflow check, task | 50 Medium | 60 High |
| Solar system with trays, inspected 10 days before | 14 Low | 32 Low: trays filled, task | 40 Medium | 54 Medium |

Same storm, opposite first effects. That is the point the model has to keep.

## Not in the model

Disease or case data. Real weather. Temperature. The size of an asset. Anything about who uses the place.
