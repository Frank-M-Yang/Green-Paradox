"""Inspection priority score: four parts added together. Pure functions, no file or network access.

The numbers all come from config/risk_config.toml, where every one of them is marked as a
placeholder. This module only applies them. It ranks inspections; it predicts nothing.

Each part returns the same shape, which the site shows as-is:

    {"key": "rain", "points": 16, "max": 25, "state": "standing",
     "short": "Water standing about 5 days", "text": "longer explanation ..."}

The inspection part is also implemented in site/app.js, because the browser has to recompute
it when an inspection is recorded. The site's self-test compares the two.
"""

from datetime import date

# Actions an inspector can record. General measures only: nothing medical, no chemicals.
ACTIONS = ["drained", "emptied", "cleared", "covered", "repaired", "reported"]
# Actions that leave the asset without accessible standing water. "reported" alone does not.
REMOVING_ACTIONS = {"drained", "emptied", "cleared", "covered", "repaired"}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def short_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]}"


def days_ago_text(n):
    if n <= 0:
        return "today"
    if n == 1:
        return "1 day ago"
    return f"{n} days ago"


def fmt_hours(h):
    if h >= 168:
        return "a week or more"
    if h >= 48:
        return f"about {round(h / 24)} days"
    return f"about {int(h)} hours"


def join_dates(days, limit=4):
    """'17 Nov, 18 Nov and 19 Nov'. Only the newest `limit` are named; the rest are counted."""
    names = [short_date(d["date"]) for d in days[-limit:]]
    text = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    earlier = len(days) - len(names)
    if earlier:
        text += f" (and {earlier} earlier day{'s' if earlier != 1 else ''})"
    return text


def removed_water(record):
    """True when an inspection left no accessible standing water behind."""
    return (not record.get("standing_water")) or bool(set(record.get("actions", [])) & REMOVING_ACTIONS)


# --------------------------------------------------------------------------- part 1: water


def water_max(cfg):
    w = cfg["water"]
    return max(v for k, v in w.items() if k.startswith("points_"))


def water_part(asset, cfg):
    w = cfg["water"]
    basis = "set for this simulated asset" if asset.get("own_properties") else "assumed for this asset type"
    out = {"key": "water", "max": water_max(cfg)}
    if not asset["holds_water"]:
        out.update(points=w["points_if_no_water"], state="none", short="Does not hold water",
                   text=f"Not expected to hold water ({basis}).")
        return out
    h = asset["drain_time_h"]
    if h < 24:
        pts, state, short = w["points_drains_within_1_day"], "hours", "Drains within a day"
    elif h < 72:
        pts, state, short = w["points_drains_within_3_days"], "days", "Holds water 1 to 3 days"
    elif h < 168:
        pts, state, short = w["points_drains_within_7_days"], "several_days", "Holds water for days"
    else:
        pts, state, short = w["points_holds_7_days_or_more"], "week_plus", "Holds water a week or more"
    # The drain time runs from the last time water arrived, so say which kind of arrival that is.
    after = {"rain": " after the last rain", "watered": " after the last watering"}.get(asset.get("water_source"), "")
    out.update(points=pts, state=state, short=short,
               text=f"Once wet it holds water for {fmt_hours(h)}{after} ({basis}). "
                    f"A mosquito needs about {cfg['life_cycle']['days']} days of unbroken standing water to develop.")
    return out


# --------------------------------------------------------------------------- part 2: inspection


def inspection_max(cfg):
    c = cfg["inspection"]
    return max(c["points_recent"], c["points_due"], c["points_overdue"], c["points_long_overdue"],
               c["points_never"], c["points_follow_up"])


def inspection_part(last, days_since, cfg):
    """last: the most recent inspection record or None. days_since: whole days since it."""
    c = cfg["inspection"]
    cycle = cfg["life_cycle"]["days"]
    out = {"key": "inspection", "max": inspection_max(cfg)}
    if last is None:
        out.update(points=c["points_never"], state="never", short="Never inspected", text="No inspection on record.")
        return out
    larvae = bool(last.get("larvae"))
    f = c["day_limits_factor_after_larvae"] if larvae else 1.0
    when = days_ago_text(days_since)
    if days_since <= c["recent_up_to_days"] * f:
        pts, state, short = c["points_recent"], "recent", f"Inspected {when}"
        text = f"Inspected {when}."
    elif days_since <= c["due_up_to_days"] * f:
        pts, state, short = c["points_due"], "due", f"Inspected {when}, due soon"
        text = f"Inspected {when}. Due again within one mosquito life cycle (about {cycle} days)."
        if larvae:
            text = f"Inspected {when}. Larvae were found then, so it comes due after {c['recent_up_to_days'] * f:g} days instead of {c['recent_up_to_days']}."
    elif days_since <= c["overdue_up_to_days"] * f:
        pts, state, short = c["points_overdue"], "overdue", f"Not inspected for {days_since} days"
        text = f"Not inspected for {days_since} days, which is longer than one mosquito life cycle (about {cycle} days)."
        if larvae:
            text = f"Not inspected for {days_since} days. Larvae were found last time, so it counts as overdue after {c['due_up_to_days'] * f:g} days instead of {c['due_up_to_days']}."
    else:
        pts, state, short = c["points_long_overdue"], "long_overdue", f"Not inspected for {days_since} days"
        text = f"Not inspected for {days_since} days, which is more than two mosquito life cycles."
        if larvae:
            text = f"Not inspected for {days_since} days. Larvae were found last time, so it counts as long overdue after {c['overdue_up_to_days'] * f:g} days instead of {c['overdue_up_to_days']}."
    if last.get("standing_water") and not removed_water(last) and c["points_follow_up"] >= pts:
        pts, state, short = c["points_follow_up"], "follow_up", "Standing water left at last visit"
        text = f"The last inspection ({when}) found standing water that was not removed. It needs a return visit."
    out.update(points=pts, state=state, short=short, text=text)
    return out


# --------------------------------------------------------------------------- part 3: rain


def rain_max(cfg):
    r = cfg["rain"]
    return max(v for k, v in r.items() if k.startswith("points_"))


def is_flush_day(day, cfg):
    r = cfg["rain"]
    return day["mm"] is not None and ((day["max60"] or 0) >= r["flush_hour_mm"] or day["mm"] >= r["flush_day_mm"])


def rain_part(asset, days, clear_days, station, cfg):
    """Estimate how long water has stood in the asset, from daily rain at the nearest station.

    days        oldest to newest, the complete days before the snapshot date:
                {"date": "2026-11-16", "mm": 47.0 or None, "max60": 30.4 or None}
                mm is None when too few readings arrived that day to trust a total.
    clear_days  set of positions in `days` on which an inspection left the asset without
                standing water. len(days) stands for the snapshot day itself.
    station     {"id": "S109", "name": "Ang Mo Kio Avenue 5", "dist_m": 912}
    """
    r = cfg["rain"]
    n = len(days)
    out = {"key": "rain", "max": rain_max(cfg), "standing_days": 0}
    where = f"at {station['id']} {station['name']}" if station else "at the nearest station"

    if not asset["holds_water"]:
        out.update(points=r["points_dry"], state="none", short="Rain does not collect here",
                   text="Not expected to hold water, so rain adds nothing.")
        return out
    if asset["water_source"] != "rain":
        how = "is kept wet by watering" if asset["water_source"] == "watered" else "holds stored water"
        out.update(points=r["points_not_rain_fed"], state="not_rain_fed", short="Holds water whatever the weather",
                   text=f"This asset {how}, so it has water whatever the weather. It gets a fixed value and rain does not change it.")
        return out
    if not days:
        out.update(points=r["points_dry"], state="no_data", short="No rain data",
                   text="No rainfall readings were available, so this part is left at 0.")
        return out

    persist = max(0, round(asset["drain_time_h"] / 24))  # days water stays after the last wetting rain
    start = last_wet = flush = cleared = None
    missing = 0
    for d, day in enumerate(days):
        if start is not None and d > last_wet + persist:
            start = last_wet = None  # dried out before this day
        if d in clear_days:
            start = last_wet = flush = None
            cleared = d
        if day["mm"] is None:
            missing += 1
        elif asset["flushable"] and is_flush_day(day, cfg):
            start = last_wet = flush = d  # washed through; the clock restarts with whatever is left behind
        elif day["mm"] >= r["wetting_rain_mm"]:
            if start is None:
                start = d
            last_wet = d
    dried = False
    if start is not None and n > last_wet + persist:
        start = None
        dried = True
    if n in clear_days:
        start = last_wet = flush = None
        cleared = n

    note = f" Rain readings were missing for {missing} of the {n} days." if missing else ""
    wet_days = [d for d in days if d["mm"] is not None and d["mm"] >= r["wetting_rain_mm"]]
    drain = fmt_hours(asset["drain_time_h"])

    # heavy rain that flushes
    if start is not None and flush is not None and start == flush and n - flush <= r["flush_relief_days"]:
        fd = days[flush]
        out.update(points=r["points_flushed"], state="flushed", short=f"Flushed by heavy rain {days_ago_text(n - flush)}",
                   text=f"Heavy rain on {short_date(fd['date'])} ({fd['mm']:.1f} mm, {fd['max60']:.1f} mm in one hour, {where}) "
                        f"is assumed to have flushed this drain. It scores 0 for {r['flush_relief_days']} days after a flush.{note}")
        return out

    # no water expected
    if start is None:
        if cleared is not None and not any(
            i > cleared and d["mm"] is not None and d["mm"] >= r["wetting_rain_mm"] for i, d in enumerate(days)
        ):
            when = days_ago_text(n - cleared)
            text = f"Left without standing water at the inspection {when}, and no day with {r['wetting_rain_mm']:g} mm or more since."
            short = "Cleared, no rain since"
        elif not wet_days:
            text = f"No day with {r['wetting_rain_mm']:g} mm of rain or more in the last {n} days {where}. Expected to be dry."
            short = "Dry spell: no water expected"
        else:
            lw = wet_days[-1]
            ago = n - days.index(lw)
            text = (f"The last rain was {days_ago_text(ago)} ({lw['mm']:.1f} mm on {short_date(lw['date'])}, {where}). "
                    f"It drains in {drain}, so it should be dry by now.")
            short = "Rain has stopped: dried out"
        out.update(points=r["points_dry"], state="dry", short=short, text=text + note)
        return out

    # water standing
    #
    # `standing` counts unbroken days of water, from the day the asset was last dry (or flushed,
    # or left clear by an inspection) to the snapshot day. It is not the time since the latest
    # shower: rain that arrives before the asset has drained tops it up, and anything already
    # living in the water carries on. The drain time only says how long the water outlasts the
    # LAST rain. The text below spells this out, because "drains in 4 days" next to "water for
    # 5 days" otherwise reads like a contradiction.
    standing = n - start
    if standing <= r["fresh_up_to_days"]:
        pts, state = r["points_fresh"], "fresh"
    elif standing <= r["several_up_to_days"]:
        pts, state = r["points_several_days"], "several_days"
    else:
        pts, state = r["points_full_cycle"], "full_cycle"
    first = short_date(days[start]["date"])
    topups = [d for i, d in enumerate(days) if i > start and d["mm"] is not None and d["mm"] >= r["wetting_rain_mm"]]
    span = f"{standing} day{'s' if standing != 1 else ''}"
    if flush is not None and start == flush:
        lead = f"Heavy rain on {first} flushed this drain, so the count starts again from that day."
    elif cleared is not None and start >= cleared:
        lead = f"Left clear at the inspection {days_ago_text(n - cleared)}. Rain on {first} wet it again."
    elif start == 0:
        lead = f"Wet since at least {first}, the first day of the {n}-day rain record."
    else:
        lead = f"Wet since the rain on {first}."
    if topups:
        kept = (f"Rain on {join_dates(topups)} topped it up before it could drain, so it has held water without a break "
                f"for about {span}. Its drain time of {drain} counts from the last rain, not the first.")
    else:
        kept = f"It has held water for about {span} and drains in {drain} if no more rain falls."
    tail = "No storm heavy enough to flush it since." if asset["flushable"] else "Heavy rain fills this kind of asset and does not flush it."
    out.update(points=pts, state=state, standing_days=standing,
               short=f"Water standing about {span}",
               text=f"{lead} {kept} {tail} Rain measured {where}.{note}")
    return out


# --------------------------------------------------------------------------- part 4: location


def location_max(cfg):
    c = cfg["location"]
    return max(c["points_in_dengue_cluster"], c["points_near_dengue_cluster"]) + c["points_in_high_aedes_area"]


def location_part(asset, cfg):
    c = cfg["location"]
    cl = asset.get("cluster")
    inside = bool(cl and cl["inside"])
    near = bool(cl and not cl["inside"] and cl["dist_m"] <= c["near_cluster_m"])
    in_aedes = bool(asset.get("aedes"))
    pts, bits, shorts = 0, [], []
    if inside:
        pts += c["points_in_dengue_cluster"]
        bits.append(f"Inside an active dengue cluster ({cl['locality']}, {cl['cases']} cases).")
        shorts.append("inside a dengue cluster")
    elif near:
        pts += c["points_near_dengue_cluster"]
        bits.append(f"About {int(round(cl['dist_m'], -1))} m from an active dengue cluster ({cl['locality']}, {cl['cases']} cases).")
        shorts.append("next to a dengue cluster")
    if in_aedes:
        pts += c["points_in_high_aedes_area"]
        bits.append("Inside an area where NEA traps found more Aedes aegypti mosquitoes.")
        shorts.append("in a high-Aedes area")
    if not bits:
        bits.append("Not inside or next to a dengue cluster, and not in a high-Aedes area.")
        shorts.append("no cluster or high-Aedes area")
    short = ", ".join(shorts)
    return {"key": "location", "points": pts, "max": location_max(cfg),
            "state": "cluster" if inside else "near" if near else "aedes" if in_aedes else "none",
            "short": short[0].upper() + short[1:], "text": " ".join(bits)}


# --------------------------------------------------------------------------- total


def band_of(score, cfg):
    b = cfg["bands"]
    return "high" if score >= b["high"] else "medium" if score >= b["medium"] else "low"


def total(parts, cfg):
    score = min(100, sum(p["points"] for p in parts))
    return score, band_of(score, cfg)
