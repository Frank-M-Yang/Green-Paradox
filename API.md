# REST API

Draft, 21 Nov 2026. Base path `/api/v1`. JSON in and out. Times are ISO 8601 in UTC. **(P)** marks a provisional default.

## Conventions

- **Session:** the browser signs in through this API, which sets a cookie. Behind it sits Supabase Auth, or the seeded accounts when the app runs on in-memory data. The browser never calls Supabase directly.
- **Roles:** "any" means any signed-in account. A User/Repairer and an Admin may both do everything a user can.
- **Errors:** `{ "error": { "code": "task_already_claimed", "message": "Someone else claimed this task." } }`

| Status | Codes |
|---|---|
| 400 | `invalid_input` |
| 401 | `not_signed_in` |
| 403 | `not_allowed`, `account_disabled` |
| 404 | `not_found` |
| 409 | `task_already_claimed`, `wrong_state`, `own_work` (verifying a task you completed) |

## Endpoints

| Method | Path | Who | What it does |
|---|---|---|---|
| POST | `/session` | anyone | Sign in with `{ email, password }`. Returns `{ user }` |
| DELETE | `/session` | any | Sign out |
| GET | `/me` | any | The signed-in account |
| GET | `/assets` | any | List. Filters: `type`, `level`, `cell` |
| GET | `/assets/{id}` | any | One asset with its risk factors, open tasks, recent events and history |
| GET | `/cells` | any | The grid, each cell with its current event intensity |
| GET | `/tasks` | any | The shared list. Filters: `status`, `mine`, `trigger`, `asset_id`. Sorted by priority, then age |
| GET | `/tasks/{id}` | any | One task with its reasons and report |
| POST | `/tasks/{id}/claim` | any | open → claimed |
| POST | `/tasks/{id}/release` | the claimer, Admin | claimed → open |
| POST | `/tasks/{id}/complete` | the claimer | claimed → done, with a report |
| POST | `/tasks/{id}/verify` | another user, Admin | done → verified **(P)** |
| POST | `/complaints` | any | Report a problem at an asset. Creates a task or joins an open one |
| GET | `/events` | any | Rainfall and flood events. Filter: `since` |
| POST | `/events` | Admin | Trigger rainfall or flooding on cells **(P)** |
| GET | `/clock` | any | The demo time |
| POST | `/clock/advance` | Admin | Move the demo time forward by days **(P)** |
| POST | `/demo/reset` | Admin | Put the seed data back |
| GET | `/risk/config` | any | The thresholds in use, for display |
| GET | `/users` | Admin | List accounts |
| POST | `/users` | Admin | Create an account: `{ email, display_name, role }` |
| PATCH | `/users/{id}` | Admin | Change `role` or `active` |

## Shapes

```ts
type Level  = 'low' | 'medium' | 'high'
type Factor = { key: 'profile' | 'inspection' | 'weather' | 'reports'; points: number; max: number; reason: string }
type Risk   = { score: number; level: Level; factors: Factor[]; updated_at: string }

type Asset  = { id: string; code: string; type: 'garden' | 'pond' | 'solar'; name: string
                lat: number; lng: number; cell_id: string; profile: string
                last_inspected_at: string | null; next_inspection_due: string
                risk: Risk; open_tasks: number }

type Person = { id: string; display_name: string }
type Task   = { id: string; asset: Pick<Asset, 'id' | 'code' | 'name' | 'type'>
                trigger: 'inspection' | 'complaint' | 'hazard'
                status: 'open' | 'claimed' | 'done' | 'verified'
                priority: number; reasons: { kind: string; text: string }[]
                created_at: string; due_at: string | null
                claimed_by: Person | null; done_by: Person | null; verified_by: Person | null
                report: Report | null }

type Action = 'drained' | 'emptied' | 'cleared' | 'covered' | 'repaired' | 'reported'
type Report = { standing_water: boolean; pests: boolean; damage: boolean; actions: Action[]; note?: string }
```

## Requests that change something

| Call | Body | Success |
|---|---|---|
| `POST /tasks/{id}/claim` | none | 200 `{ task }` |
| `POST /tasks/{id}/complete` | `Report` | 200 `{ task, asset: { id, risk_before: Risk, risk_after: Risk }, follow_up: Task \| null }` |
| `POST /tasks/{id}/verify` | none | 200 `{ task }` |
| `POST /complaints` | `{ asset_id, category, note? }` | 201 `{ complaint, task, created: boolean }` |
| `POST /events` | `{ type: 'rain' \| 'flood', intensity: number, duration_hours: number, cells: string[] }` | 201 `{ event, assets_changed, tasks_created: Task[] }` |
| `POST /clock/advance` | `{ days: number }` (1 to 14) | 200 `{ now, assets_changed, tasks_created: Task[] }` |

`assets_changed` is `{ id, code, level_before: Level, level_after: Level }[]`, so the map can show what an event or a day did.

## Rules the API enforces

- `category` is one of `standing_water`, `pests`, `damage`, `blocked_drain`, `other`. `note` is at most 300 characters.
- `actions` come from the fixed list of general measures. Nothing medical is accepted or returned.
- When `damage` is reported on a solar system, the only action accepted is `reported`.
- `created` is false when a complaint joined a task that was already open for that asset.
- `follow_up` is a new task when the report says a problem remains, for example standing water that was only reported.
- Every response that carries a risk level is for prioritising work. The web app shows that sentence wherever a level appears.
