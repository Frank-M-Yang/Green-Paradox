# The Green Paradox: product requirements

Draft for team review, 21 Nov 2026. Items marked **(P)** are provisional defaults, not yet confirmed. Each has an entry in [ADR.md](ADR.md).

## What it is

A task system for the people who look after a tropical neighbourhood's green and solar infrastructure. It works out which gardens, ponds and solar systems need attention, turns that into tasks, and tracks each task until it is done.

- **Tagline:** "More green ≠ a better environment."
- **The claim, kept narrow:** greenery by itself does not cause disease. Unmanaged green infrastructure creates risk, and managed green infrastructure can be safe. The product makes the solarpunk future workable in the tropics. It does not argue against it.
- **Setting:** a simulated neighbourhood modelled on Singapore. All assets, events, people and accounts are fictional.

## Users and what they need

| User | Needs to | So that |
|---|---|---|
| User/Repairer (one role) | see which assets need attention, and why | they go to the right place first |
| | claim a task so nobody else duplicates it | work is not done twice |
| | record what they found and did, on a phone | the asset's risk level reflects it at once |
| | report a problem they notice at an asset | it becomes a task for whoever is free |
| Admin | create, disable and change the role of accounts | only team members can act |
| | trigger rainfall or flooding during a demo **(P)** | the audience sees the system react |
| Audience and judges | see which factors produced a risk level | they can trust it, or challenge it |

## Core features

| # | Feature | Module |
|---|---|---|
| 1 | Sign in as User/Repairer or Admin, with seeded fictional accounts | REST API, Supabase Auth |
| 2 | Map of the neighbourhood: grid cells, assets coloured by risk level, active events | Web app |
| 3 | Asset page: risk level, the factors behind it, open tasks, history | Risk Assessment |
| 4 | Shared task list: open, claimed, mine, done. Sorted by priority | Task Manager |
| 5 | Claim a task, complete it with a short checklist, verify it **(P)** | Task Manager |
| 6 | Report a problem at an asset (complaint), which creates a task | Task Manager |
| 7 | Tasks created automatically when an inspection comes due | Task Manager |
| 8 | Tasks created when rainfall or flooding hits a cell | Risk Assessment, Task Manager |
| 9 | Admin: user accounts | REST API |
| 10 | Admin: event simulator and demo clock **(P)** | REST API |

## MVP scope

**In:** features 1 to 8 and 10, three asset types, one neighbourhood, seeded data, a "simulated data" banner and a "not a disease forecast" note on every screen.

**In if time allows:** feature 9 beyond a read-only list, the `verified` state, a QR code per asset, live updates without refreshing.

**Out of scope:**

- Real datasets, real weather, real addresses. The first version, in `legacy/`, is the one built on real Singapore open data.
- Any prediction of disease, cases or outbreaks.
- Medical advice. Actions are general measures only: drain, empty, clear, cover, repair, report.
- Assigning tasks to named people **(P)**, routing, notifications, photo upload.
- Creating or editing assets in the app. Assets are seeded.
- Sign-up by the public, real names, real e-mail addresses.
- Languages other than English, a native mobile app, working offline on a phone.

## The demo in seven steps

1. Map: a calm neighbourhood, most assets low.
2. Admin triggers a heavy storm on four cells.
3. Ponds and solar systems in those cells rise and get tasks. Gardens drop for a while: the storm flushed their drains.
4. A Repairer claims a task on a phone, completes the checklist, and the asset's level falls.
5. Admin advances the clock three days. Water has stood: gardens climb back and new tasks appear.
6. A user reports a problem at a pond. A task appears in the shared list.
7. Asset page: the factors behind one risk level, and the line that says what the level is not.

## Rules the product must keep

- Say on screen that the data is simulated.
- Say on screen that risk levels prioritise work and are not disease forecasts.
- More rain does not simply mean more risk (see [RISK_MODEL.md](RISK_MODEL.md)).
- Scoring is by transparent rules. Every threshold lives in one configuration file, marked as a placeholder that needs expert review.
- Fictional people and accounts only.
