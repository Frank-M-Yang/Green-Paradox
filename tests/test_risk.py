"""Checks on the score. Run from the project folder:

    python -m unittest discover tests

They read config/risk_config.toml, so they describe the behaviour of the current settings:
if you change a threshold on purpose, expect to update the matching numbers here.
"""

import sys
import tomllib
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import risk  # noqa: E402

CFG = tomllib.loads((ROOT / "config" / "risk_config.toml").read_text(encoding="utf-8"))
STATION = {"id": "S00", "name": "Test gauge", "dist_m": 500}


def days(rain, max60=None):
    """Fourteen days ending yesterday. rain is a list of mm, oldest first; None means no data."""
    start = date(2026, 1, 1)
    out = []
    for i, mm in enumerate(rain):
        hour = None if mm is None else (max60[i] if max60 else min(mm, 8.0))
        out.append({"date": (start + timedelta(days=i)).isoformat(), "mm": mm, "max60": hour})
    return out


def asset(drain_h=96, source="rain", flushable=False, holds=True):
    return {"holds_water": holds, "drain_time_h": drain_h, "water_source": source, "flushable": flushable}


DRAIN = asset(96, flushable=True)
TRAY = asset(72, source="watered")
PARK = asset(48)


class Rain(unittest.TestCase):
    def part(self, a, rain, max60=None, clears=()):
        return risk.rain_part(a, days(rain, max60), set(clears), STATION, CFG)

    def test_dry_spell_scores_nothing(self):
        p = self.part(DRAIN, [0] * 14)
        self.assertEqual((p["state"], p["points"]), ("dry", 0))

    def test_trace_of_rain_is_not_wetting(self):
        p = self.part(DRAIN, [0.4] * 14)
        self.assertEqual(p["state"], "dry")

    def test_light_rain_every_other_day_keeps_water_standing(self):
        p = self.part(DRAIN, [3, 0] * 7)
        self.assertEqual(p["state"], "full_cycle")
        self.assertEqual(p["standing_days"], 14)
        self.assertEqual(p["points"], CFG["rain"]["points_full_cycle"])

    def test_more_rain_is_not_simply_more_points(self):
        light = self.part(DRAIN, [3, 0] * 7)
        storm = self.part(DRAIN, [3, 0] * 6 + [60, 0], max60=[3, 0] * 6 + [45, 0])
        self.assertGreater(light["points"], storm["points"])

    def test_heavy_storm_flushes_a_drain(self):
        rain = [5] * 12 + [60, 2]
        p = self.part(DRAIN, rain, max60=[4] * 12 + [45, 2])
        self.assertEqual((p["state"], p["points"]), ("flushed", CFG["rain"]["points_flushed"]))

    def test_flush_by_daily_total_alone(self):
        p = self.part(DRAIN, [0] * 13 + [55], max60=[0] * 13 + [12])
        self.assertEqual(p["state"], "flushed")

    def test_heavy_storm_fills_a_container(self):
        rain = [5] * 12 + [60, 2]
        p = self.part(asset(96, flushable=False), rain, max60=[4] * 12 + [45, 2])
        self.assertEqual(p["state"], "full_cycle")
        self.assertEqual(p["standing_days"], 14)

    def test_after_the_relief_the_clock_runs_from_the_flush(self):
        rain = [0] * 8 + [60, 2, 2, 2, 2, 2]
        p = self.part(DRAIN, rain, max60=[0] * 8 + [45, 2, 2, 2, 2, 2])
        self.assertEqual(p["state"], "several_days")
        self.assertEqual(p["standing_days"], 6)

    def test_showers_before_it_drains_make_one_unbroken_spell(self):
        # A drain that empties in 4 days, flushed 5 days ago, then rain on each of the next 3 days.
        # The water never had 4 dry days to drain, so it has stood for 5 days, not 2.
        rain = [0] * 9 + [60, 3, 3, 3, 0]
        p = self.part(DRAIN, rain, max60=[0] * 9 + [45, 3, 3, 3, 0])
        self.assertEqual((p["state"], p["standing_days"]), ("several_days", 5))
        self.assertIn("without a break", p["text"])
        self.assertIn("counts from the last rain", p["text"])

    def test_a_gap_longer_than_the_drain_time_restarts_the_count(self):
        # Rain 10 days ago, then 7 dry days (longer than the 4 it takes to drain), then rain 2 days ago.
        rain = [0] * 4 + [8] + [0] * 7 + [8, 0]
        p = self.part(DRAIN, rain)
        self.assertEqual((p["state"], p["standing_days"]), ("fresh", 2))

    def test_water_stands_after_rain_stops_until_the_drain_time_passes(self):
        wet = self.part(PARK, [0] * 12 + [10, 0])      # rain two days ago, drains in 48 h
        dry = self.part(PARK, [0] * 11 + [10, 0, 0])   # rain three days ago
        self.assertEqual(wet["state"], "fresh")
        self.assertEqual(dry["state"], "dry")
        self.assertIn("should be dry", dry["text"])

    def test_slow_drain_is_still_wet_when_a_fast_one_is_dry(self):
        rain = [0] * 10 + [10, 0, 0, 0]                # rain four days ago
        self.assertEqual(self.part(asset(24), rain)["state"], "dry")
        self.assertEqual(self.part(asset(96), rain)["state"], "several_days")

    def test_assets_not_fed_by_rain_get_a_fixed_value(self):
        for rain in ([0] * 14, [30] * 14):
            p = self.part(TRAY, rain)
            self.assertEqual((p["state"], p["points"]), ("not_rain_fed", CFG["rain"]["points_not_rain_fed"]))

    def test_asset_that_holds_no_water_scores_nothing(self):
        p = self.part(asset(holds=False), [20] * 14)
        self.assertEqual(p["points"], 0)

    def test_inspection_that_cleared_water_restarts_the_clock(self):
        rain = [5] * 14
        untouched = self.part(asset(96), rain)
        cleared = self.part(asset(96), rain, clears={11})   # three days ago
        self.assertEqual(untouched["standing_days"], 14)
        self.assertEqual(cleared["standing_days"], 3)

    def test_cleared_today_scores_nothing(self):
        p = self.part(asset(96), [5] * 14, clears={14})
        self.assertEqual((p["state"], p["points"]), ("dry", 0))

    def test_missing_readings_are_reported_not_treated_as_rain(self):
        p = self.part(DRAIN, [None] * 14)
        self.assertEqual(p["points"], 0)
        self.assertIn("missing", p["text"])

    def test_no_data_at_all(self):
        p = risk.rain_part(DRAIN, [], set(), None, CFG)
        self.assertEqual((p["state"], p["points"]), ("no_data", 0))


class Inspection(unittest.TestCase):
    def part(self, days_since, water=False, larvae=False, actions=()):
        last = {"standing_water": water, "larvae": larvae, "actions": list(actions)}
        return risk.inspection_part(last, days_since, CFG)

    def test_never_inspected(self):
        p = risk.inspection_part(None, None, CFG)
        self.assertEqual((p["state"], p["points"]), ("never", CFG["inspection"]["points_never"]))

    def test_steps_follow_the_life_cycle(self):
        self.assertEqual([self.part(d)["state"] for d in (0, 3, 4, 7, 8, 14, 15, 40)],
                         ["recent", "recent", "due", "due", "overdue", "overdue", "long_overdue", "long_overdue"])

    def test_points_never_fall_as_days_pass(self):
        pts = [self.part(d)["points"] for d in range(0, 40)]
        self.assertEqual(pts, sorted(pts))

    def test_larvae_last_time_brings_it_due_sooner(self):
        self.assertEqual(self.part(4, water=True, larvae=True, actions=["emptied"])["state"], "overdue")
        self.assertEqual(self.part(4, water=True, larvae=False, actions=["emptied"])["state"], "due")

    def test_water_left_behind_needs_a_return_visit(self):
        p = self.part(1, water=True, actions=["reported"])
        self.assertEqual((p["state"], p["points"]), ("follow_up", CFG["inspection"]["points_follow_up"]))

    def test_water_removed_does_not(self):
        for action in sorted(risk.REMOVING_ACTIONS):
            self.assertEqual(self.part(1, water=True, actions=[action])["state"], "recent", action)

    def test_only_general_measures_are_offered(self):
        self.assertEqual(risk.ACTIONS, ["drained", "emptied", "cleared", "covered", "repaired", "reported"])


class WaterAndLocation(unittest.TestCase):
    def test_longer_drain_time_never_scores_less(self):
        pts = [risk.water_part({"holds_water": True, "drain_time_h": h}, CFG)["points"] for h in (1, 23, 24, 71, 72, 167, 168, 720)]
        self.assertEqual(pts, sorted(pts))

    def test_no_water_no_points(self):
        self.assertEqual(risk.water_part({"holds_water": False, "drain_time_h": 0}, CFG)["points"], 0)

    def test_location(self):
        c = CFG["location"]
        inside = {"cluster": {"locality": "X", "cases": 3, "inside": True, "dist_m": 0}, "aedes": "A"}
        near = {"cluster": {"locality": "X", "cases": 3, "inside": False, "dist_m": 100}, "aedes": None}
        far = {"cluster": {"locality": "X", "cases": 3, "inside": False, "dist_m": 300}, "aedes": None}
        self.assertEqual(risk.location_part(inside, CFG)["points"], c["points_in_dengue_cluster"] + c["points_in_high_aedes_area"])
        self.assertEqual(risk.location_part(near, CFG)["points"], c["points_near_dengue_cluster"])
        self.assertEqual(risk.location_part(far, CFG)["points"], 0)
        self.assertEqual(risk.location_part({"cluster": None, "aedes": None}, CFG)["points"], 0)


class Total(unittest.TestCase):
    def test_maximum_is_one_hundred(self):
        self.assertEqual(risk.water_max(CFG) + risk.inspection_max(CFG) + risk.rain_max(CFG) + risk.location_max(CFG), 100)

    def test_bands(self):
        b = CFG["bands"]
        self.assertEqual([risk.band_of(s, CFG) for s in (0, b["medium"] - 1, b["medium"], b["high"] - 1, b["high"], 100)],
                         ["low", "low", "medium", "medium", "high", "high"])

    def test_no_wording_suggests_a_forecast(self):
        banned = ("predict", "forecast", "outbreak risk", "will get dengue")
        a = {"holds_water": True, "drain_time_h": 96, "water_source": "rain", "flushable": True,
             "cluster": {"locality": "X", "cases": 3, "inside": True, "dist_m": 0}, "aedes": "A"}
        texts = [risk.water_part(a, CFG)["text"], risk.location_part(a, CFG)["text"],
                 risk.rain_part(a, days([5] * 14), set(), STATION, CFG)["text"],
                 risk.inspection_part({"standing_water": True, "larvae": True, "actions": []}, 9, CFG)["text"]]
        for t in texts:
            for word in banned:
                self.assertNotIn(word, t.lower())


if __name__ == "__main__":
    unittest.main()
