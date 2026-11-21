/* Canopy Care: the whole app. Plain JavaScript, no framework, no build step, no network.
 *
 * It reads one snapshot (data/snapshot.js) that the data script writes once a day.
 * Inspection records made here stay in this browser (localStorage) until exported.
 *
 * The score is the sum of four parts. Three come ready-made in the snapshot. The fourth,
 * "inspection", is recomputed here because it changes the moment an inspection is saved.
 * It mirrors inspection_part() in scripts/risk.py; selfTest() checks the two agree.
 */
(function () {
  'use strict';

  var S = window.CANOPY_SNAPSHOT;
  if (!S) {
    document.body.innerHTML = '<p style="padding:1rem;font:16px system-ui">No snapshot found. Run <code>python scripts/refresh.py</code> once, then reload.</p>';
    return;
  }
  var CFG = S.config, META = S.meta, AS_OF = META.as_of;
  var STORE = 'canopy-care/records/v1';
  var BAND = { high: 'Inspect first', medium: 'Inspect this week', low: 'Routine' };
  var PART = { water: 'Holds water', inspection: 'Last inspection', rain: 'Rain and standing water', location: 'Location' };
  var ASSET = {}; S.assets.forEach(function (a) { ASSET[a.id] = a; });
  var SCEN = {}; S.scenarios.forEach(function (s) { SCEN[s.id] = s; });
  var REAL = S.scenarios[0].id;

  var state = {
    scenario: REAL, records: [], memoryOnly: false,
    layers: { clusters: true, aedes: true }, sel: null, selCluster: null, vb: null, filter: 'all',
    day: null,          // which day of the window the map shows: null is the snapshot day, 0 upward replays an earlier one
    keyOpen: null,      // whether the map key is unfolded; decided from the screen width on first use
    flash: null         // the inspection just saved: { id, before, rankBefore }, so the map and the task list can show what changed
  };

  // ------------------------------------------------------------------ small helpers
  function $(sel, el) { return (el || document).querySelector(sel); }
  function $$(sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function dayNum(iso) { var p = iso.slice(0, 10).split('-'); return Date.UTC(+p[0], p[1] - 1, +p[2]) / 864e5; }
  function shortDate(iso) { var p = iso.slice(0, 10).split('-'); return (+p[2]) + ' ' + MONTHS[p[1] - 1]; }
  function longDate(iso) { return shortDate(iso) + ' ' + iso.slice(0, 4); }
  function daysAgoText(n) { return n <= 0 ? 'today' : n === 1 ? '1 day ago' : n + ' days ago'; }
  function sgDate(isoTime) { return new Date(Date.parse(isoTime) + 8 * 36e5).toISOString().slice(0, 10); }  // Singapore calendar date
  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }
  function fmtHours(h) { return h >= 168 ? 'a week or more' : h >= 48 ? 'about ' + Math.round(h / 24) + ' days' : 'about ' + h + ' hours'; }

  // ------------------------------------------------------------------ records kept on this device
  function loadRecords() {
    try {
      var list = JSON.parse(localStorage.getItem(STORE) || '[]');
      state.records = Array.isArray(list) ? list.filter(validRecord) : [];
    } catch (e) { state.records = []; state.memoryOnly = true; }
  }
  function saveRecords() {
    try { localStorage.setItem(STORE, JSON.stringify(state.records)); state.memoryOnly = false; }
    catch (e) { state.memoryOnly = true; }
  }
  function validRecord(r) {
    return r && typeof r.id === 'string' && ASSET[r.asset_id] && typeof r.recorded_at === 'string' && !isNaN(Date.parse(r.recorded_at)) &&
      typeof r.standing_water === 'boolean' && typeof r.larvae === 'boolean' && Array.isArray(r.actions) &&
      r.actions.every(function (a) { return S.actions.indexOf(a) >= 0; });
  }
  function recordsFor(id) {
    return state.records.filter(function (r) { return r.asset_id === id; })
      .sort(function (a, b) { return a.recorded_at < b.recorded_at ? 1 : -1; });
  }

  // ------------------------------------------------------------------ the score
  function removedWater(r) {
    return !r.standing_water || r.actions.some(function (a) { return S.removing_actions.indexOf(a) >= 0; });
  }

  // Newest inspection for an asset: one recorded on this device if there is one, else the snapshot's.
  function lastInspection(a, useDevice) {
    var dev = useDevice ? recordsFor(a.id)[0] : null;
    if (dev) return { rec: dev, days: Math.max(0, dayNum(AS_OF) - dayNum(sgDate(dev.recorded_at))), device: true };
    var snap = a.inspections[0];
    return snap ? { rec: snap, days: dayNum(AS_OF) - dayNum(snap.date), device: false } : { rec: null, days: null, device: false };
  }

  // Mirror of inspection_part() in scripts/risk.py. Keep the two in step.
  function inspectionPart(last, days) {
    var c = CFG.inspection, cycle = CFG.life_cycle.days;
    var max = Math.max(c.points_recent, c.points_due, c.points_overdue, c.points_long_overdue, c.points_never, c.points_follow_up);
    if (!last) return { key: 'inspection', max: max, points: c.points_never, state: 'never', short: 'Never inspected', text: 'No inspection on record.' };
    var larvae = !!last.larvae, f = larvae ? c.day_limits_factor_after_larvae : 1, when = daysAgoText(days), pts, st, short, text;
    if (days <= c.recent_up_to_days * f) {
      pts = c.points_recent; st = 'recent'; short = 'Inspected ' + when; text = 'Inspected ' + when + '.';
    } else if (days <= c.due_up_to_days * f) {
      pts = c.points_due; st = 'due'; short = 'Inspected ' + when + ', due soon';
      text = larvae ? 'Inspected ' + when + '. Larvae were found then, so it comes due after ' + (c.recent_up_to_days * f) + ' days instead of ' + c.recent_up_to_days + '.'
        : 'Inspected ' + when + '. Due again within one mosquito life cycle (about ' + cycle + ' days).';
    } else if (days <= c.overdue_up_to_days * f) {
      pts = c.points_overdue; st = 'overdue'; short = 'Not inspected for ' + days + ' days';
      text = larvae ? 'Not inspected for ' + days + ' days. Larvae were found last time, so it counts as overdue after ' + (c.due_up_to_days * f) + ' days instead of ' + c.due_up_to_days + '.'
        : 'Not inspected for ' + days + ' days, which is longer than one mosquito life cycle (about ' + cycle + ' days).';
    } else {
      pts = c.points_long_overdue; st = 'long_overdue'; short = 'Not inspected for ' + days + ' days';
      text = larvae ? 'Not inspected for ' + days + ' days. Larvae were found last time, so it counts as long overdue after ' + (c.overdue_up_to_days * f) + ' days instead of ' + c.overdue_up_to_days + '.'
        : 'Not inspected for ' + days + ' days, which is more than two mosquito life cycles.';
    }
    if (last.standing_water && !removedWater(last) && c.points_follow_up >= pts) {
      pts = c.points_follow_up; st = 'follow_up'; short = 'Standing water left at last visit';
      text = 'The last inspection (' + when + ') found standing water that was not removed. It needs a return visit.';
    }
    return { key: 'inspection', max: max, points: pts, state: st, short: short, text: text };
  }

  function scoreAsset(a, scen, useDevice) {
    var li = lastInspection(a, useDevice !== false);
    var rain = S.parts[a.rain[scen]];
    // An inspection made on or after the snapshot day that left no standing water overrides the
    // rain estimate. An older record does not: rain has fallen since, and the data script, which
    // cannot see records kept on a device, has already counted that rain.
    if (li.device && li.days === 0 && a.holds_water && a.water_source === 'rain' && removedWater(li.rec)) {
      rain = { key: 'rain', max: rain.max, points: CFG.rain.points_dry, state: 'cleared', station: rain.station,
        short: 'No standing water at this inspection',
        text: 'Left without standing water at the inspection recorded on this device. Rain after the snapshot is not known until the next daily run.' };
    }
    var parts = [S.parts[a.water], inspectionPart(li.rec, li.days), rain, S.parts[a.location]];
    var total = Math.min(100, parts.reduce(function (n, p) { return n + p.points; }, 0));
    return { parts: parts, total: total, band: total >= CFG.bands.high ? 'high' : total >= CFG.bands.medium ? 'medium' : 'low', last: li };
  }

  // Inspection tasks: every asset, ranked. Same order as the data script uses for the printed sheet.
  function rankTasks(scen, useDevice) {
    var list = S.assets.map(function (a) { var s = scoreAsset(a, scen, useDevice); s.asset = a; return s; });
    list.sort(function (x, y) {
      return y.total - x.total || y.parts[1].points - x.parts[1].points || (x.asset.name < y.asset.name ? -1 : x.asset.name > y.asset.name ? 1 : 0);
    });
    list.forEach(function (t, i) { t.rank = i + 1; });
    return list;
  }
  function rankIndex(list) { var m = {}; list.forEach(function (t) { m[t.asset.id] = t; }); return m; }

  // Does the browser reach the same baseline numbers as the data script? Device records are left out.
  function selfTest() {
    var bad = [], n = 0;
    S.scenarios.forEach(function (sc) {
      S.assets.forEach(function (a) {
        var s = scoreAsset(a, sc.id, false);
        n++;
        // ... and the day-by-day replay must end on the same number as the score itself
        if (s.total !== a.baseline_score[sc.id] || s.parts[1].points !== a.inspection_check[0] || s.parts[1].state !== a.inspection_check[1] ||
            a.daily[sc.id][sc.dates.length - 1] !== s.total) {
          bad.push({ asset: a.id, scenario: sc.id, browser: s.total, script: a.baseline_score[sc.id] });
        }
      });
    });
    return { checked: n, mismatches: bad };
  }

  // ------------------------------------------------------------------ shared pieces of markup
  function simBadge(a) { return a.simulated ? ' <span class="sim" title="Not a real object. Added to stand in for small items that open data does not list.">SIMULATED</span>' : ''; }
  function chip(s) { return '<span class="chip b-' + s.band + '"><b>' + s.total + '</b> ' + BAND[s.band] + '</span>'; }
  function sourceOf(key) { return S.sources.filter(function (x) { return x.key === key; })[0]; }
  function srcNote(key) {          // "agency, file of date" for a map layer, or a plain note when it was not available
    var x = sourceOf(key);
    return x && x.snapshot_date ? esc(x.agency) + ', file of ' + longDate(x.source_updated || x.snapshot_date) : 'not available in this snapshot';
  }
  function originText(a) {
    if (a.simulated) return 'Simulated asset. Its position is illustrative and does not describe a real object or place.';
    var src = sourceOf(a.source);
    return 'Real location from ' + esc(src.title) + ' (' + esc(src.agency) + '), snapshot ' + longDate(src.snapshot_date) + '.';
  }
  function whyList(parts, limit) {
    return parts.filter(function (p) { return p.points > 0; }).sort(function (a, b) { return b.points - a.points; }).slice(0, limit || 3)
      .map(function (p) { return '<li>' + esc(p.short) + ' <span class="pts">+' + p.points + '</span></li>'; }).join('');
  }
  function partsHtml(s) {
    var h = '<ul class="parts">';
    s.parts.forEach(function (p) {
      var w = p.max ? Math.round(100 * p.points / p.max) : 0, tag = '';
      // The largest part rests on the inspection history, which in this demo is made up. Say so right here.
      if (p.key === 'inspection') tag = s.last && s.last.device ? ' <span class="tag dev">recorded on this device</span>' : ' <span class="tag">simulated history</span>';
      h += '<li><div class="ph"><span class="pn">' + PART[p.key] + tag + '</span><span class="pv">+' + p.points + ' <small>of ' + p.max + '</small></span></div>' +
        '<div class="meter" role="img" aria-label="' + p.points + ' of ' + p.max + ' points"><i style="width:' + w + '%"></i></div>' +
        '<p>' + esc(p.text) + '</p></li>';
    });
    return h + '</ul><p class="sum">Total <b>' + s.total + '</b> of 100: ' + BAND[s.band].toLowerCase() +
      '. This ranks inspections. It does not predict dengue cases.</p>';
  }
  function historyHtml(a) {
    var rows = recordsFor(a.id).map(function (r) { return { date: sgDate(r.recorded_at), r: r, dev: true }; })
      .concat(a.inspections.map(function (r) { return { date: r.date, r: r, dev: false }; }));
    if (!rows.length) return '<p class="muted">No inspection on record.</p>';
    var h = '<table class="hist"><thead><tr><th>Date</th><th>Found</th><th>Action</th><th>Note</th></tr></thead><tbody>';
    rows.forEach(function (x) {
      var r = x.r, found = r.standing_water ? (r.larvae ? 'Standing water, larvae' : 'Standing water') : 'No standing water';
      h += '<tr><td>' + shortDate(x.date) + (x.dev ? '<br><span class="tag dev">this device</span>' : '<br><span class="tag">simulated</span>') + '</td><td>' + found +
        '</td><td>' + esc(r.actions.join(', ') || 'none') + '</td><td>' + esc(r.note || '') + '</td></tr>';
    });
    return h + '</tbody></table>';
  }
  function baseUrl() {
    var b = META.public_url || location.href.split('#')[0].replace(/[^\/]*$/, '');
    return b.charAt(b.length - 1) === '/' ? b : b + '/';
  }
  function inspectUrl(id) { return baseUrl() + 'index.html#/inspect/' + encodeURIComponent(id); }

  // One asset's score on each day of the window, as a small line. The day the map is showing is
  // marked. If an inspection was saved on this device, one more point shows where that left it.
  function sparkHtml(a) {
    var sc = SCEN[state.scenario], vals = a.daily[sc.id], n = vals.length, cur = state.day == null ? n - 1 : state.day;
    var live = scoreAsset(a, sc.id), extra = live.last.device ? live.total : null;
    var W = 330, H = 104, L = 24, R = extra == null ? 14 : 46, T = 16, B = 20, pw = W - L - R, ph = H - T - B, pts = '', dots = '', i, b = CFG.bands;
    function X(i) { return L + pw * i / (n - 1); }
    function Y(v) { return T + ph * (1 - v / 100); }
    var h = '<svg class="spark" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Score on each of the ' + n + ' days: ' + vals.join(', ') + (extra == null ? '' : '. After the inspection saved here: ' + extra) + '">';
    [0, b.medium, b.high, 100].forEach(function (g) {
      h += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(g) + '" y2="' + Y(g) + '" class="' + (g === 0 ? 'axis' : 'grid') + '"/><text x="' + (L - 4) + '" y="' + (Y(g) + 3.5) + '" class="tick" text-anchor="end">' + g + '</text>';
    });
    for (i = 0; i < n; i++) {
      pts += (i ? ' ' : '') + X(i).toFixed(1) + ',' + Y(vals[i]).toFixed(1);
      dots += '<circle cx="' + X(i).toFixed(1) + '" cy="' + Y(vals[i]).toFixed(1) + '" r="' + (i === cur ? 4.5 : 2) + '" class="' + (i === cur ? 'now' : 'pt') + '"><title>After ' + shortDate(sc.dates[i]) + ': ' + vals[i] + '</title></circle>';
    }
    h += '<polyline points="' + pts + '" class="ln"/>' + dots +
      '<text x="' + X(cur).toFixed(1) + '" y="' + (Y(vals[cur]) - 8).toFixed(1) + '" class="val" text-anchor="' + (cur > n - 3 ? 'end' : cur < 2 ? 'start' : 'middle') + '">' + vals[cur] + '</text>' +
      '<text x="' + L + '" y="' + (H - 5) + '" class="tick">' + shortDate(sc.dates[0]) + '</text><text x="' + X(n - 1) + '" y="' + (H - 5) + '" class="tick" text-anchor="end">' + shortDate(sc.dates[n - 1]) + '</text>';
    if (extra != null) {
      h += '<line x1="' + X(n - 1) + '" y1="' + Y(vals[n - 1]) + '" x2="' + (W - 30) + '" y2="' + Y(extra) + '" class="ln dash"/><circle cx="' + (W - 30) + '" cy="' + Y(extra) + '" r="4.5" class="dev"/>' +
        '<text x="' + (W - 22) + '" y="' + (Y(extra) + 4) + '" class="val">' + extra + '</text><text x="' + (W - 30) + '" y="' + (H - 5) + '" class="tick" text-anchor="middle">now</text>';
    }
    return h + '</svg><p class="muted">The score the data script would have given after each day: rain up to that day, the inspections made by then (simulated), and today\'s clusters. ' +
      'NEA publishes no history of clusters.' + (extra == null ? '' : ' The last point is after the inspection saved on this device.') + '</p>';
  }
  // The four parts on a replayed day. Two never change (what the asset is, where it is); the other two come from the snapshot's day-by-day table.
  function dayPartsHtml(a, i) {
    var st = dayStates(a, i), rows = [[PART.water, S.parts[a.water].points, S.parts[a.water].max, S.parts[a.water].short],
      [PART.inspection + ' <span class="tag">simulated history</span>', st.inspection[0], inspectionPart(null, null).max, st.inspection[1]],
      [PART.rain, st.rain[0], S.parts[a.rain[state.scenario]].max, st.rain[1]],
      [PART.location + ' <span class="tag">today\'s clusters</span>', S.parts[a.location].points, S.parts[a.location].max, S.parts[a.location].short]];
    return '<ul class="parts">' + rows.map(function (r) {
      return '<li><div class="ph"><span class="pn">' + r[0] + '</span><span class="pv">+' + r[1] + ' <small>of ' + r[2] + '</small></span></div>' +
        '<div class="meter" role="img" aria-label="' + r[1] + ' of ' + r[2] + ' points"><i style="width:' + Math.round(100 * r[1] / r[2]) + '%"></i></div><p>' + esc(r[3]) + '</p></li>';
    }).join('') + '</ul>';
  }

  function assetDetail(a, where) {
    var s = scoreAsset(a, state.scenario), t = S.types[a.type], sc = SCEN[state.scenario];
    var replay = where === 'map' && state.day != null, list = replay ? shownList() : rankTasks(state.scenario);
    var rank = rankIndex(list)[a.id].rank, shown = replay ? rankIndex(list)[a.id] : s;
    var basis = a.own_properties ? 'set for this simulated asset' : 'assumed for this asset type, not measured';
    var h = '<article class="ad"><h2>' + esc(a.name) + simBadge(a) + '</h2>' +
      '<p class="meta">' + esc(t.label) + ' · rank ' + rank + ' of ' + S.assets.length + (replay ? ' after ' + shortDate(sc.dates[state.day]) : '') + '</p>' +
      '<p>' + chip(shown) + (replay ? ' <span class="muted">today ' + s.total + '</span>' : '') + '</p>' +
      '<p class="acts"><a class="btn pri" href="#/inspect/' + esc(a.id) + '">Inspect now</a>' +
      (where === 'map' ? '' : ' <a class="btn" href="#/map/' + esc(a.id) + '">Show on map</a>') +
      ' <button class="btn" data-qr="' + esc(a.id) + '">QR code</button></p><div class="qrbox" hidden></div>' +
      (replay ? '<h3>The score after ' + shortDate(sc.dates[state.day]) + '</h3>' + dayPartsHtml(a, state.day) +
        '<p class="sum">Total <b>' + shown.total + '</b> of 100 on that day. <button class="link" data-day="today">Back to today</button></p>'
        : '<h3>Why this score</h3>' + partsHtml(s)) +
      (where === 'map' ? '<h3>Over the ' + sc.dates.length + ' days</h3>' + sparkHtml(a) : '') +
      '<h3>About this asset</h3><dl class="kv">' +
      '<dt>Origin</dt><dd>' + originText(a) + (a.location_note ? ' ' + esc(a.location_note) : '') + '</dd>' +
      '<dt>Holds water</dt><dd>' + (a.holds_water ? 'Yes' : 'No') + ' <span class="muted">(' + basis + ')</span></dd>' +
      (a.holds_water ? '<dt>Drain time</dt><dd>' + fmtHours(a.drain_time_h) + ' <span class="muted">(' + basis + ')</span></dd>' : '') +
      '<dt>Water comes from</dt><dd>' + ({ rain: 'Rain', watered: 'Watering by people', stored: 'Stored water' }[a.water_source]) +
      (a.flushable ? '. A heavy storm flushes it through.' : '') + '</dd>' +
      '<dt>Look for</dt><dd>' + esc(t.look_for) + '</dd>' +
      (a.note ? '<dt>Note</dt><dd>' + esc(a.note) + '</dd>' : '') +
      '</dl><h3>Inspection history</h3>' + historyHtml(a) + '</article>';
    return h;
  }

  // ------------------------------------------------------------------ map
  var mapEl = null;
  var FAR = 5.5, NEAR = 2.6;        // metres per pixel: beyond FAR minor names and small numbers are dropped, within NEAR every marker shows its number
  var marks = [], fixedDiscs = [], areaLabels = [], drawnK = null, areaAnchors = null, playTimer = null;
  var MOTION = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  function still() { return !!(MOTION && MOTION.matches); }      // the viewer asked for less motion: change things at once, do not glide
  function mapSize() { var r = mapEl.getBoundingClientRect(); return { w: Math.max(50, r.width), h: Math.max(50, r.height), left: r.left, top: r.top }; }
  // The map opens on the neighbourhood itself. The margin drawn around it is context, reached by zooming out.
  function focusBox() {
    var f = S.map.focus || [0, 0, S.map.w, S.map.h], pad = 0.03 * Math.max(f[2] - f[0], f[3] - f[1]);
    return [f[0] - pad, f[1] - pad, f[2] + pad, f[3] + pad];
  }
  function fitScale() { var z = mapSize(), b = focusBox(); return Math.max((b[2] - b[0]) / z.w, (b[3] - b[1]) / z.h); }   // metres per pixel when the neighbourhood fills the box
  function wholeScale() { var z = mapSize(); return Math.max(fitScale(), S.map.w / z.w, S.map.h / z.h); }               // and when everything drawn fits

  // ---- which day the map shows.
  // state.day is null for the snapshot day, with this device's inspections counted. A number
  // replays an earlier day of the 14-day window from scores the data script worked out in advance:
  // the browser looks them up and never recomputes them.
  function lastDay() { return SCEN[state.scenario].dates.length - 1; }
  function bandOf(total) { return total >= CFG.bands.high ? 'high' : total >= CFG.bands.medium ? 'medium' : 'low'; }
  function shownList() {
    if (state.day == null) return rankTasks(state.scenario);
    var list = S.assets.map(function (a) { var v = a.daily[state.scenario][state.day]; return { asset: a, total: v, band: bandOf(v) }; });
    list.sort(function (x, y) { return y.total - x.total || (x.asset.name < y.asset.name ? -1 : x.asset.name > y.asset.name ? 1 : 0); });
    list.forEach(function (t, i) { t.rank = i + 1; });
    return list;
  }
  function dayStates(a, i) {       // the two parts that change from day to day, as [points, reason]
    var D = S.daily;
    return { inspection: D.states[D.series[a.daily_insp][i]], rain: D.states[D.series[a.daily_rain[state.scenario]][i]] };
  }

  // ---- markers: size and colour both follow the score, on one scale
  function radius(total) { return 4.5 + 8 * total / 100; }       // pixels on screen: 4.5 at a score of 0, 12.5 at 100
  function shade(total) {                                         // five steps of one colour; the band limits sit on step edges
    var m = CFG.bands.medium, h = CFG.bands.high;
    return total >= (h + 100) / 2 ? 5 : total >= h ? 4 : total >= m ? 3 : total >= m / 2 ? 2 : 1;
  }
  function markClass(v, id) { return 'mk c' + shade(v) + ' b-' + bandOf(v) + (radius(v) >= 8 ? ' n-in' : ' n-out') + (state.sel === id ? ' on' : ''); }
  function markTitle(a, v) { return a.name + (a.simulated ? ' (simulated)' : '') + ': ' + v + ', ' + BAND[bandOf(v)]; }
  function markerHtml(t) {
    var a = t.asset, v = t.total, r = radius(v);
    var shape = a.simulated ? '<rect x="-9" y="-9" width="18" height="18" transform="rotate(45)" class="sh"/>' : '<circle r="10" class="sh"/>';
    return '<g class="' + markClass(v, a.id) + '" data-id="' + esc(a.id) + '" data-v="' + v + '"><title>' + esc(markTitle(a, v)) + '</title>' +
      '<path class="tether" d="M0,0"/><circle class="spot" r="2"/><circle r="15" class="hit"/>' +
      '<g class="mb" transform="scale(' + (r / 10).toFixed(3) + ')">' + shape + '</g>' +
      (state.sel === a.id ? '<circle class="ring" r="' + (r + 6).toFixed(1) + '"/>' : '') +
      '<text y="3.6"' + (r >= 8 ? '' : ' x="' + (r + 4).toFixed(1) + '"') + '>' + v + '</text></g>';
  }
  function collectMarks() {
    marks = $$('.mk', mapEl).map(function (g) {
      var a = ASSET[g.getAttribute('data-id')], v = +g.getAttribute('data-v'), top = v;
      a.daily[state.scenario].forEach(function (d) { if (d > top) top = d; });
      return { a: a, el: g, mb: g.querySelector('.mb'), v: v, s: radius(v) / 10, rmax: radius(top) * (a.simulated ? 1.15 : 1), dx: 0, dy: 0, raf: 0 };   // a diamond's points reach further than a circle's edge
    });
    marks.sort(function (p, q) { return p.a.id < q.a.id ? -1 : 1; });      // a fixed order, so the nudging below comes out the same every time
    drawnK = null;
  }
  // Change one marker to a new score. With motion allowed it grows or shrinks over half a second
  // and the fill fades (a CSS transition); with reduced motion it simply changes.
  function paintMark(m, v, glide) {
    var r = radius(v), to = r / 10, g = m.el, tx = g.querySelector('text'), ring = g.querySelector('.ring');
    m.v = v;
    g.setAttribute('class', markClass(v, m.a.id) + (g.classList.contains('moved') ? ' moved' : ''));
    g.querySelector('title').textContent = markTitle(m.a, v);
    tx.textContent = v;
    if (r >= 8) tx.removeAttribute('x'); else tx.setAttribute('x', (r + 4).toFixed(1));
    if (m.raf) { cancelAnimationFrame(m.raf); m.raf = 0; }
    function set(s) { m.s = s; m.mb.setAttribute('transform', 'scale(' + s.toFixed(3) + ')'); if (ring) ring.setAttribute('r', (s * 10 + 6).toFixed(1)); }
    if (!glide || still() || document.hidden || Math.abs(to - m.s) < 0.01) { set(to); return; }   // a hidden tab runs no animation frames
    var from = m.s, t0 = null;
    function step(ts) {
      if (t0 == null) t0 = ts;
      var p = Math.min(1, (ts - t0) / 500), e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
      set(from + (to - from) * e);
      m.raf = p < 1 ? requestAnimationFrame(step) : 0;
    }
    m.raf = requestAnimationFrame(step);
  }

  // Nudge markers apart on screen until none covers another, and off the subzone names, the
  // cluster badges and the rain gauges. A marker's size here is the largest it reaches on any
  // day of the window, so nothing shifts while the days play. A marker that had to move keeps a
  // thin line back to a dot on its true spot. Nothing in the data moves: only the drawing.
  function declutter(k) {
    var P = marks.map(function (m) { return { m: m, ox: m.a.x / k, oy: m.a.y / k, x: m.a.x / k, y: m.a.y / k, r: m.rmax + 1.5 }; });
    var cap = 22, it, i, j, a, b, dx, dy, d, need, ux, uy, push, busy;
    function away(p, cx, cy, hw, hh) {         // push a disc out of a box (a round obstacle is a box of no size)
      var px = p.x - cx, py = p.y - cy, ex = hw + p.r, ey = hh + p.r, ax = Math.abs(px), ay = Math.abs(py), len;
      if (ax >= ex || ay >= ey) return false;
      if (!hw && !hh) {
        len = Math.sqrt(px * px + py * py);
        if (len >= p.r) return false;
        if (len < 0.01) { px = 0; py = -1; len = 1; }
        p.x = cx + px / len * p.r; p.y = cy + py / len * p.r;
      } else if (ey - ay <= ex - ax) p.y = cy + (py >= 0 ? ey : -ey);
      else p.x = cx + (px >= 0 ? ex : -ex);
      return true;
    }
    for (it = 0; it < 60; it++) {
      busy = false;
      for (i = 0; i < P.length; i++) for (j = i + 1; j < P.length; j++) {
        a = P[i]; b = P[j]; dx = b.x - a.x; dy = b.y - a.y; d = Math.sqrt(dx * dx + dy * dy); need = a.r + b.r;
        if (d >= need) continue;
        if (d < 0.01) { d = 0; ux = Math.cos(i * 2.4 + j); uy = Math.sin(i * 2.4 + j); } else { ux = dx / d; uy = dy / d; }
        push = (need - d) / 2 + 0.05;
        a.x -= ux * push; a.y -= uy * push; b.x += ux * push; b.y += uy * push; busy = true;
      }
      P.forEach(function (p) {
        areaLabels.forEach(function (L) { if (away(p, L.x / k, L.y / k, L.hw, L.hh)) busy = true; });
        fixedDiscs.forEach(function (f) { var keep = p.r; p.r += f.r; if (away(p, f.x / k + (f.ox || 0), f.y / k, 0, 0)) busy = true; p.r = keep; });
        dx = p.x - p.ox; dy = p.y - p.oy; d = Math.sqrt(dx * dx + dy * dy);
        if (d > cap) { p.x = p.ox + dx / d * cap; p.y = p.oy + dy / d * cap; }
      });
      if (!busy) break;
    }
    P.forEach(function (p) {
      var m = p.m, far = false;
      m.dx = p.x - p.ox; m.dy = p.y - p.oy;
      far = Math.sqrt(m.dx * m.dx + m.dy * m.dy) > 3.5;
      m.el.classList.toggle('moved', far);
      m.el.querySelector('.tether').setAttribute('d', far ? 'M0,0L' + (-m.dx).toFixed(1) + ',' + (-m.dy).toFixed(1) : 'M0,0');
      m.el.querySelector('.spot').setAttribute('transform', 'translate(' + (-m.dx).toFixed(1) + ' ' + (-m.dy).toFixed(1) + ')');
    });
  }

  // ---- names. Subzone names sit on free ground and markers are kept off them. A minor name
  // (a park, a neighbouring subzone) that a marker would cover is hidden until there is room.
  // Sizes are estimated from the text length, because a hidden label cannot be measured.
  function labelHtml(x, y, text, cls, charW, minor) {
    return '<g class="fix lab" data-x="' + x + '" data-y="' + y + '" data-hw="' + Math.round(text.length * charW / 2) + '"' + (minor ? ' data-minor="1"' : '') +
      '><text class="lb ' + cls + '" y="4">' + esc(text) + '</text></g>';
  }
  function boxGap(o, x, y, hw, hh, k) {      // distance in pixels from a label box to a point, 0 when inside
    var dx = Math.max(Math.abs(o.x - x) - hw * k, 0), dy = Math.max(Math.abs(o.y - y) - hh * k, 0);
    return Math.sqrt(dx * dx + dy * dy) / k;
  }
  function hideCoveredLabels(k, far) {
    var shown = areaLabels.map(function (L) { return { x: L.x, y: L.y, hw: L.hw }; }), z = mapSize(), v = state.vb;
    var discs = fixedDiscs.map(function (f) { return { x: f.x + (f.ox || 0) * k, y: f.y, r: f.r }; })
      .concat(marks.map(function (m) { return { x: m.a.x + m.dx * k, y: m.a.y + m.dy * k, r: m.rmax + 2 }; }));
    // The key and the locator sit on top of the map: a name under either is hidden, not left half-covered.
    var panels = $$('.mapkey, .locator').map(function (el) { var r = el.getBoundingClientRect(); return [r.left - z.left - 4, r.top - z.top - 4, r.right - z.left + 4, r.bottom - z.top + 4]; });
    $$('.lab[data-minor]', mapEl).forEach(function (g) {
      var x = +g.getAttribute('data-x'), y = +g.getAttribute('data-y'), hw = +g.getAttribute('data-hw'), hit = false, i, o;
      if (far) return;                                                     // minor names are not drawn at this zoom
      var sx = (x - v.x) / k, sy = (y - v.y) / k;                          // where the name sits on screen
      panels.forEach(function (p) { if (sx + hw > p[0] && sx - hw < p[2] && sy + 8 > p[1] && sy - 8 < p[3]) hit = true; });
      for (i = 0; i < discs.length && !hit; i++) { o = discs[i]; hit = boxGap(o, x, y, hw, 7, k) < o.r; }
      for (i = 0; i < shown.length && !hit; i++) { o = shown[i]; hit = Math.abs(o.x - x) < (hw + o.hw + 6) * k && Math.abs(o.y - y) < 16 * k; }
      g.style.visibility = hit ? 'hidden' : '';
      if (!hit) shown.push({ x: x, y: y, hw: hw });
    });
  }
  // Each subzone name goes to the spot inside its own outline that is furthest from the markers.
  // Worked out once per page load, at a typical laptop scale: the assets do not move.
  function findAreaAnchors() {
    var pt = mapEl.createSVGPoint ? mapEl.createSVGPoint() : null, paths = $$('path.area', mapEl), k = 4.5, placed = [], fixed = [];
    S.assets.forEach(function (a) { fixed.push({ x: a.x, y: a.y, r: 13 }); });
    S.map.clusters.forEach(function (c) { fixed.push({ x: c.x, y: c.y, r: 14 }); });
    (S.map.stations || []).forEach(function (s) { fixed.push({ x: s.x, y: s.y, r: 12 }); });
    function inside(p, x, y) { pt.x = x; pt.y = y; return p.isPointInFill(pt); }
    return S.map.frame.map(function (f, i) {
      var p = paths[i], hw = f.name.length * 7.8 / 2, best = null, b, n = 28, ix, iy, x, y, gap;
      if (!pt || !p || !p.isPointInFill) return null;
      b = p.getBBox();
      for (ix = 1; ix < n; ix++) for (iy = 1; iy < n; iy++) {
        x = b.x + b.width * ix / n; y = b.y + b.height * iy / n;
        if (!inside(p, x, y) || !inside(p, x - (hw + 8) * k, y) || !inside(p, x + (hw + 8) * k, y)) continue;
        gap = 1e9;
        fixed.forEach(function (o) { gap = Math.min(gap, boxGap(o, x, y, hw, 8, k) - o.r); });
        placed.forEach(function (o) { if (Math.abs(o.x - x) < (hw + o.hw + 10) * k && Math.abs(o.y - y) < 22 * k) gap = -1e9; });
        if (!best || gap > best.gap) best = { gap: gap, x: Math.round(x), y: Math.round(y), hw: hw };
      }
      if (best) placed.push(best);
      return best;
    });
  }

  function applyView() {
    var z = mapSize(), v = state.vb, k = v.k, far = k > FAR;
    v.x = Math.min(Math.max(v.x, -0.25 * z.w * k), S.map.w - 0.75 * z.w * k);
    v.y = Math.min(Math.max(v.y, -0.25 * z.h * k), S.map.h - 0.75 * z.h * k);
    mapEl.setAttribute('viewBox', v.x + ' ' + v.y + ' ' + z.w * k + ' ' + z.h * k);
    mapEl.classList.toggle('far', far);          // zoomed far out: drop the minor names and the numbers on all but the most urgent markers
    mapEl.classList.toggle('near', k < NEAR);    // zoomed well in: small markers show their number too
    if (drawnK !== k) { drawnK = k; declutter(k); hideCoveredLabels(k, far); }
    $$('.fix', mapEl).forEach(function (g) {     // keep names and badges the same size on screen
      g.setAttribute('transform', 'translate(' + g.getAttribute('data-x') + ' ' + g.getAttribute('data-y') + ') scale(' + k + ')');
    });
    marks.forEach(function (m) { m.el.setAttribute('transform', 'translate(' + (m.a.x + m.dx * k) + ' ' + (m.a.y + m.dy * k) + ') scale(' + k + ')'); });
  }
  function resetView() {
    var z = mapSize(), b = focusBox(), k = fitScale();
    state.vb = { k: k, x: (b[0] + b[2] - z.w * k) / 2, y: (b[1] + b[3] - z.h * k) / 2, fit: true, w: z.w, h: z.h };
  }
  // When the window changes size: stay fitted if the neighbourhood was showing, otherwise keep the same centre.
  function onResize() {
    var z = mapSize(), v = state.vb;
    if (v.fit) { resetView(); } else { v.x += (v.w - z.w) * v.k / 2; v.y += (v.h - z.h) * v.k / 2; v.w = z.w; v.h = z.h; v.k = Math.min(v.k, wholeScale()); }
    applyView();
    drawTimeline();
  }
  function zoomAt(factor, px, py) {
    var z = mapSize(), v = state.vb, k2 = Math.min(wholeScale(), Math.max(wholeScale() / 14, v.k * factor));
    if (px == null) { px = z.w / 2; py = z.h / 2; }
    v.x += px * (v.k - k2); v.y += py * (v.k - k2); v.k = k2; v.fit = false;
    applyView();
  }
  function centreOn(a) {
    var z = mapSize(), v = state.vb;
    v.k = Math.min(v.k, wholeScale() / 2.2); v.fit = false;
    v.x = a.x - z.w * v.k / 2; v.y = a.y - z.h * v.k / 2;
  }
  // The marker nearest to a point on screen. Used for taps, so that every marker can be chosen
  // however the browser stacks them.
  function pickMarker(px, py) {
    var k = state.vb.k, best = null, bd = 1e9;
    marks.forEach(function (m) {
      var dx = px - ((m.a.x - state.vb.x) / k + m.dx), dy = py - ((m.a.y - state.vb.y) / k + m.dy), d = Math.sqrt(dx * dx + dy * dy);
      if (d < Math.max(m.s * 10 + 5, 14) && d < bd) { bd = d; best = m; }
    });
    return best;
  }

  function mapSvg() {
    var m = S.map, h = '';
    h += '<rect x="-2000" y="-2000" width="' + (m.w + 4000) + '" height="' + (m.h + 4000) + '" class="land"/>';
    h += '<path d="' + m.context + '" class="ctx"/>';
    m.frame.forEach(function (f) { h += '<path d="' + f.d + '" class="area"/>'; });
    h += '<path d="' + m.parks + '" class="park"/><path d="' + m.water + '" class="water"/><path d="' + m.roads + '" class="road"/>';
    if (state.layers.aedes) h += '<path d="' + m.aedes + '" class="aedes"/>';
    if (state.layers.clusters) m.clusters.forEach(function (c, i) {
      h += '<path d="' + c.d + '" class="cl' + (state.selCluster === i ? ' on' : '') + '" data-cl="' + i + '"><title>Dengue cluster: ' + esc(c.locality) + ', ' + c.cases + ' cases</title></path>';
    });
    m.frame.forEach(function (f) { h += '<path d="' + f.d + '" class="edge"/>'; });
    areaLabels = []; fixedDiscs = [];
    m.frame.forEach(function (f, i) {
      var at = (areaAnchors && areaAnchors[i]) || f, t = f.name.toUpperCase();
      areaLabels.push({ x: at.x, y: at.y, hw: t.length * 7.8 / 2 + 2, hh: 8 });
      h += labelHtml(at.x, at.y, t, 'areal', 7.8);
    });
    m.park_labels.forEach(function (l) { h += labelHtml(l.x, l.y, l.t, 'parkl', 5.6, true); });
    m.context_labels.forEach(function (l) { h += labelHtml(l.x, l.y, l.t.toUpperCase(), 'ctxl', 6.7, true); });
    if (state.layers.clusters) m.clusters.forEach(function (c, i) {
      fixedDiscs.push({ x: c.x, y: c.y, r: 12 });
      h += '<g class="fix clb" data-cl="' + i + '" data-x="' + c.x + '" data-y="' + c.y + '"><title>Dengue cluster: ' + esc(c.locality) + ', ' + c.cases + ' cases</title><circle r="11"/><text y="4">' + c.cases + '</text></g>';
    });
    SCEN[state.scenario].stations.forEach(function (st) {
      fixedDiscs.push({ x: st.x, y: st.y, r: 9 }, { x: st.x, y: st.y, r: 11, ox: 22 });      // the triangle, and its short label beside it
      h += '<g class="fix stn" data-x="' + st.x + '" data-y="' + st.y + '"><title>Rain gauge ' + esc(st.id + ' ' + st.name) + '</title><path d="M0,-8 7,5 -7,5z"/><text x="10" y="4" class="lb">' + esc(st.id) + '</text></g>';
    });
    // draw low priority first so the urgent ones end up on top
    shownList().slice().reverse().forEach(function (t) { h += markerHtml(t); });
    return h;
  }
  function drawMap() { mapEl.innerHTML = mapSvg(); collectMarks(); }

  function mapPanel() {
    if (state.sel && ASSET[state.sel]) return '<button class="x" data-close aria-label="Close">×</button>' + assetDetail(ASSET[state.sel], 'map');
    if (state.selCluster != null) {
      var c = S.map.clusters[state.selCluster], src = sourceOf('dengue_clusters');
      var h = '<button class="x" data-close aria-label="Close">×</button><article class="ad"><h2>Dengue cluster</h2><p class="meta">' + esc(c.locality) + '</p>' +
        '<p><b>' + c.cases + '</b> reported cases. Source: ' + esc(src.title) + ', ' + esc(src.agency) + ', snapshot ' + longDate(src.snapshot_date) + '.</p>';
      if (c.homes || c.public_places || c.construction_sites) {
        h += '<h3>Breeding habitats NEA found here</h3><dl class="kv">' +
          (c.homes ? '<dt>Homes</dt><dd>' + esc(c.homes) + '</dd>' : '') +
          (c.public_places ? '<dt>Public places</dt><dd>' + esc(c.public_places) + '</dd>' : '') +
          (c.construction_sites ? '<dt>Construction sites</dt><dd>' + esc(c.construction_sites) + '</dd>' : '') +
          '</dl><p class="muted">Quoted from the NEA dataset. What the items share is standing water left in place: containers, trays and drains, and plants too where they hold water.</p>';
      } else {
        h += '<p class="muted">NEA lists breeding habitats only for some clusters. None is listed for this one.</p>';
      }
      return h + '<p class="muted">An asset inside a cluster gets +' + CFG.location.points_in_dengue_cluster + ', and one within ' + CFG.location.near_cluster_m +
        ' m gets +' + CFG.location.points_near_dengue_cluster + '. A cluster is where cases were reported, not a forecast.</p></article>';
    }
    var bands = CFG.bands, dc = sourceOf('dengue_clusters'), ae = sourceOf('high_aedes_areas'), pk = sourceOf('park_polygons'), sz = sourceOf('subzone_boundaries');
    return '<article class="ad"><h2>' + esc(META.neighbourhood) + '</h2>' +
      '<p class="meta">' + esc(META.subzones.join(', ')) + '</p>' +
      '<p>' + S.assets.length + ' assets: ' + S.assets.filter(function (a) { return !a.simulated; }).length + ' real locations and ' +
      S.assets.filter(function (a) { return a.simulated; }).length + ' simulated. Tap one to see what makes up its score.</p>' +
      '<h3>Reading the markers</h3>' +
      '<p>A marker grows and darkens with its inspection priority, a score out of 100. ' + BAND.high + ' is ' + bands.high + ' or more, ' + BAND.medium.toLowerCase() + ' is ' + bands.medium + ' to ' + (bands.high - 1) +
      ', and ' + BAND.low.toLowerCase() + ' is anything lower. Small pale markers have nothing due now. That is not the same as safe, and no marker predicts dengue.</p>' +
      '<p class="muted">Circles are real places and diamonds are simulated assets. Small markers show their number once you zoom in.</p>' +
      '<h3>The strip under the map</h3>' +
      '<p>It shows the rain of each day in the window. Drag the day marker, or press Play, and the map shows the scores as they stood after that day\'s rain. ' +
      'Storm drains drop after a storm heavy enough to flush them, then climb again while water stands.</p>' +
      '<h3>Where each layer comes from</h3><ul class="legend">' +
      '<li><span class="sw cl"></span> Active dengue clusters, with case counts <span class="muted">' + esc(dc.agency) + ', ' + longDate(dc.snapshot_date) + '</span></li>' +
      '<li><span class="sw ae"></span> High-Aedes areas <span class="muted">' + esc(ae.agency) + ', file of ' + longDate(ae.source_updated || ae.snapshot_date) + '</span></li>' +
      '<li><span class="sw pk"></span> Parks <span class="muted">' + esc(pk.agency) + ', ' + longDate(pk.snapshot_date) + '</span></li>' +
      '<li><span class="sw wt"></span> Canals and water <span class="muted">' + srcNote('waterbodies') + '</span></li>' +
      '<li><span class="sw rd"></span> Major roads <span class="muted">' + srcNote('road_lines') + '</span></li>' +
      '<li><svg width="22" height="16"><path d="M11,2 18,14 4,14z" fill="#0b0b0b"/></svg> Rain gauge <span class="muted">' + esc(sourceOf('rainfall').agency) + ', rain to ' + longDate(SCEN[REAL].to) + '</span></li>' +
      '<li><span class="sw is"></span> Outline of Singapore and subzone lines <span class="muted">' + (sz ? esc(sz.agency) + ', file of ' + longDate(sz.source_updated || sz.snapshot_date) : 'not available') + '</span></li></ul>' +
      '<p class="muted">Drawn from the open data itself. No map tiles, no network.</p></article>';
  }

  // The key stays on the map whatever the side panel is showing, so every mark is explained at all times.
  function keyCounts() { var n = { high: 0, medium: 0, low: 0 }; shownList().forEach(function (t) { n[t.band]++; }); return n; }
  function mapKey() {
    var n = keyCounts(), b = CFG.bands, sw = '', i;
    for (i = 1; i <= 5; i++) sw += '<svg width="27" height="27" aria-hidden="true"><circle cx="13.5" cy="13.5" r="' + [5, 6.8, 8.4, 10.2, 12][i - 1] + '" class="lg c' + i + '"/></svg>';
    return '<summary>Key</summary><div class="keybody">' +
      '<p class="kt">Inspection priority, 0 to 100</p>' +
      '<div class="scale" role="img" aria-label="Markers grow and darken as the inspection priority rises">' + sw + '</div>' +
      '<div class="bands"><span>' + BAND.low + '<br><small>under ' + b.medium + '</small><b id="kn-low">' + n.low + '</b></span>' +
      '<span>This week<br><small>' + b.medium + ' to ' + (b.high - 1) + '</small><b id="kn-medium">' + n.medium + '</b></span>' +
      '<span>' + BAND.high + '<br><small>' + b.high + ' and over</small><b id="kn-high">' + n.high + '</b></span></div>' +
      '<ul class="legend">' +
      '<li><svg width="22" height="22" aria-hidden="true"><circle cx="11" cy="11" r="6.5" class="lg plain"/></svg> Real place</li>' +
      '<li><svg width="22" height="22" aria-hidden="true"><rect x="5.5" y="5.5" width="11" height="11" transform="rotate(45 11 11)" class="lg plain"/></svg> Simulated asset</li>' +
      '<li><svg width="22" height="22" aria-hidden="true"><path d="M4,17L13,8" class="tether"/><circle cx="4" cy="17" r="2" class="spot"/><circle cx="14" cy="7" r="5" class="lg plain"/></svg> Moved aside to stay clickable. The dot is its true spot</li>' +
      '<li><label><input type="checkbox" data-layer="clusters"' + (state.layers.clusters ? ' checked' : '') + '> <span class="sw cl"></span> Active dengue cluster. The number is its cases</label></li>' +
      '<li><label><input type="checkbox" data-layer="aedes"' + (state.layers.aedes ? ' checked' : '') + '> <span class="sw ae"></span> Area with more Aedes mosquitoes in NEA traps</label></li>' +
      '<li><svg width="22" height="22" aria-hidden="true"><path d="M11,4 18,17 4,17z" fill="#0b0b0b"/></svg> Rain gauge (weather station)</li></ul>' +
      '<p class="kf">A priority for inspection. Not a forecast.</p></div>';
  }
  function updateKeyCounts() {
    var n = keyCounts();
    ['low', 'medium', 'high'].forEach(function (b) { var el = $('#kn-' + b); if (el) el.textContent = n[b]; });
  }

  // A small outline of Singapore, drawn from the same subzone file, with the neighbourhood marked.
  function locatorHtml() {
    var L = S.map.locator;
    if (!L || !L.d) return '';
    var b = L.box, cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2;
    return '<figure class="locator"><svg viewBox="0 0 ' + L.w + ' ' + L.h + '" role="img" aria-label="Outline of Singapore. ' + esc(META.neighbourhood) + ' is marked, north of the centre.">' +
      '<path d="' + L.d + '" class="isle"/><rect x="' + b[0] + '" y="' + b[1] + '" width="' + (b[2] - b[0]).toFixed(1) + '" height="' + (b[3] - b[1]).toFixed(1) + '" class="here"/>' +
      '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="24" class="herering"/></svg><figcaption>' + esc(META.neighbourhood) + ', Singapore</figcaption></figure>';
  }

  // ---- the rainfall strip under the map: one bar per day, a day marker to drag, and Play
  function dayRain(sc, i) {          // mean of the gauges in use that day, and whether any counted the day as a flushing storm
    var sum = 0, n = 0, flush = false, bits = [];
    sc.stations.forEach(function (st) {
      if (st.mm[i] == null) { bits.push(st.id + ' no data'); return; }
      sum += st.mm[i]; n++; flush = flush || st.flush[i];
      bits.push(st.id + ' ' + st.mm[i].toFixed(1) + ' mm' + (st.flush[i] ? ' (flushing storm)' : ''));
    });
    return { mm: n ? sum / n : null, flush: flush, text: bits.join(', ') };
  }
  function dayLabel() {
    var sc = SCEN[state.scenario], last = lastDay(), i = state.day == null ? last : state.day, n = keyCounts(), gaps = (sc.replay_gaps || [])[i];
    var tail = ' <span class="tlcount">' + n.high + ' ' + BAND.high.toLowerCase() + ' · ' + n.medium + ' this week · ' + n.low + ' routine</span>';
    if (state.day == null) {
      return '<b>' + (sc.replayed ? 'End of the replayed period.' : 'Today, ' + longDate(AS_OF) + '.') + '</b> Rain counted up to ' + shortDate(sc.dates[last]) + '.' + tail;
    }
    return '<b>After the rain of ' + shortDate(sc.dates[i]) + '.</b> Day ' + (i + 1) + ' of ' + (last + 1) + ', from scores worked out in advance.' +
      (state.records.length ? ' Inspections saved on this device are left out.' : '') +
      (gaps ? ' <span class="tag warn">' + plural(gaps, 'earlier day') + ' of rain not cached: counted as unknown</span>' : '') + tail +
      ' <button class="link" data-day="today">Back to today</button>';
  }
  function timelineHtml() {
    var sc = SCEN[state.scenario], last = lastDay(), ids = sc.stations.map(function (s) { return s.id; });
    if (!sc.stations.length) return '<p class="err">No rainfall is cached for this period, so there is nothing to replay. Run the refresh while online.</p>';
    return '<div class="tlhead"><b>Daily rain, ' + shortDate(sc.dates[0]) + ' to ' + longDate(sc.dates[last]) + '</b> <span class="muted">mean of ' + (ids.length > 1 ? 'gauges ' : 'gauge ') + esc(ids.join(' and ')) +
      ', ' + esc(sourceOf('rainfall').agency) + (sc.replayed ? '. Replayed over today\'s assets' : '') + '</span></div>' +
      '<div class="tlrow"><button class="btn tlplay" data-play aria-pressed="false" aria-label="Play the ' + (last + 1) + ' days"><span class="ico" aria-hidden="true">▶</span> <span class="txt">Play</span></button>' +
      '<div class="tltrack" id="tltrack"><svg id="tlbars" aria-hidden="true"></svg>' +
      '<input type="range" id="tlday" min="0" max="' + last + '" step="1" value="' + (state.day == null ? last : state.day) + '" aria-label="Day shown on the map"></div></div>' +
      '<p class="tlnow" id="tlnow" role="status">' + dayLabel() + '</p>';
  }
  function drawTimeline() {
    var box = $('#tltrack'), svg = $('#tlbars'), sc = SCEN[state.scenario];
    if (!box || !svg) return;
    // T is the width of the day marker (see #tlday in style.css): the slider moves its centre from T/2 to W - T/2, so the bars are laid out to match.
    var W = box.clientWidth, H = 66, T = 30, n = sc.dates.length, stepX = (W - T) / (n - 1), bw = Math.max(5, Math.min(20, stepX - 8));
    var top = rainMax(), base = H - 17, ph = base - 13, cur = state.day == null ? n - 1 : state.day, h = '', every = stepX < 34 ? 3 : stepX < 52 ? 2 : 1;
    h += '<line x1="0" x2="' + W + '" y1="' + base + '" y2="' + base + '" class="axis"/>';
    sc.dates.forEach(function (d, i) {
      var cx = T / 2 + stepX * i, r = dayRain(sc, i), bh, y, rr;
      if (i % every === (n - 1) % every) h += '<text x="' + cx + '" y="' + (H - 4) + '" class="tick' + (i === cur ? ' cur' : '') + '" text-anchor="middle">' + shortDate(d) + '</text>';
      if (r.mm == null) { h += '<text x="' + cx + '" y="' + (base - 4) + '" class="tick" text-anchor="middle">?</text>'; return; }
      bh = Math.max(r.mm > 0 ? 2 : 0, ph * r.mm / top); y = base - bh; rr = Math.min(3, bh);
      h += '<g class="bar' + (r.flush ? ' flush' : '') + (i > cur ? ' later' : '') + '">';
      if (bh) h += '<path d="M' + (cx - bw / 2) + ',' + base + 'v' + (-(bh - rr)) + 'q0,' + (-rr) + ' ' + rr + ',' + (-rr) + 'h' + (bw - 2 * rr) + 'q' + rr + ',0 ' + rr + ',' + rr + 'v' + (bh - rr) + 'z"/>';
      if (r.flush) h += '<text x="' + cx + '" y="' + (y - 3) + '" class="fl" text-anchor="middle">flush</text>';
      else if (r.mm >= 1 && bw >= 16) h += '<text x="' + cx + '" y="' + (y - 3) + '" class="val" text-anchor="middle">' + Math.round(r.mm) + '</text>';
      h += '</g>';
    });
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.setAttribute('width', W); svg.setAttribute('height', H);
    svg.innerHTML = h;
    var inp = $('#tlday'), now = dayRain(sc, cur);
    if (inp) inp.setAttribute('aria-valuetext', shortDate(sc.dates[cur]) + ': ' + (now.mm == null ? 'no rain data' : now.text));
  }
  // Show another day. Markers glide to that day's size and colour; nothing else on the map moves.
  function setDay(i, fromSlider) {
    var last = lastDay(), inp = $('#tlday'), now;
    state.day = i == null || i >= last ? null : Math.max(0, i);
    if (inp && !fromSlider) inp.value = state.day == null ? last : state.day;
    now = {};
    shownList().forEach(function (t) { now[t.asset.id] = t.total; });
    marks.forEach(function (m) { if (now[m.a.id] !== m.v) paintMark(m, now[m.a.id], true); });
    updateKeyCounts();
    if ($('#tlnow')) $('#tlnow').innerHTML = dayLabel();
    if (state.sel && $('#panel')) $('#panel').innerHTML = mapPanel();
    var z = mapSize();
    if (Math.abs(z.h - state.vb.h) > 1 || Math.abs(z.w - state.vb.w) > 1) onResize(); else drawTimeline();   // the strip grew or shrank by a line
  }
  function stopPlay() {
    if (playTimer) { clearInterval(playTimer); playTimer = null; }
    var b = $('[data-play]');
    if (b) { b.setAttribute('aria-pressed', 'false'); b.querySelector('.ico').textContent = '▶'; b.querySelector('.txt').textContent = 'Play'; }
  }
  function togglePlay() {
    if (playTimer) { stopPlay(); return; }
    var last = lastDay(), b = $('[data-play]');
    setDay(state.day == null ? 0 : state.day + 1);          // from the end, start over; otherwise carry on from here
    if (state.day == null) return;
    b.setAttribute('aria-pressed', 'true'); b.querySelector('.ico').textContent = '❚❚'; b.querySelector('.txt').textContent = 'Pause';
    playTimer = setInterval(function () {
      if (!$('#tlday')) { stopPlay(); return; }             // the map screen was left
      setDay(state.day == null ? last : state.day + 1);
      if (state.day == null) stopPlay();
    }, still() ? 1500 : 950);
  }

  // After an inspection is saved: the marker starts at its old score, then changes to the new one
  // while a ring spreads from it, and a label beside it shows the two numbers.
  function showFlashOnMap() {
    var f = state.flash, m;
    if (!f || f.onMap || state.day != null) return;
    m = marks.filter(function (x) { return x.a.id === f.id; })[0];
    if (!m) return;
    f.onMap = true;
    var after = scoreAsset(m.a, state.scenario).total, note = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    note.setAttribute('class', 'chg'); note.setAttribute('y', (-(radius(Math.max(after, f.before)) + 9)).toFixed(1));
    note.textContent = f.before + ' → ' + after;
    m.el.appendChild(note);
    if (still() || after === f.before) return;
    paintMark(m, f.before, false);
    setTimeout(function () {
      if (!document.body.contains(m.el)) return;
      var pulse = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      pulse.setAttribute('class', 'pulse'); pulse.setAttribute('r', '12');
      m.el.insertBefore(pulse, m.mb);
      paintMark(m, after, true);
    }, 600);
  }

  function renderMap(focusId) {
    if (focusId && ASSET[focusId]) { state.sel = focusId; state.selCluster = null; }
    if (state.keyOpen == null) state.keyOpen = window.innerWidth > 760;
    $('#view').innerHTML = '<div class="mapwrap' + (state.sel || state.selCluster != null ? ' has-sel' : '') + '"><div class="mapcol"><div class="mapbox">' +
      '<svg id="map" role="img" aria-label="Map of ' + esc(META.neighbourhood) + '. Markers grow and darken with inspection priority. The Tasks screen lists the same assets as text."></svg>' +
      '<div class="mapctl"><button data-z="in" aria-label="Zoom in">+</button><button data-z="out" aria-label="Zoom out">−</button><button data-z="fit" aria-label="Show the neighbourhood">⤢</button></div>' +
      '<details class="mapkey" id="mapkey"' + (state.keyOpen ? ' open' : '') + '>' + mapKey() + '</details>' + locatorHtml() +
      '</div><div class="strip" id="strip">' + timelineHtml() + '</div></div>' +
      '<aside id="panel" class="panel">' + mapPanel() + '</aside></div>';
    mapEl = $('#map');
    drawMap();
    if (!areaAnchors) { areaAnchors = findAreaAnchors(); drawMap(); }   // second pass, with the names moved to free ground
    if (!state.vb) resetView();
    onResize();                                   // the box may have changed size since the map was last shown
    if (focusId && ASSET[focusId]) { centreOn(ASSET[focusId]); applyView(); }
    bindMap();
    showFlashOnMap();
  }
  function refreshMap() {
    drawMap();
    $('#panel').innerHTML = mapPanel();
    $('.mapwrap').classList.toggle('has-sel', !!(state.sel || state.selCluster != null));
    onResize();                                   // on a phone the map box shrinks when the panel opens
  }

  function bindMap() {
    var ptrs = {}, moved = false, downTarget = null, lastDist = 0;
    function count() { return Object.keys(ptrs).length; }
    mapEl.addEventListener('pointerdown', function (e) {
      ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
      if (count() === 1) { moved = false; downTarget = e.target; }
      try { mapEl.setPointerCapture(e.pointerId); } catch (err) { /* older browsers */ }
    });
    mapEl.addEventListener('pointermove', function (e) {
      var p = ptrs[e.pointerId];
      if (!p) return;
      var dx = e.clientX - p.x, dy = e.clientY - p.y;
      if (count() === 1) {
        if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
        if (moved) { state.vb.x -= dx * state.vb.k; state.vb.y -= dy * state.vb.k; state.vb.fit = false; p.x = e.clientX; p.y = e.clientY; applyView(); }
      } else {
        p.x = e.clientX; p.y = e.clientY;
        var ids = Object.keys(ptrs), a = ptrs[ids[0]], b = ptrs[ids[1]], d = Math.hypot(a.x - b.x, a.y - b.y), z = mapSize();
        if (lastDist) zoomAt(lastDist / d, (a.x + b.x) / 2 - z.left, (a.y + b.y) / 2 - z.top);
        lastDist = d; moved = true;
      }
    });
    function up(e) {
      delete ptrs[e.pointerId];
      lastDist = 0;
      if (count() || moved || !downTarget || !downTarget.closest) return;
      var z = mapSize(), mk = pickMarker(e.clientX - z.left, e.clientY - z.top), cl = downTarget.closest('[data-cl]');
      state.sel = mk ? mk.a.id : null;
      state.selCluster = !mk && cl ? +cl.getAttribute('data-cl') : null;
      refreshMap();
    }
    mapEl.addEventListener('pointerup', up);
    mapEl.addEventListener('pointercancel', function (e) { delete ptrs[e.pointerId]; lastDist = 0; });
    mapEl.addEventListener('wheel', function (e) {
      e.preventDefault();
      var z = mapSize();
      zoomAt(e.deltaY > 0 ? 1.25 : 0.8, e.clientX - z.left, e.clientY - z.top);
    }, { passive: false });
  }

  // ------------------------------------------------------------------ task list
  function renderTasks() {
    var list = rankTasks(state.scenario), base = state.scenario === REAL ? null : rankIndex(rankTasks(REAL));
    var n = { all: list.length, high: 0, medium: 0, low: 0 };
    list.forEach(function (t) { n[t.band]++; });
    var h = '<section class="pad"><h1>Inspection tasks</h1>' +
      '<p class="lead">Every asset, ranked by what is known today. The reasons are listed with each one. ' +
      '<b>The "inspected" and "not inspected" reasons come from a simulated history</b> until an inspection is recorded on this device. Rain, clusters and locations are real.</p>' +
      '<div class="filters" role="group" aria-label="Show">';
    [['all', 'All'], ['high', BAND.high], ['medium', BAND.medium], ['low', BAND.low]].forEach(function (f) {
      h += '<button data-filter="' + f[0] + '" aria-pressed="' + (state.filter === f[0]) + '">' + f[1] + ' <span>' + n[f[0]] + '</span></button>';
    });
    h += '<a class="btn" href="task-sheet.html">Printable sheet with route</a></div><ol class="tasks">';
    var fl = state.flash;
    list.forEach(function (t) {
      var a = t.asset, mv = '', was = fl && fl.id === a.id ? fl : null, moved = '';
      if (state.filter !== 'all' && t.band !== state.filter && !was) return;       // the asset just inspected stays in view whatever the filter
      if (base) {
        var d = base[a.id].rank - t.rank;
        mv = d > 0 ? '<span class="mv up" title="Up ' + d + ' against the real rainfall">▲ ' + d + '</span>'
          : d < 0 ? '<span class="mv down" title="Down ' + (-d) + ' against the real rainfall">▼ ' + (-d) + '</span>' : '<span class="mv">=</span>';
      }
      if (was) {
        // What the inspection just saved did to this asset's place in the list.
        var step = t.rank - was.rankBefore;
        moved = '<p class="moved" role="status"><b>' + (step > 0 ? '▼ Down ' + plural(step, 'place') : step < 0 ? '▲ Up ' + plural(-step, 'place') : 'Same place') + '</b> since your inspection: rank ' +
          was.rankBefore + ' → ' + t.rank + ', score ' + was.before + ' → ' + t.total + '.</p>';
      }
      h += '<li class="task b-' + t.band + (was ? ' just' : '') + '"' + (was ? ' id="just"' : '') + '><div class="rk"><b>' + t.rank + '</b>' + mv + '</div>' +
        '<div class="tb"><p class="tn"><a href="#/map/' + esc(a.id) + '">' + esc(a.name) + '</a>' + simBadge(a) + '</p>' +
        '<p class="tt">' + esc(S.types[a.type].label) + (t.last.device ? ' · <span class="tag dev">inspected on this device</span>' : '') + '</p>' + moved +
        '<ul class="why">' + whyList(t.parts) + '</ul>' +
        '<details><summary>How this score is made</summary>' + partsHtml(t) + '</details></div>' +
        '<div class="ts">' + chip(t) + '<a class="btn pri" href="#/inspect/' + esc(a.id) + '">Inspect</a></div></li>';
    });
    if (!n[state.filter]) h += '<li class="muted">Nothing in this group.</li>';
    $('#view').innerHTML = h + '</ol></section>';
    var row = $('#just');
    if (row && fl && !fl.onList) {            // bring the asset just inspected into view, once
      fl.onList = true;
      row.scrollIntoView({ block: 'center', behavior: still() ? 'auto' : 'smooth' });
    }
  }

  // ------------------------------------------------------------------ inspection checklist
  var form = null;
  function renderInspect(id, saved) {
    var a = ASSET[id];
    if (!a) {
      $('#view').innerHTML = '<section class="pad"><h1>Asset not found</h1><p>No asset has the code <code>' + esc(id) + '</code> in this snapshot. It may have been removed since the QR code was printed.</p><p><a class="btn" href="#/tasks">Go to the task list</a></p></section>';
      return;
    }
    var t = S.types[a.type], s = scoreAsset(a, state.scenario);
    if (!form || form.id !== id) form = { id: id, water: null, larvae: null, actions: [], note: '' };
    var h = '<section class="pad narrow"><p class="crumb"><a href="#/tasks">Tasks</a> / Inspection</p>' +
      '<h1>' + esc(a.name) + simBadge(a) + '</h1><p class="meta">' + esc(t.label) + '. ' + originText(a) + '</p>';
    if (saved) {
      h += '<div class="done" role="status"><h2>Saved on this device</h2><p class="big">' + chip(saved.before) + ' <span aria-hidden="true">→</span> ' + chip(s) + '</p>' +
        '<p>' + (s.total < saved.before.total ? 'Priority went down by ' + (saved.before.total - s.total) + ' points.' : s.total === saved.before.total ? 'Priority is unchanged.' : 'Priority went up.') +
        ' Rank ' + saved.rankBefore + ' → ' + rankIndex(rankTasks(state.scenario))[a.id].rank + ' of ' + S.assets.length + '.' +
        (s.parts[1].state === 'follow_up' ? ' Standing water was left in place, so the asset stays flagged for a return visit.' : '') + '</p>' +
        '<p class="muted">Kept in this browser only. Other devices do not see it until it is exported and imported there.</p>' +
        '<p class="acts"><a class="btn pri" href="#/tasks">Back to tasks</a> <a class="btn" href="#/map/' + esc(a.id) + '">Show on map</a> <button class="btn" data-undo="' + esc(saved.id) + '">Undo</button></p></div>';
    }
    h += '<details class="now"><summary>' + chip(s) + ' <span>Why this score</span></summary>' + partsHtml(s) + '</details>';
    if (saved) {
      $('#view').innerHTML = h + '<h3>Inspection history</h3>' + historyHtml(a) + '</section>';
      return;
    }
    h += '<form id="chk" novalidate><p class="look"><b>Look for:</b> ' + esc(t.look_for) + '</p>' +
      '<fieldset><legend>1. Standing water found?</legend><div class="seg">' + radio('water', 'yes', 'Yes', form.water === true) + radio('water', 'no', 'No', form.water === false) + '</div></fieldset>' +
      '<fieldset id="q-larvae"' + (form.water ? '' : ' disabled') + '><legend>2. Larvae found?</legend><div class="seg">' + radio('larvae', 'yes', 'Yes', form.larvae === true) + radio('larvae', 'no', 'No', form.larvae === false) + '</div>' +
      '<p class="hint">Wrigglers in the water. If unsure, answer Yes and report it.</p></fieldset>' +
      '<fieldset><legend>3. Action taken</legend><div class="chips">';
    S.actions.forEach(function (act) {
      h += '<label><input type="checkbox" name="action" value="' + act + '"' + (form.actions.indexOf(act) >= 0 ? ' checked' : '') + '><span>' + act.charAt(0).toUpperCase() + act.slice(1) + '</span></label>';
    });
    h += '</div><p class="hint">General measures only. Leave all unticked if nothing was needed.</p></fieldset>' +
      '<fieldset><legend>4. Note <span class="muted">(optional)</span></legend><textarea name="note" rows="2" maxlength="200" placeholder="What you saw. No names or contact details.">' + esc(form.note) + '</textarea></fieldset>' +
      '<p class="err" id="err" role="alert" hidden></p>' +
      '<p class="acts"><button class="btn pri big" type="submit">Save inspection</button></p></form>' +
      '<h3>Inspection history</h3>' + historyHtml(a) + '</section>';
    $('#view').innerHTML = h;
  }
  function radio(name, val, label, on) {
    return '<label><input type="radio" name="' + name + '" value="' + val + '"' + (on ? ' checked' : '') + '><span>' + label + '</span></label>';
  }
  function readForm() {
    var f = $('#chk');
    if (!f) return;
    var w = f.querySelector('input[name=water]:checked'), l = f.querySelector('input[name=larvae]:checked');
    form.water = w ? w.value === 'yes' : null;
    form.larvae = form.water ? (l ? l.value === 'yes' : null) : false;
    form.actions = $$('input[name=action]:checked', f).map(function (i) { return i.value; });
    form.note = f.querySelector('textarea').value.slice(0, 200);
    $('#q-larvae').disabled = !form.water;
  }
  function submitForm() {
    readForm();
    var err = $('#err');
    if (form.water === null) { err.textContent = 'Answer question 1: was there standing water?'; err.hidden = false; return; }
    if (form.water && form.larvae === null) { err.textContent = 'Answer question 2: were there larvae in the water?'; err.hidden = false; return; }
    var a = ASSET[form.id], before = scoreAsset(a, state.scenario), rankBefore = rankIndex(rankTasks(state.scenario))[a.id].rank;
    var rec = { id: 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), asset_id: a.id, recorded_at: new Date().toISOString(),
      standing_water: form.water, larvae: !!form.larvae, actions: form.actions, note: form.note.trim() };
    state.records.push(rec);
    saveRecords();
    form = null;
    state.flash = { id: a.id, rec: rec.id, before: before.total, rankBefore: rankBefore };   // the map and the task list show this change once each
    state.day = null;
    renderInspect(a.id, { before: before, id: rec.id, rankBefore: rankBefore });
    window.scrollTo(0, 0);
  }

  // ------------------------------------------------------------------ dashboard
  function renderDashboard() {
    var onTime = CFG.inspection.on_time_days, list = rankTasks(state.scenario);
    var ok = [], overdue = [], never = [], repeat = [], byType = {};
    list.forEach(function (t) {
      var a = t.asset, li = t.last, bt = byType[a.type] || (byType[a.type] = { n: 0, ok: 0 });
      bt.n++;
      if (!li.rec) never.push(t);
      else if (li.days <= onTime) { ok.push(t); bt.ok++; }
      else overdue.push(t);
      var recent = recordsFor(a.id).concat(a.inspections).slice(0, 3);
      if (recent.filter(function (r) { return r.standing_water; }).length >= 2) repeat.push(t);
    });
    overdue.sort(function (x, y) { return y.last.days - x.last.days; });
    var total = list.length, pct = Math.round(100 * ok.length / total);
    var h = '<section class="pad"><h1>Dashboard</h1><p class="lead">Coverage of the ' + total + ' registered assets as of ' + longDate(AS_OF) +
      ', plus anything recorded on this device since.</p>';
    h += '<div class="tiles">' +
      tile('Inspected on time', pct + '%', ok.length + ' of ' + total + ' within ' + onTime + ' days', '<div class="meter wide" role="img" aria-label="' + pct + ' percent"><i style="width:' + pct + '%"></i></div>') +
      tile('Overdue', overdue.length, 'last inspected more than ' + onTime + ' days ago') +
      tile('Never inspected', never.length, 'no inspection on record') +
      tile('Repeat problem sites', repeat.length, 'standing water at 2 of the last 3 visits') + '</div>';

    h += '<div class="cols"><div><h2>On time, by asset type</h2><ul class="mlist">';
    Object.keys(byType).sort(function (x, y) { return byType[y].n - byType[x].n; }).forEach(function (k) {
      var b = byType[k], p = Math.round(100 * b.ok / b.n);
      h += '<li><span class="mn">' + esc(S.types[k].label) + '</span><div class="meter" role="img" aria-label="' + p + ' percent"><i style="width:' + p + '%"></i></div><span class="mv2">' + b.ok + ' of ' + b.n + '</span></li>';
    });
    h += '</ul><h2>Repeat problem sites</h2>';
    h += repeat.length ? '<ul class="plain">' + repeat.map(function (t) {
      return '<li><a href="#/map/' + esc(t.asset.id) + '">' + esc(t.asset.name) + '</a>' + simBadge(t.asset) + ' <span class="muted">' + esc(S.types[t.asset.type].label) + '</span></li>';
    }).join('') + '</ul>' : '<p class="muted">None.</p>';
    h += '<p class="muted">In this demo only simulated assets carry made-up findings, so only they can appear here.</p></div>';

    h += '<div><h2>Overdue and never inspected</h2><table class="tbl"><thead><tr><th>Asset</th><th>Last inspected</th><th>Priority</th></tr></thead><tbody>';
    overdue.concat(never).forEach(function (t) {
      h += '<tr><td><a href="#/map/' + esc(t.asset.id) + '">' + esc(t.asset.name) + '</a>' + simBadge(t.asset) + '</td><td>' +
        (t.last.rec ? daysAgoText(t.last.days) : 'never') + '</td><td>' + chip(t) + '</td></tr>';
    });
    h += '</tbody></table></div></div>';

    var mine = state.records.length;
    h += '<h2>Records on this device</h2><div class="card"><p><b>' + plural(mine, 'inspection') + '</b> recorded in this browser. ' +
      '<b>They are not shared.</b> Another phone or laptop will not see them until they are exported here and imported there.' +
      (state.memoryOnly ? ' <span class="err">This browser refused to store data, so they will be lost when the page closes.</span>' : '') + '</p>' +
      '<p class="acts"><button class="btn pri" data-do="export"' + (mine ? '' : ' disabled') + '>Copy records as text</button> ' +
      '<button class="btn" data-do="import">Import from text</button> <button class="btn" data-do="clear"' + (mine ? '' : ' disabled') + '>Delete records on this device</button></p>' +
      '<div id="io" hidden><textarea id="iotext" rows="6" aria-label="Records as text"></textarea><p class="acts"><button class="btn pri" data-do="import-go" hidden>Add these records</button> <span id="iomsg" role="status"></span></p></div></div>';

    h += '<h2>Print and share</h2><p class="acts"><a class="btn" href="task-sheet.html">Daily task sheet with route</a> <a class="btn" href="qr-sheet.html">QR codes for every asset</a> ' +
      '<a class="btn" href="qr-sheet.html#only=site">QR code that opens this site</a></p>';

    h += '<h2 id="sources">Data sources</h2><div class="scroll"><table class="tbl src"><thead><tr><th>Dataset</th><th>Agency</th><th>Snapshot</th><th>Source updated</th><th>Used for</th></tr></thead><tbody>';
    S.sources.forEach(function (x) {
      h += '<tr><td>' + esc(x.title) + (x.detail ? '<br><span class="muted">' + esc(x.detail) + '</span>' : '') + '</td><td>' + esc(x.agency) + '</td><td>' +
        (x.snapshot_date ? longDate(x.snapshot_date) : 'not cached') + (x.refresh && x.refresh.status === 'failed' ? '<br><span class="tag warn">source unavailable at last refresh, older copy used</span>' : '') +
        '</td><td>' + (x.source_updated ? longDate(x.source_updated) : '<span class="muted">live readings</span>') + '</td><td>' + esc(x.use) + '</td></tr>';
    });
    h += '</tbody></table></div><p class="muted">Contains information from data.gov.sg accessed under the <a href="' + esc(META.licence_url) + '" rel="noopener">' + esc(META.licence) + '</a>.</p>';

    var sim = S.assets.filter(function (a) { return a.simulated; }).length, test = selfTest(), ctx = S.context || {};
    h += '<h2>What is real and what is not</h2><ul class="plain honest">' +
      '<li><b>Real:</b> the locations of ' + (total - sim) + ' parks, park facilities, community gardens and PUB drain sensor sites; the dengue clusters and high-Aedes areas; the rainfall.</li>' +
      '<li><b>Simulated:</b> ' + sim + ' small assets (planters, pot trays, rain barrels, roadside drains, roof gardens), marked SIMULATED wherever they appear.</li>' +
      '<li><b>Simulated:</b> every past inspection. A real place carries made-up visit dates only, each recorded as "no standing water". Made-up problems (standing water, larvae) are attached to simulated assets only.</li>' +
      '<li><b>Assumed:</b> whether an asset holds water and how fast it drains. No open dataset records this.</li>' +
      '<li><b>Placeholders:</b> every threshold and weight in the score. They await review by people who know vector control.</li></ul>';
    // How much of the ranking rests on each kind of input. The largest part is the one with made-up data behind it.
    var pts = { water: 0, simulated: 0, device: 0, rain: 0, location: 0 }, all = 0;
    list.forEach(function (t) {
      t.parts.forEach(function (p) { pts[p.key === 'inspection' ? (t.last.device ? 'device' : 'simulated') : p.key] += p.points; all += p.points; });
    });
    function share(v) { return all ? Math.round(100 * v / all) + '%' : '0%'; }
    h += '<h3>Where the points on today\'s list come from</h3><table class="tbl num mix"><thead><tr><th>Part of the score</th><th>Share of all points</th><th>What it rests on</th></tr></thead><tbody>' +
      '<tr><td>' + PART.inspection + '</td><td>' + share(pts.simulated) + '</td><td><b>Simulated inspection history</b></td></tr>' +
      (pts.device ? '<tr><td>' + PART.inspection + '</td><td>' + share(pts.device) + '</td><td>Inspections recorded on this device</td></tr>' : '') +
      '<tr><td>' + PART.water + '</td><td>' + share(pts.water) + '</td><td>Assumption per asset type</td></tr>' +
      '<tr><td>' + PART.rain + '</td><td>' + share(pts.rain) + '</td><td>Real rainfall, assumed drain time</td></tr>' +
      '<tr><td>' + PART.location + '</td><td>' + share(pts.location) + '</td><td>Real clusters and high-Aedes areas</td></tr></tbody></table>' +
      '<p class="muted">So the order of the list is driven largely by made-up inspection dates. In real use, each inspection that is recorded replaces a made-up date, and an asset that has never been inspected simply scores the full ' +
      CFG.inspection.points_never + ' for that part.</p>';
    h += '<h2>About this snapshot</h2><ul class="plain">' +
      '<li>Computed once, on ' + esc(META.generated_at.slice(0, 16).replace('T', ' ')) + ' Singapore time, by one script. Nothing runs in between.</li>' +
      '<li>Everything this page loaded weighs <b>' + (META.page_weight_bytes / 1024).toFixed(0) + ' KB</b>, map included. It makes no network requests after that.</li>' +
      (META.last_refresh ? '<li>The last refresh made ' + META.last_refresh.requests + ' requests and received ' + META.last_refresh.kilobytes + ' KB.</li>' : '') +
      (ctx.temperature ? '<li>Context, not used in the score: ' + ctx.temperature.value + ' °C' + (ctx.humidity ? ' and ' + ctx.humidity.value + '% humidity' : '') + ' at ' + esc(ctx.temperature.station) + ' when the snapshot was taken. ' +
        (ctx.flood_alerts != null ? plural(ctx.flood_alerts, 'PUB flood alert') + ' active.' : '') + '</li>' : '') +
      '<li>Self-check: the browser and the data script ' + (test.mismatches.length ? '<b class="err">disagree on ' + test.mismatches.length + ' of ' + test.checked + ' scores</b>. Run the refresh again.' : 'agree on all ' + test.checked + ' scores.') + '</li>' +
      (META.warnings.length ? '<li class="err">' + META.warnings.map(esc).join(' ') + '</li>' : '') + '</ul></section>';
    $('#view').innerHTML = h;
  }
  function tile(label, value, sub, extra) {
    return '<div class="tile"><p class="tl">' + label + '</p><p class="tv">' + value + '</p>' + (extra || '') + '<p class="tsub">' + sub + '</p></div>';
  }

  function exportText() {
    return 'Canopy Care inspection records\nexported ' + new Date().toISOString() + ' | snapshot ' + AS_OF + ' | ' + plural(state.records.length, 'record') + '\n' +
      JSON.stringify(state.records, null, 1);
  }
  function importText(text) {
    var at = text.indexOf('['), list;
    try { list = JSON.parse(text.slice(at)); } catch (e) { return 'That text is not a Canopy Care export.'; }
    if (at < 0 || !Array.isArray(list)) return 'That text is not a Canopy Care export.';
    var have = {}, added = 0, skipped = 0;
    state.records.forEach(function (r) { have[r.id] = 1; });
    list.forEach(function (r) {
      if (!validRecord(r)) { skipped++; return; }
      if (have[r.id]) return;
      state.records.push({ id: r.id, asset_id: r.asset_id, recorded_at: r.recorded_at, standing_water: r.standing_water, larvae: r.larvae,
        actions: r.actions.slice(), note: String(r.note || '').slice(0, 200) });
      have[r.id] = 1; added++;
    });
    saveRecords();
    return plural(added, 'record') + ' added' + (skipped ? ', ' + skipped + ' not recognised and left out' : '') + '.';
  }

  // ------------------------------------------------------------------ scenarios
  function rainMax() {
    var mx = 10;
    S.scenarios.forEach(function (s) { s.stations.forEach(function (st) { st.mm.forEach(function (v) { if (v > mx) mx = v; }); }); });
    return Math.ceil(mx / 20) * 20;
  }
  function rainChart(sc, st, top) {
    var W = 420, H = 150, L = 30, B = 22, T = 14, n = sc.dates.length, slot = (W - L - 6) / n, bw = Math.min(24, slot - 2), ph = H - B - T;
    var h = '<svg class="rain" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Daily rainfall at ' + esc(st.id) + ', ' + longDate(sc.from) + ' to ' + longDate(sc.to) + '. The table below has the numbers.">';
    for (var g = 0; g <= top; g += top / 4) {
      var gy = T + ph - ph * g / top;
      h += '<line x1="' + L + '" x2="' + (W - 6) + '" y1="' + gy + '" y2="' + gy + '" class="' + (g ? 'grid' : 'axis') + '"/><text x="' + (L - 5) + '" y="' + (gy + 3.5) + '" class="tick" text-anchor="end">' + g + '</text>';
    }
    sc.dates.forEach(function (d, i) {
      var x = L + slot * i + (slot - bw) / 2, v = st.mm[i], cx = x + bw / 2;
      if (i === n - 1 || (i % 4 === 0 && i < n - 2)) h += '<text x="' + cx + '" y="' + (H - 7) + '" class="tick" text-anchor="middle">' + shortDate(d) + '</text>';
      if (v == null) { h += '<text x="' + cx + '" y="' + (T + ph - 4) + '" class="tick" text-anchor="middle">?</text>'; return; }
      var bh = Math.max(v > 0 ? 1.5 : 0, ph * v / top), y = T + ph - bh, r = Math.min(4, bh);
      var tip = shortDate(d) + ': ' + v.toFixed(1) + ' mm, heaviest hour ' + (st.max60[i] || 0).toFixed(1) + ' mm' + (st.flush[i] ? '. Counted as a flushing storm.' : '');
      h += '<g class="bar' + (st.flush[i] ? ' flush' : '') + '" tabindex="0" data-tip="' + esc(tip) + '"><rect x="' + (x - 1) + '" y="' + T + '" width="' + (bw + 2) + '" height="' + ph + '" class="hit"/>';
      if (bh) h += '<path d="M' + x + ',' + (T + ph) + 'v' + (-(bh - r)) + 'q0,' + (-r) + ' ' + r + ',' + (-r) + 'h' + (bw - 2 * r) + 'q' + r + ',0 ' + r + ',' + r + 'v' + (bh - r) + 'z"/>';
      if (st.flush[i]) h += '<text x="' + cx + '" y="' + (y - 4) + '" class="fl" text-anchor="middle">flush</text>';
      h += '</g>';
    });
    return h + '</svg>';
  }
  function rainTable(sc) {
    var h = '<details class="tview"><summary>Show the numbers</summary><div class="scroll"><table class="tbl num"><thead><tr><th>Date</th>';
    sc.stations.forEach(function (st) { h += '<th>' + esc(st.id) + ' mm</th><th>' + esc(st.id) + ' heaviest hour</th>'; });
    h += '</tr></thead><tbody>';
    sc.dates.forEach(function (d, i) {
      h += '<tr><td>' + shortDate(d) + '</td>';
      sc.stations.forEach(function (st) {
        h += st.mm[i] == null ? '<td colspan="2">no data</td>' : '<td>' + st.mm[i].toFixed(1) + (st.flush[i] ? ' <span class="tag">flush</span>' : '') + '</td><td>' + (st.max60[i] || 0).toFixed(1) + '</td>';
      });
      h += '</tr>';
    });
    return h + '</tbody></table></div></details>';
  }
  function renderScenario() {
    var top = rainMax(), r = CFG.rain, realIdx = rankIndex(rankTasks(REAL));
    var h = '<section class="pad wide"><h1>Rainfall scenarios</h1>' +
      '<p class="lead">More rain does not simply mean more risk. Switch the rainfall and watch the task list reorder. Every scenario replays <b>real rain measured at the same stations</b>; only the period changes. Keys 1 to ' + S.scenarios.length + ' switch too.</p><div class="scens">';
    S.scenarios.forEach(function (sc, i) {
      var on = sc.id === state.scenario, list = rankTasks(sc.id), n = { high: 0, medium: 0, low: 0 };
      list.forEach(function (t) { n[t.band]++; });
      h += '<article class="scn' + (on ? ' on' : '') + '"><header><button class="btn ' + (on ? 'pri' : '') + '" data-scen="' + esc(sc.id) + '" aria-pressed="' + on + '"><kbd>' + (i + 1) + '</kbd> ' + esc(sc.label) + '</button>' +
        '<p class="when">' + (sc.replayed ? 'Replays ' : '') + longDate(sc.from) + ' to ' + longDate(sc.to) + (sc.replayed ? '' : ' <span class="tag">what actually happened</span>') + '</p></header>' +
        '<p>' + esc(sc.summary) + '</p>';
      if (!sc.stations.length) h += '<p class="err">No rainfall is cached for this period. Run the refresh while online.</p>';
      sc.stations.forEach(function (st) {
        h += '<figure><figcaption><b>' + esc(st.id + ' ' + st.name) + '</b> · daily rain in mm · nearest gauge for ' + plural(st.assets, 'asset') + '</figcaption>' + rainChart(sc, st, top) + '</figure>';
      });
      if (sc.stations.length) h += rainTable(sc);
      h += '<p class="split"><span class="chip b-high"><b>' + n.high + '</b> ' + BAND.high + '</span> <span class="chip b-medium"><b>' + n.medium + '</b> ' + BAND.medium + '</span> <span class="chip b-low"><b>' + n.low + '</b> ' + BAND.low + '</span></p>';
      h += '<p class="toplist"><b>Top of the list:</b> ' + list.slice(0, 5).map(function (t) {
        var d = realIdx[t.asset.id].rank - t.rank;
        return esc(t.asset.name) + ' <span class="muted">' + t.total + (sc.id !== REAL && d ? (d > 0 ? ', up ' + d : ', down ' + (-d)) : '') + '</span>';
      }).join('; ') + '</p></article>';
    });
    h += '</div><h2>How rain enters the score</h2><div class="cols3">' +
      '<div class="card"><h3>Light or moderate rain</h3><p>A day with ' + r.wetting_rain_mm + ' mm or more wets every rain-fed asset. The water stays for the asset\'s drain time after the last shower, so showers that keep arriving before it has drained keep it wet without a break. ' +
      'The count is of unbroken days of standing water, not days since the latest rain. ' +
      'Water standing ' + CFG.life_cycle.days + ' days or more scores the full ' + r.points_full_cycle + '.</p></div>' +
      '<div class="card"><h3>Heavy rain</h3><p>A storm of ' + r.flush_hour_mm + ' mm in an hour, or ' + r.flush_day_mm + ' mm in a day, is taken to flush drains: the clock restarts and the drain scores 0 for ' + r.flush_relief_days +
      ' days. Containers are not flushed. Heavy rain fills them.</p></div>' +
      '<div class="card"><h3>After the rain stops</h3><p>Water keeps standing until the drain time has passed, then the asset counts as dry. Assets watered by hand or holding stored water do not depend on rain at all, so in a dry spell they are what is left on the list.</p></div></div>' +
      '<p class="muted">Why a flush lowers the score: a year of field surveys in Geylang found most Aedes aegypti breeding in storm drains gone after intense monsoon storms (Seidahmed and Eltahir 2016, PLoS Negl Trop Dis 10(7): e0004842), and dengue outbreak risk in Singapore was lower one to six weeks after flushing events (Benedum et al. 2018, PLoS Negl Trop Dis 12(12): e0006935). ' +
      '<b>Neither paper gives a single rainfall cut-off, so every number here is a placeholder awaiting expert review.</b> They are in <code>config/risk_config.toml</code>.</p></section>';
    $('#view').innerHTML = h;
  }

  // ------------------------------------------------------------------ chrome, routing, events
  function setScenario(id) {
    if (!SCEN[id]) return;
    stopPlay();
    state.scenario = id;
    state.day = null;                         // another rainfall period: start from its last day
    try { sessionStorage.setItem('canopy-care/scenario', id); } catch (e) { /* not essential */ }
    route();
  }
  function chrome(tab) {
    var sc = SCEN[state.scenario];
    $('#place').textContent = META.neighbourhood + ' · data as of ' + longDate(AS_OF);
    $('#scenario').innerHTML = S.scenarios.map(function (s) { return '<option value="' + esc(s.id) + '"' + (s.id === state.scenario ? ' selected' : '') + '>' + esc(s.label) + '</option>'; }).join('');
    $$('nav a').forEach(function (a) { a.classList.toggle('on', a.getAttribute('data-tab') === tab); if (a.getAttribute('data-tab') === tab) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    $('#caveat').innerHTML = '<b>Inspection priority, not a dengue forecast.</b> Thresholds are placeholders. Locations are real; inspection history and assets marked SIMULATED are made up. <a href="#/dashboard">What is real</a>';
    var rp = $('#replay');
    rp.hidden = !sc.replayed;
    if (sc.replayed) rp.innerHTML = '<b>Scenario: ' + esc(sc.label) + '.</b> Replaying the real rainfall of ' + longDate(sc.from) + ' to ' + longDate(sc.to) + ' over today\'s assets. Not today\'s conditions. <button class="link" data-scen="' + esc(REAL) + '">Back to real rainfall</button>';
    $('#foot').innerHTML = 'Data: NEA, NParks, PUB and URA via data.gov.sg, ' + esc(META.licence) + '. Snapshot ' + longDate(AS_OF) + '. <a href="#/dashboard">Sources and dates</a>';
    document.body.className = 'v-' + tab;
  }
  var lastHash = null;
  function route() {
    var p = (location.hash || '#/map').replace(/^#\/?/, '').split('/'), tab = p[0] || 'map', arg = p[1] ? decodeURIComponent(p[1]) : null;
    hideTip();
    stopPlay();
    if (tab !== 'map') state.day = null;       // the day-by-day replay belongs to the map; every other screen shows the snapshot day
    var fresh = lastHash !== location.hash;
    if (fresh) { window.scrollTo(0, 0); lastHash = location.hash; }   // a new screen starts at its top; a scenario switch stays put
    // #/map/<asset id or ->/<day 1 to 14> opens the map on that day of the window, for a link or a bookmark.
    if (fresh && tab === 'map' && /^\d+$/.test(p[2] || '')) state.day = +p[2] > lastDay() ? null : Math.max(0, +p[2] - 1);
    document.title = 'Canopy Care: ' + ({ tasks: 'Tasks', inspect: 'Inspection', dashboard: 'Dashboard', scenario: 'Scenarios' }[tab] || 'Map');
    if (tab === 'tasks') { chrome('tasks'); renderTasks(); }
    else if (tab === 'inspect') { chrome('tasks'); renderInspect(arg); }
    else if (tab === 'dashboard') { chrome('dashboard'); renderDashboard(); }
    else if (tab === 'scenario') { chrome('scenario'); renderScenario(); }
    else { chrome('map'); renderMap(arg); }
  }

  var tipEl = null;
  function showTip(el) {
    if (!tipEl) { tipEl = document.createElement('div'); tipEl.className = 'tip'; tipEl.setAttribute('role', 'tooltip'); document.body.appendChild(tipEl); }
    tipEl.textContent = el.getAttribute('data-tip');
    tipEl.hidden = false;
    var r = el.getBoundingClientRect(), w = tipEl.offsetWidth;
    tipEl.style.left = Math.max(6, Math.min(window.innerWidth - w - 6, r.left + r.width / 2 - w / 2)) + window.scrollX + 'px';
    tipEl.style.top = r.top + window.scrollY - tipEl.offsetHeight - 6 + 'px';
  }
  function hideTip() { if (tipEl) tipEl.hidden = true; }

  function copyText(text, done) {
    function oldWay() {            // works on plain http and from a file, where the clipboard API is not offered
      var ta = $('#iotext'), ok = false;
      ta.focus(); ta.select();
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      done(ok);
    }
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(function () { done(true); }, oldWay);
    else oldWay();
  }

  document.addEventListener('click', function (e) {
    var t = e.target, el;
    if ((el = t.closest('[data-scen]'))) { setScenario(el.getAttribute('data-scen')); return; }
    if (t.closest('[data-play]')) { togglePlay(); return; }
    if (t.closest('[data-day]')) { stopPlay(); setDay(null); return; }
    if ((el = t.closest('[data-filter]'))) { state.filter = el.getAttribute('data-filter'); renderTasks(); return; }
    if ((el = t.closest('[data-z]'))) {
      var z = el.getAttribute('data-z');
      if (z === 'fit') { resetView(); applyView(); } else zoomAt(z === 'in' ? 0.7 : 1.43);
      return;
    }
    if (t.closest('[data-close]')) { state.sel = null; state.selCluster = null; refreshMap(); return; }
    if ((el = t.closest('[data-qr]'))) {
      var box = el.closest('.ad').querySelector('.qrbox'), url = inspectUrl(el.getAttribute('data-qr'));
      box.hidden = !box.hidden;
      if (!box.hidden) {
        box.innerHTML = window.CanopyQR.svg(url, 190) + '<p class="muted">Scan to open this asset\'s checklist.<br><code>' + esc(url) + '</code></p>' +
          (/^file:|\/\/(localhost|127\.0\.0\.1|\[::1\])/i.test(url) ? '<p class="err">This is a local address, so the code only opens on this computer. Host the site folder, or serve it on your network, to scan it from a phone (see README).</p>' : '');
      }
      return;
    }
    if ((el = t.closest('[data-undo]'))) {
      var rid = el.getAttribute('data-undo'), rec = state.records.filter(function (r) { return r.id === rid; })[0];
      state.records = state.records.filter(function (r) { return r.id !== rid; });
      if (state.flash && state.flash.rec === rid) state.flash = null;
      saveRecords();
      renderInspect(rec ? rec.asset_id : form && form.id);
      return;
    }
    if ((el = t.closest('[data-do]'))) {
      var act = el.getAttribute('data-do'), io = $('#io'), ta = $('#iotext'), msg = $('#iomsg'), go = $('[data-do=import-go]');
      if (act === 'export') {
        io.hidden = false; go.hidden = true; ta.value = exportText(); ta.readOnly = true;
        copyText(ta.value, function (ok) { msg.textContent = ok ? 'Copied. Paste it into a message, a file, or Import on another device.' : 'Copying is blocked here. Select the text above and copy it by hand.'; });
      } else if (act === 'import') {
        io.hidden = false; go.hidden = false; ta.readOnly = false; ta.value = ''; ta.placeholder = 'Paste exported records here'; msg.textContent = ''; ta.focus();
      } else if (act === 'import-go') {
        var res = importText(ta.value);
        renderDashboard();
        $('#io').hidden = false; $('#iomsg').textContent = res;
      } else if (act === 'clear' && window.confirm('Delete the ' + plural(state.records.length, 'inspection') + ' recorded on this device? This cannot be undone.')) {
        state.records = []; saveRecords(); renderDashboard();
      }
      return;
    }
  });
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (t.id === 'scenario') { setScenario(t.value); $('#scenario').blur(); }   // drop focus so keys 1 to 4 work straight away
    else if (t.getAttribute('data-layer')) { state.layers[t.getAttribute('data-layer')] = t.checked; if (!t.checked) state.selCluster = null; refreshMap(); }
    else if (t.closest && t.closest('#chk')) readForm();
  });
  document.addEventListener('input', function (e) { if (e.target.id === 'tlday') { stopPlay(); setDay(+e.target.value, true); } });
  document.addEventListener('toggle', function (e) { if (e.target.id === 'mapkey') state.keyOpen = e.target.open; }, true);
  document.addEventListener('submit', function (e) { if (e.target.id === 'chk') { e.preventDefault(); submitForm(); } });
  document.addEventListener('keydown', function (e) {
    // Typing in a field is left alone. The day slider is an input too, but digits mean nothing to it, so they still switch scenario.
    if (e.ctrlKey || e.metaKey || e.altKey || (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) && e.target.type !== 'range')) return;
    var i = parseInt(e.key, 10);
    if (i >= 1 && i <= S.scenarios.length) setScenario(S.scenarios[i - 1].id);
  });
  ['pointerover', 'focusin'].forEach(function (ev) {
    document.addEventListener(ev, function (e) { var el = e.target.closest && e.target.closest('[data-tip]'); if (el) showTip(el); });
  });
  ['pointerout', 'focusout'].forEach(function (ev) {
    document.addEventListener(ev, function (e) { if (e.target.closest && e.target.closest('[data-tip]')) hideTip(); });
  });
  window.addEventListener('hashchange', route);
  window.addEventListener('resize', function () { if (document.body.className === 'v-map' && mapEl && document.body.contains(mapEl)) onResize(); });

  loadRecords();
  try { var saved = sessionStorage.getItem('canopy-care/scenario'); if (saved && SCEN[saved]) state.scenario = saved; } catch (e) { /* not essential */ }
  route();

  // For checks from the console and from the verification steps in DEMO.md.
  window.CanopyCare = { selfTest: selfTest, rankTasks: rankTasks, scoreAsset: scoreAsset, state: state, inspectUrl: inspectUrl };
})();
