/* Canopy Care: a small QR code generator. No dependencies.
 *
 * Byte mode, error correction level M, versions 1 to 10 (up to 213 bytes), which is
 * plenty for a web address. Written from the public QR Code specification (ISO/IEC 18004).
 *
 *   CanopyQR.matrix("https://example.org/#/inspect/x")  ->  array of rows of 0/1
 *   CanopyQR.svg(text, sizePx)                           ->  SVG markup with a quiet zone
 */
(function (root) {
  'use strict';

  // Per version (index 1..10), level M: error-correction codewords per block, then
  // [blocks, data codewords per block] groups.
  var EC = [null,
    [10, [[1, 16]]], [16, [[1, 28]]], [26, [[1, 44]]], [18, [[2, 32]]], [24, [[2, 43]]],
    [16, [[4, 27]]], [18, [[4, 31]]], [22, [[2, 38], [2, 39]]], [22, [[3, 36], [2, 37]]], [26, [[4, 43], [1, 44]]]];
  var ALIGN = [null, [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34], [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50]];

  // GF(256) tables for Reed-Solomon, primitive polynomial x^8 + x^4 + x^3 + x^2 + 1.
  var EXP = [], LOG = [];
  (function () {
    var x = 1;
    for (var i = 0; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 256) x ^= 0x11d; }
    for (i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
  })();
  function mul(a, b) { return a && b ? EXP[LOG[a] + LOG[b]] : 0; }

  function rsRemainder(data, n) {
    var gen = [1], i, j;
    for (i = 0; i < n; i++) {
      var next = [];
      for (j = 0; j <= gen.length; j++) next[j] = (j < gen.length ? mul(gen[j], EXP[i]) : 0) ^ (j > 0 ? gen[j - 1] : 0);
      gen = next;
    }
    // gen holds coefficients lowest power first; use it highest first for the division.
    var g = gen.slice().reverse();
    var rem = [];
    for (i = 0; i < n; i++) rem[i] = 0;
    for (i = 0; i < data.length; i++) {
      var f = data[i] ^ rem.shift();
      rem.push(0);
      for (j = 0; j < n; j++) rem[j] ^= mul(g[j + 1], f);
    }
    return rem;
  }

  function utf8(text) {
    var out = [], s = unescape(encodeURIComponent(text));
    for (var i = 0; i < s.length; i++) out.push(s.charCodeAt(i));
    return out;
  }

  function dataCapacity(v) {
    var n = 0;
    EC[v][1].forEach(function (g) { n += g[0] * g[1]; });
    return n;
  }

  function codewords(bytes, v) {
    var bits = [];
    function put(val, len) { for (var i = len - 1; i >= 0; i--) bits.push((val >> i) & 1); }
    put(4, 4);                                  // byte mode
    put(bytes.length, v < 10 ? 8 : 16);         // character count
    bytes.forEach(function (b) { put(b, 8); });
    var cap = dataCapacity(v) * 8;
    put(0, Math.min(4, cap - bits.length));     // terminator
    while (bits.length % 8) bits.push(0);
    var data = [];
    for (var i = 0; i < bits.length; i += 8) {
      var b = 0;
      for (var j = 0; j < 8; j++) b = (b << 1) | bits[i + j];
      data.push(b);
    }
    for (var pad = 0; data.length < cap / 8; pad++) data.push(pad % 2 ? 0x11 : 0xec);

    // split into blocks, add error correction, interleave
    var ecLen = EC[v][0], blocks = [], pos = 0;
    EC[v][1].forEach(function (g) {
      for (var k = 0; k < g[0]; k++) {
        var d = data.slice(pos, pos + g[1]);
        pos += g[1];
        blocks.push({ d: d, e: rsRemainder(d, ecLen) });
      }
    });
    var out = [], longest = 0;
    blocks.forEach(function (b) { longest = Math.max(longest, b.d.length); });
    for (i = 0; i < longest; i++) blocks.forEach(function (b) { if (i < b.d.length) out.push(b.d[i]); });
    for (i = 0; i < ecLen; i++) blocks.forEach(function (b) { out.push(b.e[i]); });
    return out;
  }

  function build(v, cw, mask) {
    var n = 17 + 4 * v, m = [], fn = [], r, c;
    for (r = 0; r < n; r++) { m.push(new Array(n).fill(0)); fn.push(new Array(n).fill(false)); }
    function set(x, y, dark) { m[y][x] = dark ? 1 : 0; fn[y][x] = true; }

    function finder(cx, cy) {
      for (var dy = -4; dy <= 4; dy++) for (var dx = -4; dx <= 4; dx++) {
        var x = cx + dx, y = cy + dy, d = Math.max(Math.abs(dx), Math.abs(dy));
        if (x >= 0 && x < n && y >= 0 && y < n) set(x, y, d !== 2 && d !== 4);
      }
    }
    for (var i = 0; i < n; i++) { set(6, i, i % 2 === 0); set(i, 6, i % 2 === 0); }   // timing
    finder(3, 3); finder(n - 4, 3); finder(3, n - 4);
    var al = ALIGN[v];
    for (i = 0; i < al.length; i++) for (var j = 0; j < al.length; j++) {
      if ((i === 0 && j === 0) || (i === 0 && j === al.length - 1) || (i === al.length - 1 && j === 0)) continue;
      for (var dy = -2; dy <= 2; dy++) for (var dx = -2; dx <= 2; dx++) {
        set(al[i] + dx, al[j] + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
      }
    }

    function formatBits(mk) {
      var data = mk, rem = data;                 // level M is 00, so the 5 data bits are just the mask
      for (var k = 0; k < 10; k++) rem = (rem << 1) ^ ((rem >> 9) * 0x537);
      var bits = ((data << 10) | rem) ^ 0x5412;
      function bit(k) { return ((bits >> k) & 1) === 1; }
      for (k = 0; k <= 5; k++) set(8, k, bit(k));
      set(8, 7, bit(6)); set(8, 8, bit(7)); set(7, 8, bit(8));
      for (k = 9; k < 15; k++) set(14 - k, 8, bit(k));
      for (k = 0; k < 8; k++) set(n - 1 - k, 8, bit(k));
      for (k = 8; k < 15; k++) set(8, n - 15 + k, bit(k));
      set(8, n - 8, true);                       // the fixed dark module
    }
    formatBits(mask);                            // reserves the format area before data goes in

    if (v >= 7) {
      var rem = v;
      for (i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >> 11) * 0x1f25);
      var vbits = (v << 12) | rem;
      for (i = 0; i < 18; i++) {
        var on = ((vbits >> i) & 1) === 1, a = n - 11 + (i % 3), b = Math.floor(i / 3);
        set(a, b, on); set(b, a, on);
      }
    }

    // data: two-column zigzag from the bottom right, skipping the vertical timing column
    var idx = 0, total = cw.length * 8;
    for (var right = n - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (var vert = 0; vert < n; vert++) {
        for (j = 0; j < 2; j++) {
          var x = right - j, up = ((right + 1) & 2) === 0, y = up ? n - 1 - vert : vert;
          if (!fn[y][x] && idx < total) {
            m[y][x] = (cw[idx >> 3] >> (7 - (idx & 7))) & 1;
            idx++;
          }
        }
      }
    }

    for (r = 0; r < n; r++) for (c = 0; c < n; c++) {
      if (fn[r][c]) continue;
      var inv;
      switch (mask) {
        case 0: inv = (c + r) % 2 === 0; break;
        case 1: inv = r % 2 === 0; break;
        case 2: inv = c % 3 === 0; break;
        case 3: inv = (c + r) % 3 === 0; break;
        case 4: inv = (Math.floor(c / 3) + Math.floor(r / 2)) % 2 === 0; break;
        case 5: inv = (c * r) % 2 + (c * r) % 3 === 0; break;
        case 6: inv = ((c * r) % 2 + (c * r) % 3) % 2 === 0; break;
        default: inv = ((c + r) % 2 + (c * r) % 3) % 2 === 0;
      }
      if (inv) m[r][c] ^= 1;
    }
    return m;
  }

  // Penalty score from the specification: lower is easier for a scanner to read.
  function penalty(m) {
    var n = m.length, score = 0, r, c, dark = 0;
    function line(get) {
      var run = 1, s = 0, k, seq = '';
      for (k = 0; k < n; k++) {
        seq += get(k);
        if (k > 0 && get(k) === get(k - 1)) { run++; } else { if (run >= 5) s += run - 2; run = 1; }
      }
      if (run >= 5) s += run - 2;
      var from = 0, at;
      while ((at = seq.indexOf('10111010000', from)) >= 0) { s += 40; from = at + 1; }
      from = 0;
      while ((at = seq.indexOf('00001011101', from)) >= 0) { s += 40; from = at + 1; }
      return s;
    }
    for (r = 0; r < n; r++) {
      score += line(function (k) { return m[r][k]; });
      score += line(function (k) { return m[k][r]; });
    }
    for (r = 0; r < n - 1; r++) for (c = 0; c < n - 1; c++) {
      var v = m[r][c];
      if (v === m[r][c + 1] && v === m[r + 1][c] && v === m[r + 1][c + 1]) score += 3;
    }
    for (r = 0; r < n; r++) for (c = 0; c < n; c++) dark += m[r][c];
    score += Math.floor(Math.abs(dark * 20 - n * n * 10) / (n * n)) * 10;
    return score;
  }

  function matrix(text) {
    var bytes = utf8(text), v = 1;
    while (v <= 10 && bytes.length > dataCapacity(v) - (v < 10 ? 2 : 3)) v++;
    if (v > 10) throw new Error('Text too long for a QR code here (' + bytes.length + ' bytes, limit 213).');
    var cw = codewords(bytes, v), best = null, bestScore = Infinity;
    for (var mask = 0; mask < 8; mask++) {
      var m = build(v, cw, mask), s = penalty(m);
      if (s < bestScore) { bestScore = s; best = m; }
    }
    return best;
  }

  function svg(text, sizePx) {
    var m = matrix(text), n = m.length, q = 4, d = '';
    for (var r = 0; r < n; r++) for (var c = 0; c < n; c++) {
      if (m[r][c]) {
        var w = 1;
        while (c + w < n && m[r][c + w]) w++;
        d += 'M' + (c + q) + ',' + (r + q) + 'h' + w + 'v1h-' + w + 'z';
        c += w - 1;
      }
    }
    var dim = n + 2 * q;
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + dim + ' ' + dim + '" width="' + sizePx + '" height="' + sizePx +
      '" shape-rendering="crispEdges" role="img" aria-label="QR code"><rect width="' + dim + '" height="' + dim +
      '" fill="#fff"/><path d="' + d + '" fill="#000"/></svg>';
  }

  // _parts is for tests/qr_selftest.html only.
  root.CanopyQR = { matrix: matrix, svg: svg, _parts: { rsRemainder: rsRemainder, codewords: codewords, build: build, utf8: utf8 } };
})(window);
