"""Checks on the day-by-day replay that feeds the rainfall strip on the map.

    python -m unittest discover tests

The replay is the ordinary score, worked out once for each day of the window. These tests
hold it to that: the last day must equal the score itself, and an earlier day must only
know what had happened by then.
"""

import sys
import tomllib
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_snapshot as build  # noqa: E402
import risk  # noqa: E402

CFG = tomllib.loads((ROOT / "config" / "risk_config.toml").read_text(encoding="utf-8"))
N = CFG["rain"]["lookback_days"]
STATION = {"id": "S00", "name": "Test gauge", "dist_m": 500}


def rows(rain, max60=None):
    """Thirteen earlier days followed by the 14-day window, oldest first."""
    assert len(rain) == 2 * N - 1
    start = date(2026, 1, 1)
    return [{"date": (start + timedelta(days=i)).isoformat(), "mm": mm, "max60": (max60[i] if max60 else min(mm, 8.0))}
            for i, mm in enumerate(rain)]


def asset(history=(), flushable=True, drain_h=96):
    a = {"holds_water": True, "drain_time_h": drain_h, "water_source": "rain", "flushable": flushable,
         "cluster": None, "aedes": None, "history": sorted(history, key=lambda r: r["days_ago"])}
    a["parts"] = {"water": risk.water_part(a, CFG), "location": risk.location_part(a, CFG)}
    return a


def visit(days_ago, water=False, actions=()):
    return {"days_ago": days_ago, "standing_water": water, "larvae": False, "actions": list(actions)}


class Replay(unittest.TestCase):
    def test_one_entry_per_day_of_the_window(self):
        self.assertEqual(len(build.daily_replay(asset(), rows([2] * 27), STATION, N, CFG)), N)

    def test_last_day_is_the_score_itself(self):
        a = asset([visit(5), visit(20)])
        table = rows([0, 3] * 13 + [0])
        total, insp, rain = build.daily_replay(a, table, STATION, N, CFG)[-1]
        clears = {N - r["days_ago"] for r in a["history"] if r["days_ago"] <= N}
        want_rain = risk.rain_part(a, table[-N:], clears, STATION, CFG)
        want_insp = risk.inspection_part(a["history"][0], 5, CFG)
        self.assertEqual((rain["points"], insp["points"]), (want_rain["points"], want_insp["points"]))
        self.assertEqual(total, risk.total([a["parts"]["water"], want_insp, want_rain, a["parts"]["location"]], CFG)[0])

    def test_a_drain_drops_after_a_flushing_storm_and_climbs_back(self):
        # Light rain every day; a storm heavy enough to flush on the 9th day of the window.
        rain = [3] * 27
        hour = [3] * 27
        rain[13 + 8], hour[13 + 8] = 70, 45
        pts = [r[2]["points"] for r in build.daily_replay(asset(), rows(rain, hour), STATION, N, CFG)]
        self.assertEqual(pts[7], CFG["rain"]["points_full_cycle"])       # the day before: water has stood all fortnight
        self.assertEqual(pts[8:11], [CFG["rain"]["points_flushed"]] * 3)  # the storm day and the relief after it
        self.assertGreater(pts[11], 0)                                    # then water is standing again
        self.assertGreaterEqual(pts[13], pts[11])

    def test_a_container_does_not_drop_after_the_same_storm(self):
        rain = [3] * 27
        hour = [3] * 27
        rain[13 + 8], hour[13 + 8] = 70, 45
        pts = [r[2]["points"] for r in build.daily_replay(asset(flushable=False), rows(rain, hour), STATION, N, CFG)]
        self.assertEqual(set(pts), {CFG["rain"]["points_full_cycle"]})

    def test_an_inspection_is_not_known_before_it_happens(self):
        # Inspected 4 days before the snapshot, and before that 30 days before.
        a = asset([visit(4), visit(30)])
        insp = [r[1] for r in build.daily_replay(a, rows([0] * 27), STATION, N, CFG)]
        # Index 9 is 4 days before the snapshot: the day of the visit. Index 8 is the day before it.
        self.assertEqual(insp[8]["state"], "long_overdue")
        self.assertEqual(insp[9]["state"], "recent")
        self.assertEqual(insp[13]["state"], "due")


if __name__ == "__main__":
    unittest.main()
