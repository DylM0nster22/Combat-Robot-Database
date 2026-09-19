/* Combat Robot Database — client behaviour.
   Three independent pieces: theme toggle (every page), search (search.html),
   calculators (calculators.html). Each bails out quietly if its page elements
   are absent, so one script tag serves the whole site. */

(function theme() {
  var btn = document.getElementById('theme-toggle');
  if (!btn) return;
  btn.addEventListener('click', function () {
    var root = document.documentElement;
    var next = root.dataset.theme === 'light' ? 'dark' : 'light';
    root.dataset.theme = next;
    try { localStorage.setItem('crdb-theme', next); } catch (e) {}
  });
})();

/* ------------------------------------------------------------------ search */

(function search() {
  var input = document.getElementById('q');
  if (!input) return;

  var resultsEl = document.getElementById('results');
  var countEl = document.getElementById('count');
  var typeEl = document.getElementById('f-type');
  var classEl = document.getElementById('f-class');
  var clearEl = document.getElementById('f-clear');
  var data = null;

  var TYPE_LABEL = {
    weight_class: 'Weight class', archetype: 'Archetype', component: 'Component',
    material: 'Material', formula: 'Formula', bot: 'Robot', event: 'Event',
    supplier: 'Supplier', ruleset: 'Ruleset', term: 'Term', kit: 'Kit'
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  fetch('data/index.json')
    .then(function (r) { return r.json(); })
    .then(function (json) {
      data = json;
      // Build each record's searchable text once, not on every keystroke.
      data.entities.forEach(function (e) {
        e._hay = (e.name + ' ' + e.summary + ' ' + (e.tags || []).join(' ') + ' ' +
                  e.id + ' ' + (e.spec_keys || []).join(' ')).toLowerCase();
      });
      data.chunks.forEach(function (c) {
        c._hay = (c.title + ' ' + c.section + ' ' + c.preview + ' ' +
                  (c.tags || []).join(' ')).toLowerCase();
      });

      var types = {};
      data.entities.forEach(function (e) { types[e.type] = (types[e.type] || 0) + 1; });
      Object.keys(types).sort().forEach(function (t) {
        var o = document.createElement('option');
        o.value = t; o.textContent = (TYPE_LABEL[t] || t) + ' (' + types[t] + ')';
        typeEl.appendChild(o);
      });

      var classes = {};
      data.entities.forEach(function (e) {
        (e.weight_classes || []).forEach(function (w) { classes[w] = (classes[w] || 0) + 1; });
      });
      Object.keys(classes).sort().forEach(function (w) {
        var o = document.createElement('option');
        o.value = w; o.textContent = w + ' (' + classes[w] + ')';
        classEl.appendChild(o);
      });

      var params = new URLSearchParams(location.search);
      if (params.get('q')) input.value = params.get('q');
      run();
    })
    .catch(function () {
      resultsEl.innerHTML = '<div class="empty">Could not load the search index. ' +
        'If you opened this file directly from disk, serve the folder instead ' +
        '(<code>python3 -m http.server</code>) — browsers block local fetch().</div>';
    });

  function score(record, terms, hay) {
    var total = 0;
    for (var i = 0; i < terms.length; i++) {
      var idx = hay.indexOf(terms[i]);
      if (idx === -1) return -1;           // every term must appear
      total += idx < 40 ? 3 : 1;           // early match ranks higher
    }
    return total;
  }

  function run() {
    if (!data) return;
    var query = input.value.trim().toLowerCase();
    var terms = query.split(/\s+/).filter(Boolean);
    var wantType = typeEl.value;
    var wantClass = classEl.value;

    var ents = data.entities.filter(function (e) {
      if (wantType && e.type !== wantType) return false;
      if (wantClass && (e.weight_classes || []).indexOf(wantClass) === -1) return false;
      return true;
    });
    var chunks = data.chunks.filter(function (c) {
      if (wantType) return false;          // type filter only applies to entities
      if (wantClass && (c.weight_classes || []).indexOf(wantClass) === -1) return false;
      return true;
    });

    if (terms.length) {
      ents = ents.map(function (e) { return [score(e, terms, e._hay), e]; })
                 .filter(function (p) { return p[0] >= 0; })
                 .sort(function (a, b) { return b[0] - a[0]; })
                 .map(function (p) { return p[1]; });
      chunks = chunks.map(function (c) { return [score(c, terms, c._hay), c]; })
                     .filter(function (p) { return p[0] >= 0; })
                     .sort(function (a, b) { return b[0] - a[0]; })
                     .map(function (p) { return p[1]; });
    }

    var total = ents.length + chunks.length;
    countEl.textContent = query || wantType || wantClass
      ? total + ' result' + (total === 1 ? '' : 's')
      : data.entities.length + ' entries and ' + data.chunks.length + ' guides — start typing';

    var html = ents.slice(0, 60).map(function (e) {
      return '<div class="result"><h3><a href="e/' + esc(e.id) + '.html">' + esc(e.name) +
        '</a></h3><p>' + esc(e.summary) + '</p><div class="meta">' +
        esc(TYPE_LABEL[e.type] || e.type) +
        ((e.weight_classes || []).length ? ' · ' + esc(e.weight_classes.join(', ')) : '') +
        ' · <code>' + esc(e.id) + '</code></div></div>';
    }).join('');

    html += chunks.slice(0, 40).map(function (c) {
      return '<div class="result"><h3><a href="g/' + esc(c.id) + '.html">' + esc(c.title) +
        '</a></h3><p>' + esc(c.preview.slice(0, 200)) + '…</p><div class="meta">Guide · ' +
        esc(c.section || c.topic_id) + ' · ' + c.word_count + ' words</div></div>';
    }).join('');

    resultsEl.innerHTML = html || '<div class="empty">Nothing matched. Try fewer or broader words.</div>';
  }

  var timer;
  input.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(run, 110);
  });
  typeEl.addEventListener('change', run);
  classEl.addEventListener('change', run);
  clearEl.addEventListener('click', function () {
    input.value = ''; typeEl.value = ''; classEl.value = ''; run(); input.focus();
  });
})();

/* ------------------------------------------------------------- calculators */

(function calculators() {
  var host = document.getElementById('calcs');
  if (!host) return;

  var r = function (n, p) { var f = Math.pow(10, p); return Math.round(n * f) / f; };

  // These mirror agent/kb.py exactly so the site, the MCP server and the
  // Discord bot all give the same answer for the same inputs.
  var CALCS = [
    {
      id: 'tip_speed', name: 'Tip speed',
      desc: 'How fast the outer edge of a spinner is travelling. The headline number for any spinner; most competitive antweights land in the 70–110 m/s range.',
      fields: [
        { k: 'rpm', label: 'Weapon RPM', v: 20000 },
        { k: 'radius_mm', label: 'Weapon radius (mm)', v: 45 }
      ],
      run: function (i) {
        var omega = i.rpm * 2 * Math.PI / 60;
        var v = omega * (i.radius_mm / 1000);
        return {
          rows: {
            'Angular velocity (rad/s)': r(omega, 1),
            'Tip speed (m/s)': r(v, 2),
            'Tip speed (ft/s)': r(v * 3.28084, 1),
            'Tip speed (mph)': r(v * 2.23694, 1)
          }
        };
      }
    },
    {
      id: 'moi', name: 'Moment of inertia',
      desc: 'How hard a weapon is to spin up — and how much energy it holds once spinning. Mass far from the axis counts enormously more than mass near it.',
      fields: [
        { k: 'shape', label: 'Shape', v: 'disc', options: ['disc', 'ring', 'annulus', 'bar', 'bar_end', 'point'] },
        { k: 'mass_g', label: 'Mass (g)', v: 120 },
        { k: 'dim_mm', label: 'Diameter, or bar length (mm)', v: 90 },
        { k: 'inner_dim_mm', label: 'Inner diameter (mm, annulus only)', v: 0 }
      ],
      run: function (i) {
        var m = i.mass_g / 1000, d = i.dim_mm / 1000, rad = d / 2, ri = i.inner_dim_mm / 2000, I, f;
        if (i.shape === 'disc') { I = 0.5 * m * rad * rad; f = 'I = ½ m r²'; }
        else if (i.shape === 'ring') { I = m * rad * rad; f = 'I = m r²'; }
        else if (i.shape === 'annulus') { I = 0.5 * m * (rad * rad + ri * ri); f = 'I = ½ m (ro² + ri²)'; }
        else if (i.shape === 'bar') { I = m * d * d / 12; f = 'I = 1/12 m L² (about centre)'; }
        else if (i.shape === 'bar_end') { I = m * d * d / 3; f = 'I = 1/3 m L² (about one end)'; }
        else { I = m * rad * rad; f = 'I = m r² (point mass)'; }
        return { rows: { 'Formula': f, 'MOI (kg·m²)': I.toExponential(3), 'MOI (g·cm²)': r(I * 1e7, 1) } };
      }
    },
    {
      id: 'ke', name: 'Kinetic energy',
      desc: 'Energy stored in a spinning weapon. A competitive 1 lb spinner typically stores 50–350 J — enough to break bone, which is why weapon locks exist.',
      fields: [
        { k: 'moi_kg_m2', label: 'MOI (kg·m²)', v: 0.0001215, step: 'any' },
        { k: 'rpm', label: 'Weapon RPM', v: 20000 }
      ],
      run: function (i) {
        var omega = i.rpm * 2 * Math.PI / 60;
        var j = 0.5 * i.moi_kg_m2 * omega * omega;
        return {
          rows: { 'Energy (J)': r(j, 1), 'Energy (ft·lb)': r(j * 0.737562, 1) },
          note: j > 150 ? 'That is a serious amount of stored energy. Treat the robot as live whenever the battery is connected.' : null
        };
      }
    },
    {
      id: 'spinup', name: 'Spin-up time',
      desc: 'Roughly how long the weapon takes to reach speed. Anything past about 3 seconds means you will get box-rushed before the weapon is useful.',
      fields: [
        { k: 'moi_kg_m2', label: 'Weapon MOI (kg·m²)', v: 0.0001215, step: 'any' },
        { k: 'rpm_target', label: 'Target RPM', v: 20000 },
        { k: 'motor_kv', label: 'Motor KV', v: 2000 },
        { k: 'volts', label: 'Pack voltage (V)', v: 11.1 },
        { k: 'stall_current_a', label: 'Stall current (A)', v: 30 },
        { k: 'efficiency', label: 'Avg torque as fraction of stall', v: 0.6, step: '0.05' }
      ],
      run: function (i) {
        if (i.motor_kv <= 0) return { rows: { Error: 'KV must be > 0' } };
        var kt = 9.5493 / i.motor_kv;
        var stall = kt * i.stall_current_a;
        var avg = stall * i.efficiency;
        var omega = i.rpm_target * 2 * Math.PI / 60;
        var noLoad = i.motor_kv * i.volts;
        return {
          rows: {
            'Kt (N·m/A)': r(kt, 5),
            'Stall torque (N·m)': r(stall, 4),
            'No-load RPM': Math.round(noLoad),
            'Spin-up (s)': r(i.moi_kg_m2 * omega / avg, 2)
          },
          note: i.rpm_target > noLoad * 0.9
            ? 'Target RPM is close to no-load RPM — the real spin-up will be far longer than this estimate, and the weapon may never reach that speed under load.'
            : 'Assumes constant average torque. Real spin-up runs longer.'
        };
      }
    },
    {
      id: 'drive', name: 'Drive speed',
      desc: 'Top speed from motor RPM, gearing and wheel size. Most competitive antweights run somewhere around 2–5 m/s.',
      fields: [
        { k: 'motor_rpm', label: 'Output RPM (after gearbox)', v: 500 },
        { k: 'wheel_dia_mm', label: 'Wheel diameter (mm)', v: 32 },
        { k: 'gear_ratio', label: 'Further reduction (1 = none)', v: 1 }
      ],
      run: function (i) {
        var wheelRpm = i.motor_rpm / (i.gear_ratio || 1);
        var v = wheelRpm * Math.PI * (i.wheel_dia_mm / 1000) / 60;
        return { rows: { 'Wheel RPM': r(wheelRpm, 1), 'Speed (m/s)': r(v, 2), 'Speed (mph)': r(v * 2.23694, 1) } };
      }
    },
    {
      id: 'traction', name: 'Traction limit',
      desc: 'The most force your robot can push with before the wheels slip. Gearing past this point buys nothing — grip is the real limit in a pushing match.',
      fields: [
        { k: 'weight_g', label: 'Robot weight (g)', v: 454 },
        { k: 'friction_coefficient', label: 'Tyre friction coefficient', v: 1.0, step: '0.05' },
        { k: 'drive_wheels_fraction', label: 'Weight on driven wheels', v: 1.0, step: '0.05' }
      ],
      run: function (i) {
        var n = (i.weight_g / 1000) * 9.80665 * i.drive_wheels_fraction;
        var f = n * i.friction_coefficient;
        return { rows: { 'Normal force (N)': r(n, 2), 'Max push (N)': r(f, 2), 'Max push (lbf)': r(f * 0.224809, 2) } };
      }
    },
    {
      id: 'bite', name: 'Bite depth',
      desc: 'How deep each tooth can cut before the next one arrives. Fewer teeth bite deeper — which is why many hard-hitting spinners run one or two teeth, not six.',
      fields: [
        { k: 'weapon_rpm', label: 'Weapon RPM', v: 20000 },
        { k: 'tooth_count', label: 'Number of teeth', v: 2 },
        { k: 'closing_speed_m_s', label: 'Closing speed (m/s)', v: 1.5, step: '0.1' }
      ],
      run: function (i) {
        var hits = i.weapon_rpm / 60 * Math.max(1, i.tooth_count);
        return {
          rows: { 'Impacts per second': r(hits, 1), 'Max bite depth (mm)': r(i.closing_speed_m_s / hits * 1000, 2) },
          note: 'Theoretical maximum. Armour hardness, wedge angle and ground clearance all reduce real bite.'
        };
      }
    },
    {
      id: 'gyro', name: 'Gyroscopic torque',
      desc: 'The torque a spinning weapon fights you with when you turn. This is what makes a vertical spinner lift a wheel and "gyro dance" across the floor.',
      fields: [
        { k: 'moi_kg_m2', label: 'Weapon MOI (kg·m²)', v: 0.0001215, step: 'any' },
        { k: 'weapon_rpm', label: 'Weapon RPM', v: 20000 },
        { k: 'turn_rate_deg_s', label: 'Turn rate (deg/s)', v: 180 }
      ],
      run: function (i) {
        var t = i.moi_kg_m2 * (i.weapon_rpm * 2 * Math.PI / 60) * (i.turn_rate_deg_s * Math.PI / 180);
        return {
          rows: { 'Precession torque (N·m)': r(t, 4) },
          note: 'Acts perpendicular to both spin and turn. Turn more gently, or lower weapon MOI, to tame it.'
        };
      }
    },
    {
      id: 'battery', name: 'Battery check',
      desc: 'Whether a pack can actually supply what the robot demands. Voltage sag, not capacity, is what usually ends a 1 lb robot mid-match.',
      fields: [
        { k: 'capacity_mah', label: 'Capacity (mAh)', v: 450 },
        { k: 'c_rating', label: 'C rating (as marketed)', v: 75 },
        { k: 'cells_s', label: 'Cells in series (S)', v: 3 },
        { k: 'average_draw_a', label: 'Average draw (A)', v: 12 }
      ],
      run: function (i) {
        var ah = i.capacity_mah / 1000;
        var cont = ah * i.c_rating;
        var v = i.cells_s * 3.7;
        var headroom = i.average_draw_a > 0 ? cont / i.average_draw_a : null;
        return {
          rows: {
            'Nominal voltage (V)': r(v, 1),
            'Energy (Wh)': r(ah * v, 2),
            'Rated continuous (A)': r(cont, 1),
            'Headroom ratio': headroom ? r(headroom, 2) : '—',
            'Runtime estimate (min)': i.average_draw_a > 0 ? r(ah / i.average_draw_a * 60, 1) : '—'
          },
          note: headroom && headroom < 1.5
            ? 'Under 1.5× headroom — expect voltage sag and possible brownouts on weapon spin-up. Marketing C ratings are optimistic.'
            : 'Marketing C ratings are optimistic; real-world headroom is lower than the number suggests.'
        };
      }
    },
    {
      id: 'budget', name: 'Weight budget',
      desc: 'Turn a percentage split into grams against the class limit. A 1 lb antweight is 454 g and every gram is contested.',
      fields: [
        { k: 'total_g', label: 'Class limit (g)', v: 454 },
        { k: 'weapon', label: 'Weapon %', v: 32 },
        { k: 'drive', label: 'Drive %', v: 20 },
        { k: 'armor_chassis', label: 'Armour + chassis %', v: 24 },
        { k: 'electronics', label: 'Electronics %', v: 12 },
        { k: 'battery', label: 'Battery %', v: 8 },
        { k: 'fasteners_misc', label: 'Fasteners + misc %', v: 4 }
      ],
      run: function (i) {
        var keys = ['weapon', 'drive', 'armor_chassis', 'electronics', 'battery', 'fasteners_misc'];
        var rows = {}, sum = 0;
        keys.forEach(function (k) {
          rows[k.replace(/_/g, ' ') + ' (g)'] = r(i.total_g * i[k] / 100, 1);
          sum += i[k];
        });
        return {
          rows: rows,
          note: Math.abs(sum - 100) > 0.01
            ? 'Your percentages add up to ' + r(sum, 1) + '%, not 100%.'
            : 'Leave yourself 3–5% of slack — robots always come in heavier than the CAD says.'
        };
      }
    }
  ];

  CALCS.forEach(function (calc) {
    var el = document.createElement('div');
    el.className = 'calc';
    var fields = calc.fields.map(function (f) {
      if (f.options) {
        return '<div><label for="' + calc.id + '-' + f.k + '">' + f.label + '</label>' +
          '<select id="' + calc.id + '-' + f.k + '" data-k="' + f.k + '">' +
          f.options.map(function (o) {
            return '<option value="' + o + '"' + (o === f.v ? ' selected' : '') + '>' + o + '</option>';
          }).join('') + '</select></div>';
      }
      return '<div><label for="' + calc.id + '-' + f.k + '">' + f.label + '</label>' +
        '<input id="' + calc.id + '-' + f.k + '" type="number" step="' + (f.step || 'any') +
        '" value="' + f.v + '" data-k="' + f.k + '"></div>';
    }).join('');

    el.innerHTML = '<h3>' + calc.name + '</h3><p class="desc">' + calc.desc + '</p>' +
      '<div class="fields">' + fields + '</div><div class="out" id="' + calc.id + '-out"></div>';
    host.appendChild(el);

    var out = el.querySelector('#' + calc.id + '-out');
    var inputs = el.querySelectorAll('input, select');

    function update() {
      var values = {};
      inputs.forEach(function (input) {
        values[input.dataset.k] = input.type === 'number' ? parseFloat(input.value) || 0 : input.value;
      });
      var result;
      try { result = calc.run(values); }
      catch (e) { out.innerHTML = '<div class="note">Could not compute with those inputs.</div>'; return; }
      var html = Object.keys(result.rows).map(function (k) {
        return '<div class="row"><span class="k">' + k + '</span><span class="v">' + result.rows[k] + '</span></div>';
      }).join('');
      if (result.note) html += '<div class="note">' + result.note + '</div>';
      out.innerHTML = html;
    }

    inputs.forEach(function (input) { input.addEventListener('input', update); });
    update();
  });
})();
