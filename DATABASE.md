# Database

Supabase (Postgres and Auth). Draft, 21 Nov 2026. **(P)** marks a provisional default. All rows are simulated or fictional.

## Tables

| Table | Fields | Notes |
|---|---|---|
| `profiles` | `id` uuid PK (same as the Supabase Auth user), `display_name`, `role` ('resident' or 'admin'), `skills` text[] (from: 'roof', 'solar', 'electrical', 'repair'; empty by default), `active` bool, `created_at` | One row per account. Passwords stay in Supabase Auth. There is no steward role. `skills` decides who may claim tasks marked `needs_skills` |
| `cells` | `id` text PK (for example "C4"), `row`, `col`, `min_lng`, `min_lat`, `max_lng`, `max_lat` | The grid **(P)**. Seeded, 250 m squares |
| `assets` | `id` uuid PK, `code` unique (for example "G-07"), `type` ('garden', 'pond', 'solar'), `name`, `lat`, `lng`, `cell_id` → cells, `profile` text, `inspection_interval_days`, `last_inspected_at`, `next_inspection_due`, `risk_score` int, `risk_level` ('routine', 'this_week', 'inspect_first'), `risk_factors` jsonb, `risk_updated_at` | `profile` is the one assumed property per type: garden 'good_drainage' or 'poor_drainage', pond 'pump' or 'still', solar 'raised_meshed' or 'tray_low'. The `risk_*` fields are a cache written by the API |
| `hazard_events` | `id` uuid PK, `type` ('rain', 'flood'), `started_at`, `duration_hours`, `note`, `created_by` → profiles, `created_at` | Simulated, created from the Admin panel |
| `event_cells` | `event_id` → hazard_events, `cell_id` → cells, `intensity` numeric. PK is the pair | Rain: millimetres in the heaviest hour. Flood: depth in centimetres |
| `complaints` | `id` uuid PK, `asset_id` → assets, `reported_by` → profiles (nullable: null means an anonymous report from the QR page), `category` ('standing_water', 'pests', 'damage', 'blocked_drain', 'other'), `note` (300 characters at most), `status` ('open', 'resolved'), `task_id` → tasks, `created_at`, `resolved_at` | A problem a user reports at an asset |
| `tasks` | `id` uuid PK, `asset_id` → assets, `trigger` ('inspection', 'complaint', 'hazard'), `status` ('open', 'overdue', 'claimed', 'done', 'verified'), `needs_skills` bool, `required_skill` text (nullable, one of the `profiles.skills` values), `priority` int, `reasons` jsonb, `event_id` → hazard_events, `created_at`, `due_at`, `overdue_at`, `claimed_by`, `claimed_at`, `done_by`, `done_at`, `verified_by`, `verified_at` | `priority` is the asset's risk score when the task was created or last updated. `reasons` lists what caused it. `tick()` sets `status` to 'overdue' and fills `overdue_at` when a task stays unclaimed for 2 days; the Admin dashboard lists these first. `needs_skills` is true for roof, solar, cable and broken-part work. 'verified' is **optional**. States are **(P)** |
| `task_reports` | `task_id` PK → tasks, `standing_water` bool, `pests` bool, `damage` bool, `actions` text[] (from: drained, emptied, cleared, covered, repaired, reported), `note`, `risk_before`, `risk_after`, `created_by`, `created_at` | The checklist filled in when a task is completed |
| `app_settings` | `key` text PK, `value` jsonb | `clock_offset_days` for the demo clock **(P)**, `last_tick_at` |

## Relationships

```mermaid
erDiagram
  cells ||--o{ assets : contains
  cells ||--o{ event_cells : "hit by"
  hazard_events ||--|{ event_cells : covers
  assets ||--o{ tasks : has
  assets ||--o{ complaints : receives
  complaints }o--o| tasks : "handled by"
  hazard_events ||--o{ tasks : causes
  tasks ||--o| task_reports : "completed with"
  profiles ||--o{ tasks : "claims, completes, verifies"
  profiles ||--o{ complaints : reports
```

Two rules are enforced by the database itself:

- **One open task per asset and trigger:** a unique index on (`asset_id`, `trigger`) where `status` is 'open', 'overdue' or 'claimed'.
- **A task is claimed by one person:** the claim is `update ... where status in ('open', 'overdue')`, and it either changes one row or none. The API also refuses the claim when `needs_skills` is true and the resident's `skills` do not include `required_skill`.

## Who can read and write

| Table | Anonymous (QR page) | Resident | Admin |
|---|---|---|---|
| `profiles` | None | Read names and roles. Edit their own `skills` | Read all. Create, disable, change role |
| `cells` | None | Read | Read |
| `assets` | Read one asset's code, type, name and risk level, through the API | Read. Completing a task updates the inspection date and the risk fields | Read. Create and edit assets **(optional; the MVP uses seed data)** |
| `hazard_events`, `event_cells` | None | Read | Read. Create from the simulator |
| `complaints` | Create one, through the API, with `reported_by` null | Read all. Create their own | Read all |
| `tasks` | None | Read all. Claim an open or overdue task (if it needs skills, only with the matching skill). Release or complete a task they claimed. Verify a task someone else completed (optional) | The same, and may release or verify any task. Sees overdue tasks first |
| `task_reports` | None | Read all. Create for a task they claimed | Read all |
| `app_settings` | None | Read | Read. Advance the clock, reset the demo data |

Nobody creates tasks directly. The Task Manager does, from the three triggers.

## How it is enforced

- Row-level security is on for every table.
- A signed-in account may **select** from every table above. For `profiles` that is limited to `id`, `display_name`, `role`, `skills` and `active`.
- Anonymous visitors have no direct database access. The QR page reads one asset and posts a complaint through the API, which writes with the service key and limits how often one device can post **(P)**.
- No client may insert, update or delete. Every write goes through the REST API, which checks the caller's session and role and then writes with the service key **(Proposed, ADR 6)**.
- The service key exists only in the server's environment.

## Seed data

Written by `supabase/seed.ts`, the same generator that would fill the optional in-memory fallback.

- A grid of 8 by 6 cells over a neighbourhood modelled on Singapore.
- About 36 assets, 12 of each type, with neutral names such as "Garden G-07". No real building, owner or address.
- Six accounts, five residents (two with skills such as 'solar' or 'roof') and one Admin, with plainly fictional names and addresses ending `@greenparadox.example`.
- Three weeks of simulated history, so the first screen is not empty: past inspections, two rain events, a few completed tasks.
