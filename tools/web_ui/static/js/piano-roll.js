/* === Piano roll SVG renderer === */

var _LAYER_COLORS = {
  'expressive_melody': '#4af',
  'cathedral_pad': '#6a6',
  'void_bass': '#a66',
  'phantom_choir': '#a6f',
  'tape_decay': '#886'
};
var _NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];

function midiName(n) { return _NOTE_NAMES[n % 12] + (Math.floor(n / 12) - 1); }

function renderPianoRoll(config) {
  if (!config || !config.layers) return null;
  var melodyLayers = config.layers.filter(function(l) {
    return l.type === 'expressive_melody' && l.notes && l.notes.length > 0;
  });
  if (melodyLayers.length === 0) return null;

  var allPitches = [];
  var maxBeats = 0;
  melodyLayers.forEach(function(layer) {
    var b = 0;
    layer.notes.forEach(function(n) {
      allPitches.push(n.pitch);
      if (n.slide_to != null) allPitches.push(n.slide_to);
      b += n.beats + (n.slide_beats || 0);
    });
    if (b > maxBeats) maxBeats = b;
  });

  var minP = Math.min.apply(null, allPitches) - 3;
  var maxP = Math.max.apply(null, allPitches) + 3;
  var range = maxP - minP + 1;

  var cellW = 28;
  var cellH = 8;
  var leftM = 44;
  var topM = 18;
  var svgW = leftM + Math.ceil(maxBeats) * cellW + 16;
  var svgH = topM + range * cellH + 8;

  var parts = [];
  parts.push('<svg xmlns="http://www.w3.org/2000/svg" width="' + svgW + '" height="' + svgH +
             '" style="font-family:monospace;font-size:9px">');
  parts.push('<rect x="0" y="0" width="' + svgW + '" height="' + svgH + '" fill="#080810"/>');

  // Grid rows
  for (var p = minP; p <= maxP; p++) {
    var y = topM + (maxP - p) * cellH;
    var isC = (p % 12 === 0);
    var color = isC ? '#2a2a3a' : '#151520';
    parts.push('<line x1="' + leftM + '" y1="' + y + '" x2="' + svgW + '" y2="' + y +
               '" stroke="' + color + '" stroke-width="' + (isC ? 1 : 0.5) + '"/>');
    if (isC || p === minP || p === maxP) {
      parts.push('<text x="' + (leftM - 4) + '" y="' + (y + 3) +
                 '" fill="#555" text-anchor="end">' + midiName(p) + '</text>');
    }
  }

  // Grid columns
  for (var b = 0; b <= Math.ceil(maxBeats); b++) {
    var x = leftM + b * cellW;
    parts.push('<line x1="' + x + '" y1="' + topM + '" x2="' + x + '" y2="' + svgH +
               '" stroke="#1a1a28" stroke-width="0.5"/>');
    if (b % 4 === 0) {
      parts.push('<text x="' + x + '" y="' + (topM - 4) + '" fill="#555" text-anchor="middle">' + b + '</text>');
    }
  }

  // Draw notes
  melodyLayers.forEach(function(layer) {
    var baseColor = _LAYER_COLORS['expressive_melody'];
    var cursor = 0;
    layer.notes.forEach(function(n) {
      var pitch = n.pitch;
      var beats = n.beats;
      var vel = n.velocity != null ? n.velocity : 0.7;
      var opacity = 0.3 + vel * 0.7;

      var nx = leftM + cursor * cellW;
      var ny = topM + (maxP - pitch) * cellH;
      var nw = beats * cellW;

      parts.push('<rect x="' + nx + '" y="' + (ny - cellH + 1) + '" width="' + Math.max(1, nw - 1) +
                 '" height="' + (cellH - 1) + '" rx="2" fill="' + baseColor + '" opacity="' + opacity.toFixed(2) + '"/>');

      if (n.vibrato && n.vibrato > 0.05) {
        parts.push('<line x1="' + nx + '" y1="' + (ny - cellH + 1) + '" x2="' + (nx + nw - 1) +
                   '" y2="' + (ny - cellH + 1) + '" stroke="#ff0" stroke-width="1.5" opacity="0.5" stroke-dasharray="2,2"/>');
      }

      cursor += beats;

      if (n.slide_to != null && n.slide_beats) {
        var slideBeats = n.slide_beats;
        var sx1 = leftM + cursor * cellW;
        var sy1 = topM + (maxP - pitch) * cellH - cellH / 2;
        var sx2 = leftM + (cursor + slideBeats) * cellW;
        var sy2 = topM + (maxP - n.slide_to) * cellH - cellH / 2;
        var cpx = (sx1 + sx2) / 2;
        parts.push('<path d="M' + sx1 + ',' + sy1 + ' C' + cpx + ',' + sy1 + ' ' + cpx + ',' + sy2 + ' ' + sx2 + ',' + sy2 +
                   '" stroke="#f84" stroke-width="2" fill="none" opacity="0.8"/>');
        parts.push('<circle cx="' + sx2 + '" cy="' + sy2 + '" r="2.5" fill="#f84" opacity="0.8"/>');
        cursor += slideBeats;
      }
    });
  });

  parts.push('</svg>');

  // Legend for non-melodic layers
  var legendParts = [];
  config.layers.forEach(function(l) {
    if (l.type === 'expressive_melody') return;
    var col = _LAYER_COLORS[l.type] || '#888';
    var info = l.type;
    if (l.freq) info += ' (' + Math.round(l.freq) + ' Hz)';
    if (l.chord) info += ' (chord)';
    legendParts.push('<span class="pr-legend-item"><span class="pr-legend-swatch" style="background:' + col + '"></span>' + esc(info) + '</span>');
  });

  var html = '<div class="piano-roll">' + parts.join('');
  if (legendParts.length > 0) {
    html += '<div class="pr-legend">' + legendParts.join('') + '</div>';
  }
  html += '</div>';
  return html;
}
