/* Drought platform prototype.
 * Hash routes:  #/?frt=YYYY-MM-DD&w=0..4&view=karte|liste
 *               #/regionen/<id>/<aktuelle-lage|jahresvergleich|zeitreihe>?frt=…&f=<row>
 * The issue date (frt) travels with every link, so drill-down keeps it fixed.
 */
(() => {
'use strict';

/* ---------------------------------------------------------------- constants */
const DAY = 864e5, WEEK = 7 * DAY;
const MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
const LEVELS = ['Nicht trocken', 'Leicht trocken', 'Trocken', 'Sehr trocken', 'Extrem trocken'];
const TABS = { 'aktuelle-lage': 'Aktuelle Lage', 'jahresvergleich': 'Jahresvergleich', 'zeitreihe': 'Zeitreihe' };
const HIST_WEEKS = 24;
const OFFICIAL = 'https://www.trockenheit.admin.ch/de';

/* Rows on the region page. `v` is the key in region/<id>.json. */
const ROWS = [
  { key: 'cdi', label: 'Trockenheitsindex', kind: 'cdi', v: 'cdi',
    link: ['Details zum Trockenheitsindex', `${OFFICIAL}/trockenheit/trockenheitsindex`],
    details: 'Kombinierter Trockenheitsindex (CDI) der Region, Stufe 1 bis 5. Ausgefüllte Felder sind beobachtet, schraffierte Felder sind die Prognose (Median).' },
  { key: 'niederschlag', label: 'Niederschlagssumme', kind: 'bars', v: 'precip_sum_1m', unit: 'mm',
    color: '--factor-precip', light: '--factor-precip-l', thr: true,
    link: ['Mehr zu diesem Einflussfaktor', `${OFFICIAL}/faktoren/niederschlag/niederschlagssummen`],
    sub: 'Niederschlagssumme der letzten 30 Tage',
    details: 'Balken: Niederschlagssumme der letzten 30 Tage. Schraffiert: Prognose (Median) mit 10–90 %-Bereich. Trockenheitsschwelle: 10. Perzentil 1991–2020 für die Kalenderwoche. Minimalwert: tiefster Wert 1991–2020.' },
  { key: 'bodenfeuchte', label: 'Bodenfeuchte', kind: 'bars', v: 'soil_moisture_ufc', unit: '%nFK',
    color: '--factor-moisture', light: '--factor-moisture-l', thr: true, yMax: 100,
    link: ['Mehr zu diesem Einflussfaktor', `${OFFICIAL}/faktoren/boden/modellierte-bodenfeuchte`],
    sub: '%nFK (pflanzenverfügbares Wasser)',
    details: 'Modellierte Bodenfeuchte in % der nutzbaren Feldkapazität. Schraffiert: Prognose (Median) mit 10–90 %-Bereich.' },
  { key: 'verdunstung', label: 'Verdunstung', kind: 'bars', v: 'eta', line: 'etp', unit: 'mm/Woche',
    color: '--factor-evap', light: '--factor-evap-l', thr: true, isNew: true,
    sub: 'Tatsächliche Verdunstung pro Woche (Balken) und potenzielle Verdunstung (Linie)',
    details: 'Neue Zeile im Prototyp. Balken: tatsächliche Verdunstung (Summe pro Woche). Linie: potenzielle Verdunstung, also das, was bei ausreichend Wasser verdunsten würde. Die Lücke zwischen Linie und Balken zeigt den Wasserstress. Schraffiert: Prognose (Median) mit 10–90 %-Bereich.' },
  { key: 'vegetation', label: 'Vegetation', kind: 'bars', v: 'vhi', unit: 'VHI',
    color: '--factor-vegetation', light: '--factor-vegetation-l', thr: true, yMax: 100, noForecast: true,
    link: ['Mehr zu diesem Einflussfaktor', `${OFFICIAL}/faktoren/vegetation/vegetationszustand-vhi`],
    sub: 'von 0 (extrem gestresst) bis 100 (optimaler Zustand)',
    details: 'Vegetation Health Index aus Satellitendaten. Für die Vegetation gibt es keine Prognose.' }
];

/* Combined row (switch "kombinieren"): precipitation up, evaporation down, both as
   30-day sums on one mm scale, plus the water balance P − ET. Replaces the two rows. */
const BAL = { key: 'bilanz', label: 'Niederschlag und Verdunstung', navLabel: 'Niederschlag & Verdunstung', kind: 'balance', v: 'wb',
  unit: 'mm', color: '--factor-precip', light: '--factor-precip-l', thr: true, line: 'etp30', wbToggle: true, isNew: true,
  sub: 'Summen der letzten 30 Tage: Niederschlag nach oben, tatsächliche Verdunstung nach unten. Punkte: Wasserbilanz (Niederschlag − Verdunstung).',
  subYear: 'Wasserbilanz der letzten 30 Tage (Niederschlag − tatsächliche Verdunstung) pro Jahr. Unter null verdunstet mehr Wasser, als fällt.',
  details: 'Niederschlag (blau) und tatsächliche Verdunstung (violett) als Summen der letzten 30 Tage, auf derselben Skala. Die Verdunstung wird aus vier Wochensummen hochgerechnet (× 30/28). In den Prognosewochen sind die Wochen vor dem Prognosezeitpunkt beobachtet und die übrigen prognostiziert. Die 10–90 %-Bereiche der Verdunstung sind als Summe der Wochenquantile angenähert, also eher zu breit. Linie unten: potenzielle Verdunstung. Punkte: Wasserbilanz; hohle Punkte sind Prognosen (Median).' };
const ACC = 30 / 28;  // four weekly sums -> 30-day sum

function sum4(arr) {
  return arr.map((_, i) => {
    if (i < 3) return null;
    let s = 0;
    for (let k = i - 3; k <= i; k++) { if (arr[k] == null) return null; s += arr[k]; }
    return s * ACC;
  });
}
/* Add 30-day evaporation sums and the water balance to a region record (once). */
function enrich(rec) {
  if (rec.obs.eta30) return;
  rec.obs.eta30 = sum4(rec.obs.eta);
  rec.obs.etp30 = rec.obs.etp ? sum4(rec.obs.etp) : null;
  rec.obs.wb = rec.obs.precip_sum_1m.map((p, i) => p == null || rec.obs.eta30[i] == null ? null : p - rec.obs.eta30[i]);
}
/* Forecast 30-day sums for one issue date: observed weeks before it plus forecast weeks. */
function balanceFc(rec, frt) {
  const f = rec.fc[iso(frt)];
  if (!f) return {};
  if (f._bal) return f._bal;
  const idx = new Map(rec.dates.map((d, i) => [ts(d), i]));
  const obsAt = (k, t) => { const i = idx.get(t); return i == null ? null : rec.obs[k]?.[i] ?? null; };
  const acc = key => {
    const fk = f[key];
    if (!fk) return null;
    const trip = Array.isArray(fk[0]) ? fk : [fk, fk, fk];
    return [0, 1, 2].map(q => [0, 1, 2, 3].map(l => {
      let s = 0;
      for (let k = l - 3; k <= l; k++) {
        const v = k < 0 ? obsAt(key, frt + k * WEEK) : trip[q][k];
        if (v == null) return null;
        s += v;
      }
      return s * ACC;
    }));
  };
  const eta30 = acc('eta'), etp = acc('etp'), P = f.precip_sum_1m;
  const diff = (a, b) => a == null || b == null ? null : a - b;
  const wb = P && eta30 ? [0, 1, 2].map(q => [0, 1, 2, 3].map(l => diff(P[q][l], eta30[2 - q][l]))) : null;
  return (f._bal = { eta30, etp30: etp ? etp[1] : null, wb });
}

/* ---------------------------------------------------------------- utils */
const NS = 'http://www.w3.org/2000/svg';
const $ = (s, el = document) => el.querySelector(s);
function S(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs || {}) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function H(html) { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; }
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const ts = d => Date.parse(d + 'T00:00:00Z');
const iso = t => new Date(t).toISOString().slice(0, 10);
const pad = n => String(n).padStart(2, '0');
const dmy = t => { const d = new Date(t); return `${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)}.${d.getUTCFullYear()}`; };
const dm = t => { const d = new Date(t); return `${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)}.`; };
function isoWeek(t) {
  const d = new Date(t); d.setUTCDate(d.getUTCDate() + 3 - ((d.getUTCDay() + 6) % 7));
  const y = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  return 1 + Math.round(((d - y) / DAY - 3 + ((y.getUTCDay() + 6) % 7)) / 7);
}
function isoYear(t) { const d = new Date(t); d.setUTCDate(d.getUTCDate() + 3 - ((d.getUTCDay() + 6) % 7)); return d.getUTCFullYear(); }
const num = (x, d = 1) => x == null ? '–' : (x < 0 ? '−' : '') + Math.abs(x).toFixed(d);
const signed = t => (t < 0 ? '−' : '') + (Number.isInteger(t) ? Math.abs(t) : Math.abs(t).toFixed(1));
const cssv = name => `var(${name})`;

/* tooltip */
const tip = $('#tip');
function showTip(html, ev) {
  tip.innerHTML = html; tip.hidden = false;
  const r = tip.getBoundingClientRect();
  let x = ev.clientX + 16, y = ev.clientY + 16;
  if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 16;
  if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - 16;
  tip.style.left = Math.max(8, x) + 'px'; tip.style.top = Math.max(8, y) + 'px';
}
const hideTip = () => { tip.hidden = true; };
function bindTip(el, fn) {
  el.addEventListener('pointermove', ev => showTip(fn(), ev));
  el.addEventListener('pointerleave', hideTip);
}
const swatch = c => `<span class="k" style="background:${c}"></span>`;

/* hatch patterns, one per colour */
function makePatterns() {
  const defs = $('#patterns');
  const mk = (id, color) => {
    const p = S('pattern', { id, patternUnits: 'userSpaceOnUse', width: 7, height: 7, patternTransform: 'rotate(45)' }, defs);
    S('rect', { width: 7, height: 7, style: `fill:${color}` }, p);
    S('line', { x1: 0, y1: 0, x2: 0, y2: 7, style: 'stroke:rgba(19,27,34,.55)', 'stroke-width': 2.4 }, p);
  };
  for (let k = 1; k <= 5; k++) mk(`hatch-lv${k}`, cssv(`--cdi-${k}`));
  for (const r of ROWS) if (r.color) mk(`hatch-${r.key}`, cssv(r.color));
}

/* ---------------------------------------------------------------- data */
const DATA = { overview: null, geo: null, regions: new Map() };
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}
function region(id) {
  if (!DATA.regions.has(id)) DATA.regions.set(id, getJSON(`data/region/${id}.json`));
  return DATA.regions.get(id);
}
const regionName = id => DATA.geo.regions.find(r => r.id === +id)?.name ?? `Region ${id}`;

/* ---------------------------------------------------------------- routing */
const state = { toggles: {}, verify: false, details: {} };
function parseRoute() {
  const raw = location.hash.slice(1) || '/';
  const [path, qs] = raw.split('?');
  const q = new URLSearchParams(qs || '');
  const parts = path.split('/').filter(Boolean);
  const frts = DATA.overview.frts;
  let frt = q.get('frt');
  if (!frts.includes(frt)) frt = frts[frts.length - 1];
  if (parts[0] === 'regionen' && parts[1]) {
    return { page: 'region', rid: parts[1], tab: TABS[parts[2]] ? parts[2] : 'aktuelle-lage', frt, f: q.get('f'), kombi: q.get('kombi') === '1', unsicher: q.get('unsicher') === '1' };
  }
  return { page: 'home', frt, w: Math.min(4, Math.max(0, +(q.get('w') ?? 0) || 0)), view: q.get('view') === 'liste' ? 'liste' : 'karte' };
}
let route;
function link(path, params) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null && v !== '') q.set(k, v);
  return `#${path}?${q}`;
}
const homeLink = (over = {}) => link('/', { frt: route.frt, w: route.w || null, view: route.view === 'liste' ? 'liste' : null, ...over });
const regionLink = (rid, tab = 'aktuelle-lage', over = {}) => link(`/regionen/${rid}/${tab}`, { frt: route.frt, kombi: route.kombi ? 1 : null, unsicher: route.unsicher ? 1 : null, ...over });

function frtControl(id) {
  const frts = DATA.overview.frts, i = frts.indexOf(route.frt);
  const opts = frts.map(f => `<option value="${f}"${f === route.frt ? ' selected' : ''}>${dmy(ts(f) - DAY)}</option>`).join('');
  return `<span class="frt-pick">
    <button type="button" class="frt-step" data-step="-1" aria-label="Eine Woche zurück"${i <= 0 ? ' disabled' : ''}>‹</button>
    <select class="frt-select" id="${id}" aria-label="Prognosezeitpunkt">${opts}</select>
    <button type="button" class="frt-step" data-step="1" aria-label="Eine Woche vor"${i >= frts.length - 1 ? ' disabled' : ''}>›</button>
  </span>`;
}
function wireFrt(root, go) {
  const sel = root.querySelector('.frt-select');
  sel.addEventListener('change', () => go(sel.value));
  root.querySelectorAll('.frt-step').forEach(b => b.addEventListener('click', () => {
    const frts = DATA.overview.frts, i = frts.indexOf(route.frt) + +b.dataset.step;
    if (i >= 0 && i < frts.length) go(frts[i]);
  }));
}

/* ================================================================ LANDING */
function renderHome() {
  const frt = ts(route.frt);
  const weeks = [frt - WEEK, frt, frt + WEEK, frt + 2 * WEEK, frt + 3 * WEEK];
  const cdi = DATA.overview.cdi[route.frt];
  const app = $('#app');
  app.innerHTML = '';

  const hero = H(`<section class="hero"><div class="wrap">
    <div class="hero-head">
      <div>
        <h1>Trockenheit <span class="sub">Situation bis ${frtControl('frt-home')}</span></h1>
        <p class="hint">Klicken Sie auf die Region für genauere Informationen.</p>
        <div class="legend">
          ${LEVELS.map((l, k) => `<span class="lv"><i class="sw" style="background:var(--cdi-${k + 1})"></i>${l}</span>`).join('')}
          <a class="link" href="${OFFICIAL}/trockenheit/trockenheitsindex" target="_blank" rel="noopener">${infoIcon()} Legende</a>
        </div>
      </div>
      <button type="button" class="btn-dark" id="toggle-view">${listIcon()} ${route.view === 'liste' ? 'Karte anzeigen' : 'Liste anzeigen'}</button>
    </div>
    <div class="weekbar">
      <span class="lbl">Woche</span>
      <div class="seg" id="weeks" role="group" aria-label="Angezeigte Woche">
        ${weeks.map((t, i) => `<button type="button" data-w="${i}" aria-pressed="${i === route.w}">${i ? '<i class="fc-mark"></i>' : ''}KW ${isoWeek(t)} ${i ? 'Prognose' : 'Lage'}</button>`).join('')}
      </div>
      <span class="lbl">Prognose vom ${dmy(frt)}</span>
    </div>
    <div id="view"></div>
    <p class="updated">Aktualisiert am ${dmy(frt)}</p>
  </div></section>`);
  app.appendChild(hero);
  wireFrt(hero, f => { location.hash = homeLink({ frt: f }); });
  $('#toggle-view', hero).addEventListener('click', () => { location.hash = homeLink({ view: route.view === 'liste' ? null : 'liste' }); });
  $('#weeks', hero).addEventListener('click', ev => {
    const b = ev.target.closest('button'); if (b) location.hash = homeLink({ w: +b.dataset.w || null });
  });

  const view = $('#view', hero);
  if (route.view === 'liste') view.appendChild(listView(cdi, weeks));
  else view.appendChild(mapView(cdi, weeks));

  app.appendChild(bulletin(cdi, weeks));
  app.appendChild(factorCards());
}

function mapView(cdi, weeks) {
  const G = DATA.geo, w = route.w;
  const box = H(`<div class="mapbox"><div class="map-week"><b>KW ${isoWeek(weeks[w])}</b> · ${dm(weeks[w])}–${dm(weeks[w] + 6 * DAY)}${w ? ' · Prognose' : ' · Beobachtung'}</div><span class="map-attr">© Schweizerische Eidgenossenschaft</span></div>`);
  const svg = S('svg', { viewBox: `-20 -20 ${G.w + 40} ${G.h + 40}`, role: 'img', 'aria-label': 'Karte der Trockenheitsregionen' });
  box.prepend(svg);
  for (const r of G.regions) {
    const lv = cdi[r.id]?.[w];
    const fill = lv == null ? '#dfe4e9' : w ? `url(#hatch-lv${lv})` : cssv(`--cdi-${lv}`);
    const p = S('path', { d: r.d, class: 'region', style: `fill:${fill}` }, svg);
    p.addEventListener('click', () => { location.hash = regionLink(r.id); });
    bindTip(p, () => {
      const v = cdi[r.id] || [];
      return `<b>${esc(r.name)}</b><br>${lv ? swatch(cssv(`--cdi-${lv}`)) + LEVELS[lv - 1] : 'keine Daten'}` +
        `<br><span class="m">Lage KW ${isoWeek(weeks[0])}: ${v[0] ?? '–'} · Prognose ${v.slice(1).map(x => x ?? '–').join(' → ')}</span>`;
    });
  }
  return box;
}

function listView(cdi, weeks) {
  const box = H(`<div class="list"><table><thead><tr><th>Region</th>${weeks.map((t, i) => `<th>KW ${isoWeek(t)}${i ? ' Prognose' : ' Lage'}</th>`).join('')}</tr></thead><tbody></tbody></table></div>`);
  const tb = $('tbody', box);
  const regs = [...DATA.geo.regions].sort((a, b) => a.name.localeCompare(b.name, 'de'));
  for (const r of regs) {
    const v = cdi[r.id] || [];
    const tr = H(`<tr class="r" tabindex="0"><td>${esc(r.name)}</td>${v.map((lv, i) => `<td>${lv ? `<span class="chipl"><i class="sw" style="background:${i ? `repeating-linear-gradient(45deg, var(--cdi-${lv}) 0 4px, rgba(19,27,34,.45) 4px 6px)` : `var(--cdi-${lv})`}"></i>${LEVELS[lv - 1]}</span>` : '–'}</td>`).join('')}</tr>`);
    const go = () => { location.hash = regionLink(r.id); };
    tr.addEventListener('click', go);
    tr.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
    tb.appendChild(tr);
  }
  return box;
}

function bulletin(cdi, weeks) {
  const ids = Object.keys(cdi);
  const counts = weeks.map((_, i) => [1, 2, 3, 4, 5].map(k => ids.filter(id => cdi[id][i] === k).length));
  const dry = i => counts[i][2] + counts[i][3] + counts[i][4];
  const d0 = dry(0), d3 = dry(4);
  const head = d0 === 0 && d3 === 0 ? 'Derzeit herrscht keine Trockenheit.'
    : d3 > d0 + 3 ? 'Die Trockenheit dürfte sich ausweiten.'
    : d3 < d0 - 3 ? 'Die Trockenheit dürfte zurückgehen.'
    : 'Die Trockenheitssituation hält an.';
  const worst = ids.filter(id => cdi[id][0] != null).sort((a, b) => cdi[b][0] - cdi[a][0])[0];
  const sec = H(`<section class="bulletin"><div class="wrap bulletin-in">
    <div>
      <h2>Trockenheitsbulletin</h2>
      <p class="head">${head}</p>
      <p>In der Kalenderwoche ${isoWeek(weeks[0])} war es in ${d0} von ${ids.length} Regionen trocken oder trockener (Stufe 3 und höher). Für Kalenderwoche ${isoWeek(weeks[4])} erwartet die Prognose dies in ${d3} Regionen.</p>
      <p class="auto">Automatisch aus den Daten erzeugter Text (Prototyp).</p>
      <a class="btn-outline-red" href="${regionLink(worst)}">Mehr Informationen <span aria-hidden="true">→</span></a>
    </div>
    <div class="dist"><h3>Anzahl Regionen pro Stufe</h3><div id="dist"></div></div>
  </div></section>`);
  const W = 560, rowH = 34, ml = 120;
  const svg = S('svg', { viewBox: `0 0 ${W} ${weeks.length * rowH + 4}`, role: 'img', 'aria-label': 'Anzahl Regionen pro Trockenheitsstufe' }, $('#dist', sec));
  counts.forEach((c, i) => {
    const y = i * rowH + 4;
    S('text', { x: 0, y: y + 18, style: 'font:13px var(--font);fill:var(--secondary-700)' }, svg).textContent = `KW ${isoWeek(weeks[i])} ${i ? 'Prognose' : 'Lage'}`;
    const tot = c.reduce((a, b) => a + b, 0) || 1;
    let x = ml;
    c.forEach((n, k) => {
      const w = (W - ml) * n / tot;
      if (!w) return;
      const r = S('rect', { x, y, width: Math.max(0, w - 2), height: 24, style: `fill:${i ? `url(#hatch-lv${k + 1})` : cssv(`--cdi-${k + 1}`)}` }, svg);
      bindTip(r, () => `${swatch(cssv(`--cdi-${k + 1}`))}${LEVELS[k]}: <b>${n}</b> Regionen`);
      if (w > 22) S('text', { x: x + w / 2 - 1, y: y + 17, 'text-anchor': 'middle', style: `font:600 12px var(--font);fill:${k >= 3 ? '#fff' : 'var(--secondary-900)'};pointer-events:none` }, svg).textContent = n;
      x += w;
    });
  });
  return sec;
}

function factorCards() {
  const rid = lastRegion || 42;
  const cards = [
    ['niederschlag', 'Niederschlag', 'Niederschlag spielt eine zentrale Rolle für das Entstehen, die Intensität und die Dauer von Trockenheit.', '--factor-precip'],
    ['bodenfeuchte', 'Bodenfeuchte', 'Die Bodenfeuchte zeigt, wie viel Wasser den Pflanzen im Wurzelraum zur Verfügung steht.', '--factor-moisture'],
    ['verdunstung', 'Verdunstung', 'Die Verdunstung zeigt, wie viel Wasser Boden und Pflanzen an die Luft abgeben, und wie stark Wassermangel sie bremst.', '--factor-evap', true],
    ['vegetation', 'Vegetation', 'Der Vegetationszustand aus Satellitendaten zeigt, wie stark Pflanzen unter Trockenheit leiden.', '--factor-vegetation']
  ];
  const sec = H(`<section class="factors"><div class="wrap"><h2>Einflussfaktoren</h2><div class="cards"></div></div></section>`);
  for (const [key, title, text, color, isNew] of cards) {
    const c = H(`<a class="card" href="${regionLink(rid, 'aktuelle-lage', { f: key })}">
      <div class="card-top"></div>
      <div class="card-body"><h3>${title}${isNew ? ' <span class="pill-new">Neu</span>' : ''}</h3><p>${text}</p><span class="go" aria-hidden="true">→</span></div>
    </a>`);
    const svg = S('svg', { viewBox: '0 0 300 132', preserveAspectRatio: 'none' }, $('.card-top', c));
    S('rect', { width: 300, height: 132, style: `fill:${cssv(color)}` }, svg);
    for (let i = 0; i < 24; i++) {
      const h = 22 + 70 * Math.abs(Math.sin(i * 1.7 + key.length));
      S('rect', { x: 8 + i * 12, y: 124 - h, width: 9, height: h, style: 'fill:rgba(255,255,255,.22)' }, svg);
    }
    sec.querySelector('.cards').appendChild(c);
  }
  return sec;
}

/* ================================================================ REGION */
let lastRegion = null;
async function renderRegion(keepScroll) {
  const rid = route.rid;
  lastRegion = rid;
  const app = $('#app');
  let rec;
  try { rec = await region(rid); }
  catch (e) { app.innerHTML = `<div class="wrap loading">Die Daten für Region ${esc(rid)} konnten nicht geladen werden (${esc(e.message)}).</div>`; return; }
  if (route.page !== 'region' || route.rid !== rid) return;
  enrich(rec);

  const frt = ts(route.frt);
  const rows = route.kombi
    ? ROWS.filter(r => r.key !== 'verdunstung').map(r => r.key === 'niederschlag' ? BAL : r)
    : ROWS;
  const ov = DATA.overview.cdi[route.frt][rid] || [];
  const last = ov[0], end = ov[4];
  const outlook = last == null || end == null ? ''
    : end > last ? 'Die Trockenheit dürfte sich in den nächsten Wochen verschärfen.'
    : end < last ? (last >= 3 ? 'Die Trockenheit dürfte in den nächsten Wochen nachlassen.' : 'Die Lage dürfte sich in den nächsten Wochen weiter entspannen.')
    : 'Die aktuelle Situation dürfte unverändert bleiben.';

  app.innerHTML = '';
  const head = H(`<section class="rhead"><div class="wrap">
    <div class="proto-banner">
      <span class="ic" aria-hidden="true">i</span>
      <span>Prognose vom <b>${dmy(frt)}</b> · Beobachtungen bis ${frtControl('frt-region')}</span>
      <label class="chk"><input type="checkbox" id="verify"${state.verify ? ' checked' : ''}> Spätere Beobachtungen einblenden</label>
      <label class="chk" title="Blendet die Prognosewochen +2 und +3 ab, weil sie laut Verifikation wenig verlässlich sind"><input type="checkbox" id="unsicher"${route.unsicher ? ' checked' : ''}> Unsicherheit anzeigen</label>
    </div>
    <div class="title-row"><h1>${esc(regionName(rid))}</h1><a class="link" href="${homeLink()}">← Zurück zur Startseite</a></div>
    <p class="outlook">${outlook} Die Einschätzung der lokalen Behörden kann davon abweichen.</p>
    <div class="tabs">${Object.entries(TABS).map(([k, l]) => `<a href="${regionLink(rid, k)}" class="${k === route.tab ? 'on' : ''}">${l}</a>`).join('')}</div>
    <nav class="subnav" aria-label="Einflussfaktoren">${rows.map((r, i) => `<button type="button" data-row="${r.key}" class="${i ? '' : 'on'}">${r.navLabel || r.label}${r.isNew ? '<i class="dot-new" title="Neu"></i>' : ''}</button>`).join('')}</nav>
  </div></section>`);
  app.appendChild(head);
  wireFrt(head, f => { location.hash = regionLink(rid, route.tab, { frt: f }); });
  $('#verify', head).addEventListener('change', e => { state.verify = e.target.checked; drawRows(); });
  $('#unsicher', head).addEventListener('change', e => { location.hash = regionLink(rid, route.tab, { unsicher: e.target.checked ? 1 : null }); });

  const body = H(`<section class="rbody"><div class="wrap" id="rows"></div></section>`);
  app.appendChild(body);
  const rowsEl = $('#rows', body);

  const evapDemo = DATA.overview.evap_source === 'synthetic';
  const rowEls = {};
  const switchable = new Set(['niederschlag', 'verdunstung', 'bilanz']);
  for (const r of rows) {
    const tg = state.toggles[r.key] ||= { thr: true, min: false, line: true, wb: true };
    const sub = route.tab === 'jahresvergleich' && r.subYear ? r.subYear : r.sub;
    const el = H(`<article class="row${r.isNew ? ' is-new' : ''}" id="row-${r.key}">
      <div class="row-head">
        <div class="row-title"><h2>${r.label}</h2>
          ${r.link ? `<a class="link" href="${r.link[1]}" target="_blank" rel="noopener">${extIcon()} ${r.link[0]}</a>` : ''}
          ${r.isNew ? '<span class="pill-new">Neu</span>' : ''}${r.isNew && evapDemo ? '<span class="pill-demo" title="Synthetische Daten aus Bodenfeuchte und SPI. Mit --evap echte Daten einlesen.">Demo-Daten</span>' : ''}
        </div>
        <div class="toggles">
          ${switchable.has(r.key) ? `<button type="button" class="switch" data-kombi aria-pressed="${route.kombi}"><i class="trk" aria-hidden="true"></i>Niederschlag &amp; Verdunstung kombinieren</button>` : ''}
          ${r.thr && !(r.kind === 'balance' && route.tab === 'jahresvergleich') ? `<button type="button" class="tog" data-t="thr" aria-pressed="${tg.thr}">${dotLine()} Trockenheitsschwelle</button>
                     <button type="button" class="tog" data-t="min" aria-pressed="${tg.min}">${solidLine()} Minimalwert</button>` : ''}
          ${r.line && route.tab !== 'jahresvergleich' ? `<button type="button" class="tog" data-t="line" aria-pressed="${tg.line}">${solidLine()} Potenzielle Verdunstung</button>` : ''}
          ${r.wbToggle && route.tab !== 'jahresvergleich' ? `<button type="button" class="tog" data-t="wb" aria-pressed="${tg.wb}">${dotIcon()} Wasserbilanz</button>` : ''}
        </div>
      </div>
      ${sub ? `<p class="row-sub">${sub}</p>` : ''}
      <div class="chart"></div>
      <div class="row-foot">
        <a class="link" href="#" data-details>${infoIcon()} Details zum Diagram</a>
        <span class="upd">${infoIcon()} Aktualisiert am ${dmy(frt)}</span>
      </div>
      <div class="details"${state.details[r.key] ? '' : ' hidden'}>${r.details}</div>
    </article>`);
    el.querySelector('[data-kombi]')?.addEventListener('click', () => {
      location.hash = regionLink(rid, route.tab, { kombi: route.kombi ? null : 1 });
    });
    el.querySelectorAll('.tog').forEach(b => b.addEventListener('click', () => {
      tg[b.dataset.t] = !tg[b.dataset.t]; b.setAttribute('aria-pressed', tg[b.dataset.t]); drawRow(r);
    }));
    $('[data-details]', el).addEventListener('click', e => {
      e.preventDefault(); state.details[r.key] = !state.details[r.key]; $('.details', el).hidden = !state.details[r.key];
    });
    rowsEl.appendChild(el);
    rowEls[r.key] = el;
  }

  function drawRow(r) {
    const host = $('.chart', rowEls[r.key]); host.innerHTML = '';
    if (route.tab === 'jahresvergleich') host.appendChild(r.kind === 'cdi' ? yearBlocks(rec, r, frt) : yearLines(rec, r, frt));
    else if (r.kind === 'balance') host.appendChild(balanceChart(rec, frt, route.tab === 'zeitreihe'));
    else host.appendChild(weekChart(rec, r, frt, route.tab === 'zeitreihe'));
  }
  function drawRows() { rows.forEach(drawRow); }
  drawRows();

  /* sub-nav: scroll to row, highlight the row in view */
  const subnav = $('.subnav', head);
  subnav.addEventListener('click', ev => {
    const b = ev.target.closest('button'); if (!b) return;
    rowEls[b.dataset.row].scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  });
  const io = new IntersectionObserver(ents => {
    for (const e of ents) if (e.isIntersecting) {
      const k = e.target.id.slice(4);
      subnav.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.row === k));
    }
  }, { rootMargin: '-30% 0px -60% 0px' });
  Object.values(rowEls).forEach(el => io.observe(el));
  const fk = route.kombi && (route.f === 'niederschlag' || route.f === 'verdunstung') ? 'bilanz' : route.f;
  if (fk && rowEls[fk] && !keepScroll) requestAnimationFrame(() => rowEls[fk].scrollIntoView());
}

/* ---------------------------------------------------------------- forecast uncertainty (switch "Unsicherheit") */
/* Fixed rule for now: lead weeks +2 and +3 count as unreliable. The skill report
   (reports/skill_report) finds the CDI level with persistence at lead week 2 and
   significantly below it at lead week 3. */
const UNC_FROM = 2;
const FC_OPACITY = [1, 1, 0.55, 0.35];
const fcOpacity = c => route.unsicher && c.fc ? FC_OPACITY[c.lead] : 1;
const UNC_NOTE = [null, null,
  'Ab Woche +2 ist die Prognose im Mittel nicht besser als die Annahme, dass die Lage gleich bleibt.',
  'In Woche +3 ist die Prognose im Mittel schlechter als die Annahme, dass die Lage gleich bleibt.'];
const uncTip = c => route.unsicher && c.fc && UNC_NOTE[c.lead] ? `<span class="unc-note"><b>Geringe Verlässlichkeit.</b> ${UNC_NOTE[c.lead]}</span>` : '';

/* Faint tint and an "unsicher" bracket over the unreliable forecast weeks */
function uncertainZone(svg, cols, x0, bw, gap, mt, base, long) {
  if (!route.unsicher) return;
  const i0 = cols.findIndex(c => c.fc && c.lead >= UNC_FROM);
  if (i0 < 0) return;
  const xa = x0(i0) - gap / 2, xb = x0(cols.length - 1) + bw + gap / 2;
  S('rect', { x: xa, y: mt - 8, width: xb - xa, height: base - mt + 8, class: 'unc-zone' }, svg);
  if (long) return; // columns are too narrow in the Zeitreihe for a label
  const yb = mt - 16;
  S('path', { d: `M${xa + 3},${yb + 5}V${yb}H${xb - 3}V${yb + 5}`, fill: 'none', class: 'unc-brk' }, svg);
  S('text', { x: (xa + xb) / 2, y: yb - 6, 'text-anchor': 'middle', class: 'ax unc-lbl' }, svg).textContent = 'unsicher';
}

/* ---------------------------------------------------------------- week chart (Aktuelle Lage, Zeitreihe) */
function columns(rec, r, frt, long) {
  const idx = new Map(rec.dates.map((d, i) => [ts(d), i]));
  const first = long ? ts(rec.dates[0]) : frt - HIST_WEEKS * WEEK;
  const cols = [];
  const obsAt = (key, t) => { const i = idx.get(t); return i == null ? null : rec.obs[key]?.[i] ?? null; };
  const thrAt = (key, t, k) => rec.thr[key]?.[k]?.[isoWeek(t) - 1] ?? null;
  for (let t = first; t < frt; t += WEEK) {
    cols.push({ t, fc: false, v: obsAt(r.v, t), line: r.line ? obsAt(r.line, t) : null,
      thr: r.thr ? thrAt(r.v, t, 'p10') : null, min: r.thr ? thrAt(r.v, t, 'min') : null });
  }
  const f = rec.fc[route.frt] || {};
  for (let l = 0; l < 4; l++) {
    const t = frt + l * WEEK;
    const q = r.noForecast ? null : r.kind === 'cdi' ? [null, f.cdi?.[l], null] : f[r.v] ? [f[r.v][0][l], f[r.v][1][l], f[r.v][2][l]] : null;
    cols.push({ t, fc: true, lead: l, q, v: q ? q[1] : null, line: r.line ? f[r.line]?.[l] ?? null : null,
      thr: r.thr ? thrAt(r.v, t, 'p10') : null, min: r.thr ? thrAt(r.v, t, 'min') : null, ver: obsAt(r.v, t) });
  }
  return cols;
}

function niceMax(v) {
  if (!(v > 0)) return 1;
  const m = Math.pow(10, Math.floor(Math.log10(v)));
  for (const s of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (s * m >= v) return s * m;
  return 10 * m;
}
function tickStep(max) {
  const raw = max / 2, m = Math.pow(10, Math.floor(Math.log10(raw)));
  return [1, 2, 2.5, 5, 10].map(s => s * m).find(s => s >= raw * 0.99);
}

function timeAxis(svg, cols, x0, bw, base, ml, long) {
  if (long) {
    let py = null;
    cols.forEach((c, i) => {
      const yr = isoYear(c.t);
      if (yr !== py) {
        S('line', { x1: x0(i), x2: x0(i), y1: base, y2: base + 7, class: 'tickl' }, svg);
        S('text', { x: x0(i) + 5, y: base + 16, class: 'ax' }, svg).textContent = yr;
        py = yr;
      }
    });
    return;
  }
  S('text', { x: ml - 34, y: base + 13, class: 'ax' }, svg).textContent = 'KW';
  let pm = null;
  cols.forEach((c, i) => {
    S('line', { x1: x0(i), x2: x0(i), y1: base, y2: base + 7, class: 'tickl' }, svg);
    S('text', { x: x0(i) + 3, y: base + 13, class: 'ax' }, svg).textContent = isoWeek(c.t);
    const m = new Date(c.t + 3 * DAY).getUTCMonth();
    if (m !== pm) { S('text', { x: x0(i) + bw / 2, y: base + 28, 'text-anchor': 'middle', class: 'ax-m' }, svg).textContent = MONTHS[m]; pm = m; }
  });
}

function prognoseMarker(svg, px, mt, base, long) {
  S('line', { x1: px, x2: px, y1: mt - 42, y2: base, style: 'stroke:#fff', 'stroke-width': 1, 'stroke-dasharray': '2 3' }, svg);
  // At the right edge (Zeitreihe) the label goes left of the line so it clears the unit label
  const lx = long ? px - 8 : px + 8, anchor = long ? 'end' : 'start';
  S('text', { x: lx, y: mt - 30, 'text-anchor': anchor, class: 'ax' }, svg).textContent = 'Prognose';
  S('path', { d: long ? `M${px - 22},${mt - 18}h14m-5,-4l5,4l-5,4` : `M${px + 8},${mt - 18}h14m-5,-4l5,4l-5,4`, fill: 'none', style: 'stroke:#fff', 'stroke-width': 1.2 }, svg);
}

function weekChart(rec, r, frt, long) {
  const cols = columns(rec, r, frt, long);
  const cdi = r.kind === 'cdi';
  const W = 1240, ml = 62, mr = 62;
  const mt = cdi ? 46 : 60, plotH = cdi ? 46 : 220, mb = 44;
  const H0 = mt + plotH + mb;
  const n = cols.length, step = (W - ml - mr) / n;
  const gap = long ? Math.max(0.6, step * 0.12) : Math.max(2, step * 0.09);
  const bw = step - gap;
  const x0 = i => ml + i * step + gap / 2;
  const tg = state.toggles[r.key];
  const svg = S('svg', { viewBox: `0 0 ${W} ${H0}`, role: 'img', 'aria-label': `${r.label}, ${long ? 'Zeitreihe' : 'aktuelle Lage'}` });
  const base = mt + plotH;

  // y scale (from every layer, so toggling layers never rescales)
  let yMax = 1;
  if (!cdi) {
    const vals = cols.flatMap(c => [c.v, c.q?.[2], c.thr, c.min, c.line, c.ver]).filter(v => v != null);
    yMax = r.yMax && Math.max(...vals) <= r.yMax ? r.yMax : niceMax(Math.max(...vals) * 1.04);
  }
  const y = v => base - plotH * v / yMax;

  // axes text
  if (!cdi) {
    S('text', { x: 4, y: mt - 30, class: 'ax-u' }, svg).textContent = r.unit;
    S('text', { x: W - 4, y: mt - 30, 'text-anchor': 'end', class: 'ax-u' }, svg).textContent = r.unit;
    const st = tickStep(yMax);
    for (let t = 0; t <= yMax + 1e-9; t += st) {
      const lab = Number.isInteger(t) ? String(t) : t.toFixed(1);
      S('text', { x: 4, y: y(t) + 4, class: 'ax' }, svg).textContent = lab;
      S('text', { x: W - 4, y: y(t) + 4, 'text-anchor': 'end', class: 'ax' }, svg).textContent = lab;
    }
  }
  S('line', { x1: 0, x2: W, y1: base, y2: base, class: 'base' }, svg);

  timeAxis(svg, cols, x0, bw, base, ml, long);
  prognoseMarker(svg, ml + cols.findIndex(c => c.fc) * step, mt, base, long);
  uncertainZone(svg, cols, x0, bw, gap, mt, base, long);

  // bars
  const fcPat = `url(#hatch-${r.key})`;
  cols.forEach((c, i) => {
    const x = x0(i);
    if (cdi) {
      const lv = c.v;
      if (lv != null) {
        S('rect', { x, y: mt, width: bw, height: plotH, opacity: fcOpacity(c), style: `fill:${c.fc ? `url(#hatch-lv${lv})` : cssv(`--cdi-${lv}`)}` }, svg);
        if (!c.fc) S('rect', { x, y: mt, width: bw, height: plotH, fill: 'none', style: 'stroke:rgba(255,255,255,.25)' }, svg);
      }
      if (c.fc && state.verify && c.ver != null) {
        S('rect', { x: x + bw * 0.2, y: base + 4 - 12, width: bw * 0.6, height: 8, style: `fill:${cssv(`--cdi-${c.ver}`)};stroke:#fff`, 'stroke-width': 1 }, svg);
      }
    } else {
      if (r.noForecast && c.fc) S('rect', { x, y: mt, width: bw, height: plotH, style: 'fill:rgba(255,255,255,.05)' }, svg);
      if (!c.fc && c.v == null) S('rect', { x, y: mt, width: bw, height: plotH, style: 'fill:rgba(255,255,255,.03)' }, svg);
      if (c.v != null) S('rect', { x, y: y(c.v), width: bw, height: base - y(c.v), opacity: fcOpacity(c), style: `fill:${c.fc ? fcPat : cssv(r.color)}` }, svg);
      if (c.fc && state.verify && c.ver != null) {
        S('rect', { x: x + 1, y: y(c.ver), width: bw - 2, height: base - y(c.ver), fill: 'none', style: 'stroke:#fff', 'stroke-width': 1.4, 'stroke-dasharray': '4 3' }, svg);
        S('line', { x1: x - 2, x2: x + bw + 2, y1: y(c.ver), y2: y(c.ver), style: 'stroke:#fff', 'stroke-width': 2.5 }, svg);
      }
    }
  });

  if (!cdi) {
    // threshold, minimum and potential-evaporation layers
    cols.forEach((c, i) => {
      const x = x0(i);
      if (tg.thr && c.thr != null) S('line', { x1: x - gap / 2, x2: x + bw + gap / 2, y1: y(c.thr), y2: y(c.thr), style: 'stroke:#fff', 'stroke-width': 2, 'stroke-dasharray': '2 2' }, svg);
      if (tg.min && c.min != null) S('line', { x1: x - gap / 2, x2: x + bw + gap / 2, y1: y(c.min), y2: y(c.min), style: `stroke:${cssv('--chip')}`, 'stroke-width': 2 }, svg);
    });
    if (r.line && tg.line) {
      let d = '';
      cols.forEach((c, i) => { if (c.line != null) d += `${d ? 'L' : 'M'}${(x0(i) - gap / 2).toFixed(1)},${y(c.line).toFixed(1)}H${(x0(i) + bw + gap / 2).toFixed(1)}`; });
      S('path', { d, fill: 'none', style: `stroke:${cssv(r.light)}`, 'stroke-width': 2.4, 'stroke-linejoin': 'round' }, svg);
    }
    // whiskers
    cols.forEach((c, i) => {
      if (!c.fc || !c.q || c.q[0] == null || c.q[2] == null) return;
      const cx = x0(i) + bw / 2, cw = Math.min(14, bw * 0.4);
      S('path', { d: `M${cx},${y(c.q[0])}V${y(c.q[2])}M${cx - cw / 2},${y(c.q[0])}h${cw}M${cx - cw / 2},${y(c.q[2])}h${cw}`, fill: 'none', style: 'stroke:#fff', 'stroke-width': 1.6 }, svg);
    });
  }

  // hover
  cols.forEach((c, i) => {
    const hit = S('rect', { x: ml + i * step, y: mt - 8, width: step, height: plotH + 8, class: 'hit' }, svg);
    bindTip(hit, () => colTip(r, c));
  });
  return svg;
}

function colTip(r, c) {
  const head = `<b>KW ${isoWeek(c.t)}</b> <span class="m">${dm(c.t)}–${dmy(c.t + 6 * DAY)}${c.fc ? ` · Prognose Woche +${c.lead}` : ''}</span>`;
  const u = r.unit ? ` ${r.unit}` : '';
  const d = r.v === 'vhi' || r.v === 'soil_moisture_ufc' || r.v === 'precip_sum_1m' || r.v === 'eta' ? 1 : 0;
  const lines = [head];
  if (r.kind === 'cdi') {
    if (c.v != null) lines.push(`${swatch(cssv(`--cdi-${c.v}`))}${c.fc ? 'Prognose: ' : ''}${LEVELS[c.v - 1]} (Stufe ${c.v})`);
    else lines.push('<span class="m">keine Daten</span>');
    if (c.fc && c.ver != null) lines.push(`<span class="m">Beobachtet: ${LEVELS[c.ver - 1]}</span>`);
    if (uncTip(c)) lines.push(uncTip(c));
    return lines.join('<br>');
  }
  if (c.fc && !c.q) lines.push('<span class="m">keine Prognose</span>');
  else if (c.fc) lines.push(`${swatch(cssv(r.color))}Median <b>${num(c.q[1], d)}${u}</b><br><span class="m">10–90 %: ${num(c.q[0], d)} bis ${num(c.q[2], d)}${u}</span>`);
  else lines.push(c.v == null ? '<span class="m">keine Beobachtung</span>' : `${swatch(cssv(r.color))}<b>${num(c.v, d)}${u}</b>`);
  if (r.line && c.line != null) lines.push(`${swatch(cssv(r.light))}Potenziell ${num(c.line, 1)}${u}`);
  if (c.thr != null) lines.push(`<span class="m">Trockenheitsschwelle ${num(c.thr, d)} · Minimum ${num(c.min, d)}${u}</span>`);
  if (c.fc && c.ver != null) lines.push(`<span class="m">Später beobachtet: ${num(c.ver, d)}${u}</span>`);
  if (uncTip(c)) lines.push(uncTip(c));
  return lines.join('<br>');
}

/* ---------------------------------------------------------------- combined precipitation / evaporation */
function balanceChart(rec, frt, long) {
  const tg = state.toggles[BAL.key];
  const P = ROWS.find(x => x.key === 'niederschlag'), E = ROWS.find(x => x.key === 'verdunstung');
  const idx = new Map(rec.dates.map((d, i) => [ts(d), i]));
  const obsAt = (k, t) => { const i = idx.get(t); return i == null ? null : rec.obs[k]?.[i] ?? null; };
  const bf = balanceFc(rec, frt);
  const cols = columns(rec, P, frt, long).map(c => {
    if (!c.fc) {
      const e = obsAt('eta30', c.t);
      return { ...c, e, ep: obsAt('etp30', c.t), wb: c.v != null && e != null ? c.v - e : null };
    }
    const l = c.lead, eq = bf.eta30 ? [bf.eta30[0][l], bf.eta30[1][l], bf.eta30[2][l]] : null;
    return { ...c, eq, e: eq?.[1] ?? null, ep: bf.etp30?.[l] ?? null, wb: bf.wb?.[1][l] ?? null, verE: obsAt('eta30', c.t) };
  });

  const W = 1240, ml = 62, mr = 62, mt = 60, plotH = 320, mb = 44;
  const base = mt + plotH, H0 = base + mb;
  const n = cols.length, step = (W - ml - mr) / n;
  const gap = long ? Math.max(0.6, step * 0.12) : Math.max(2, step * 0.09);
  const bw = step - gap;
  const x0 = i => ml + i * step + gap / 2;

  // One mm scale for both directions; extents from every layer so toggles never rescale
  const up = cols.flatMap(c => [c.v, c.q?.[2], c.thr, c.min, c.ver, c.wb]).filter(v => v != null);
  const dn = cols.flatMap(c => [c.e, c.eq?.[2], c.ep, c.verE, c.wb == null ? null : -c.wb]).filter(v => v != null);
  const yTop = niceMax(Math.max(1, ...up) * 1.04), yBot = niceMax(Math.max(1, ...dn) * 1.04);
  const k = plotH / (yTop + yBot), zero = mt + yTop * k;
  const y = v => zero - v * k;

  const wrap = document.createElement('div');
  const svg = S('svg', { viewBox: `0 0 ${W} ${H0}`, role: 'img', 'aria-label': `Niederschlag und Verdunstung, ${long ? 'Zeitreihe' : 'aktuelle Lage'}` }, wrap);
  S('text', { x: 4, y: mt - 30, class: 'ax-u' }, svg).textContent = BAL.unit;
  S('text', { x: W - 4, y: mt - 30, 'text-anchor': 'end', class: 'ax-u' }, svg).textContent = BAL.unit;
  const st = tickStep(Math.max(yTop, yBot));
  for (let t = -Math.floor(yBot / st) * st; t <= yTop + 1e-9; t += st) {
    if (t) S('line', { x1: ml, x2: W - mr, y1: y(t), y2: y(t), style: 'stroke:rgba(255,255,255,.06)' }, svg);
    S('text', { x: 4, y: y(t) + 4, class: 'ax' }, svg).textContent = signed(t);
    S('text', { x: W - 4, y: y(t) + 4, 'text-anchor': 'end', class: 'ax' }, svg).textContent = signed(t);
  }
  S('text', { x: ml + 4, y: mt + 2, class: 'ax-m' }, svg).textContent = '↑ Niederschlag';
  S('text', { x: ml + 4, y: base - 6, class: 'ax-m' }, svg).textContent = '↓ Verdunstung';
  S('line', { x1: 0, x2: W, y1: base, y2: base, style: 'stroke:rgba(255,255,255,.35)' }, svg);
  timeAxis(svg, cols, x0, bw, base, ml, long);
  prognoseMarker(svg, ml + cols.findIndex(c => c.fc) * step, mt, base, long);
  uncertainZone(svg, cols, x0, bw, gap, mt, base, long);

  // bars: precipitation above zero, evaporation below
  cols.forEach((c, i) => {
    const x = x0(i);
    if (c.v != null) S('rect', { x, y: y(c.v), width: bw, height: zero - y(c.v), opacity: fcOpacity(c), style: `fill:${c.fc ? 'url(#hatch-niederschlag)' : cssv(P.color)}` }, svg);
    if (c.e != null) S('rect', { x, y: zero, width: bw, height: y(-c.e) - zero, opacity: fcOpacity(c), style: `fill:${c.fc ? 'url(#hatch-verdunstung)' : cssv(E.color)}` }, svg);
    if (c.fc && state.verify) {
      for (const v of [c.ver, c.verE == null ? null : -c.verE]) {
        if (v == null) continue;
        S('rect', { x: x + 1, y: Math.min(y(v), zero), width: bw - 2, height: Math.abs(y(v) - zero), fill: 'none', style: 'stroke:#fff', 'stroke-width': 1.4, 'stroke-dasharray': '4 3' }, svg);
        S('line', { x1: x - 2, x2: x + bw + 2, y1: y(v), y2: y(v), style: 'stroke:#fff', 'stroke-width': 2.5 }, svg);
      }
    }
  });
  S('line', { x1: ml, x2: W - mr, y1: zero, y2: zero, class: 'base' }, svg);

  // reference layers
  cols.forEach((c, i) => {
    const x = x0(i);
    if (tg.thr && c.thr != null) S('line', { x1: x - gap / 2, x2: x + bw + gap / 2, y1: y(c.thr), y2: y(c.thr), style: 'stroke:#fff', 'stroke-width': 2, 'stroke-dasharray': '2 2' }, svg);
    if (tg.min && c.min != null) S('line', { x1: x - gap / 2, x2: x + bw + gap / 2, y1: y(c.min), y2: y(c.min), style: `stroke:${cssv('--chip')}`, 'stroke-width': 2 }, svg);
  });
  if (tg.line) {
    let d = '';
    cols.forEach((c, i) => { if (c.ep != null) d += `${d ? 'L' : 'M'}${(x0(i) - gap / 2).toFixed(1)},${y(-c.ep).toFixed(1)}H${(x0(i) + bw + gap / 2).toFixed(1)}`; });
    S('path', { d, fill: 'none', style: `stroke:${cssv(E.light)}`, 'stroke-width': 2.4, 'stroke-linejoin': 'round' }, svg);
  }
  // whiskers in both directions
  cols.forEach((c, i) => {
    if (!c.fc) return;
    const cx = x0(i) + bw / 2, cw = Math.min(14, bw * 0.4);
    for (const [a, b] of [[c.q?.[0], c.q?.[2]], [c.eq ? -c.eq[0] : null, c.eq ? -c.eq[2] : null]]) {
      if (a == null || b == null) continue;
      S('path', { d: `M${cx},${y(a)}V${y(b)}M${cx - cw / 2},${y(a)}h${cw}M${cx - cw / 2},${y(b)}h${cw}`, fill: 'none', style: 'stroke:#fff', 'stroke-width': 1.6 }, svg);
    }
  });
  // water balance P − ET
  if (tg.wb) {
    let d = '', prev = false;
    cols.forEach((c, i) => {
      if (c.wb == null) { prev = false; return; }
      d += `${prev ? 'L' : 'M'}${(x0(i) + bw / 2).toFixed(1)},${y(c.wb).toFixed(1)}`; prev = true;
    });
    S('path', { d, fill: 'none', style: 'stroke:#fff;opacity:.75', 'stroke-width': 1.4 }, svg);
    cols.forEach((c, i) => {
      if (c.wb == null) return;
      S('circle', { cx: x0(i) + bw / 2, cy: y(c.wb), r: long ? 2.2 : 4, style: c.fc ? 'fill:var(--secondary-900);stroke:#fff' : 'fill:#fff;stroke:var(--secondary-900)', 'stroke-width': 1.6 }, svg);
    });
  }

  cols.forEach((c, i) => {
    const hit = S('rect', { x: ml + i * step, y: mt - 8, width: step, height: plotH + 8, class: 'hit' }, svg);
    bindTip(hit, () => balanceTip(c));
  });

  wrap.appendChild(H(`<div class="bal-legend">
    <span><i style="background:var(${P.color})"></i>Niederschlag</span>
    <span><i style="background:var(${E.color})"></i>Tatsächliche Verdunstung</span>
    <span><i style="background:repeating-linear-gradient(45deg, var(--secondary-300) 0 3px, var(--secondary-700) 3px 6px)"></i>Prognose (Median, 10–90 %)</span>
    ${tg.line ? `<span><i style="height:3px;background:var(${E.light})"></i>Potenzielle Verdunstung</span>` : ''}
    ${tg.wb ? '<span><b class="wbdot"></b>Wasserbilanz</span>' : ''}
  </div>`));
  return wrap;
}

function balanceTip(c) {
  const lines = [`<b>KW ${isoWeek(c.t)}</b> <span class="m">${dm(c.t)}–${dmy(c.t + 6 * DAY)}${c.fc ? ` · Prognose Woche +${c.lead}` : ''} · Summen 30 Tage</span>`];
  const P = cssv('--factor-precip'), E = cssv('--factor-evap');
  if (c.fc) {
    lines.push(c.q ? `${swatch(P)}Niederschlag <b>${num(c.q[1])} mm</b> <span class="m">(${num(c.q[0])}–${num(c.q[2])})</span>` : `${swatch(P)}Niederschlag –`);
    lines.push(c.eq ? `${swatch(E)}Verdunstung <b>${num(c.eq[1])} mm</b> <span class="m">(${num(c.eq[0])}–${num(c.eq[2])})</span>` : `${swatch(E)}Verdunstung –`);
  } else {
    lines.push(`${swatch(P)}Niederschlag <b>${num(c.v)} mm</b>`);
    lines.push(`${swatch(E)}Verdunstung <b>${num(c.e)} mm</b>`);
  }
  if (c.ep != null) lines.push(`${swatch(cssv('--factor-evap-l'))}Potenzielle Verdunstung ${num(c.ep)} mm`);
  if (c.wb != null) lines.push(`Wasserbilanz <b>${c.wb > 0 ? '+' : ''}${num(c.wb)} mm</b>${c.fc ? ' <span class="m">(Median)</span>' : ''}`);
  if (c.thr != null) lines.push(`<span class="m">Trockenheitsschwelle Niederschlag ${num(c.thr)} mm</span>`);
  if (c.fc && (c.ver != null || c.verE != null)) lines.push(`<span class="m">Später beobachtet: ${num(c.ver)} mm Niederschlag, ${num(c.verE)} mm Verdunstung</span>`);
  if (uncTip(c)) lines.push(uncTip(c));
  return lines.join('<br>');
}

/* ---------------------------------------------------------------- Jahresvergleich */
const YEAR_COLORS = ['#46596b', '#596978', '#828e9a', '#acb4bd'];
function yearSeries(rec, key, frt) {
  const by = new Map();
  rec.dates.forEach((d, i) => {
    const t = ts(d); if (t >= frt) return;
    const yr = isoYear(t), v = rec.obs[key]?.[i];
    if (!by.has(yr)) by.set(yr, []);
    by.get(yr).push([isoWeek(t), v]);
  });
  return by;
}
function yearLines(rec, r, frt) {
  const wrap = document.createElement('div');
  const by = yearSeries(rec, r.v, frt);
  const years = [...by.keys()].sort();
  const cur = isoYear(frt - WEEK);
  const f = r.kind === 'balance' ? balanceFc(rec, frt).wb : rec.fc[route.frt]?.[r.v];
  const W = 1240, H0 = 300, ml = 62, mr = 62, mt = 30, mb = 34;
  const x = w => ml + (W - ml - mr) * (w - 1) / 52;
  const vals = years.flatMap(yr => by.get(yr).map(p => p[1])).concat(f && !r.noForecast ? [...f[0], ...f[2]] : []).filter(v => v != null);
  const yMax = r.yMax && Math.max(...vals) <= r.yMax ? r.yMax : niceMax(Math.max(...vals) * 1.04);
  const lo = Math.min(0, ...vals);
  const yMin = lo < 0 ? -niceMax(-lo * 1.04) : 0;
  const y = v => mt + (H0 - mt - mb) * (yMax - v) / (yMax - yMin);
  const svg = S('svg', { viewBox: `0 0 ${W} ${H0}`, role: 'img', 'aria-label': `${r.label}, Jahresvergleich` }, wrap);
  S('text', { x: 4, y: 12, class: 'ax-u' }, svg).textContent = r.unit;
  const st = tickStep(Math.max(yMax, -yMin));
  for (let t = Math.ceil(yMin / st) * st; t <= yMax + 1e-9; t += st) {
    S('line', { x1: ml, x2: W - mr, y1: y(t), y2: y(t), style: 'stroke:rgba(255,255,255,.08)' }, svg);
    S('text', { x: 4, y: y(t) + 4, class: 'ax' }, svg).textContent = signed(t);
  }
  S('line', { x1: 0, x2: W, y1: y(0), y2: y(0), class: 'base' }, svg);
  for (let m = 0; m < 12; m++) {
    const w = isoWeek(Date.UTC(2026, m, 15));
    S('text', { x: x(w), y: H0 - 10, 'text-anchor': 'middle', class: 'ax-m' }, svg).textContent = MONTHS[m];
  }
  const legend = [];
  years.forEach((yr, i) => {
    const pts = by.get(yr).filter(p => p[1] != null);
    const isCur = yr === cur;
    const col = isCur ? cssv(r.light) : YEAR_COLORS[Math.max(0, YEAR_COLORS.length - (years.length - i))];
    let d = '', prev = null;
    for (const [w, v] of pts) { d += `${prev == null || w - prev > 1 ? 'M' : 'L'}${x(w).toFixed(1)},${y(v).toFixed(1)}`; prev = w; }
    S('path', { d, fill: 'none', style: `stroke:${col}`, 'stroke-width': isCur ? 2.8 : 1.6 }, svg);
    legend.push(`<span><i style="background:${col}"></i>${yr}</span>`);
  });
  if (f && !r.noForecast) {
    const ws = [0, 1, 2, 3].map(l => isoWeek(frt + l * WEEK));
    if (ws[3] > ws[0]) {
      const up = ws.map((w, l) => `${x(w)},${y(f[2][l])}`), dn = ws.map((w, l) => `${x(w)},${y(f[0][l])}`).reverse();
      S('path', { d: `M${up.join('L')}L${dn.join('L')}Z`, style: `fill:${cssv(r.color)};opacity:.45` }, svg);
      const lastObs = by.get(cur)?.filter(p => p[1] != null).slice(-1)[0];
      const pts = (lastObs ? [`${x(lastObs[0])},${y(lastObs[1])}`] : []).concat(ws.map((w, l) => `${x(w)},${y(f[1][l])}`));
      S('path', { d: 'M' + pts.join('L'), fill: 'none', style: `stroke:${cssv(r.light)}`, 'stroke-width': 2.8, 'stroke-dasharray': '6 4' }, svg);
      legend.push(`<span><i style="background:repeating-linear-gradient(90deg, ${cssv(r.light)} 0 5px, transparent 5px 8px)"></i>Prognose ${cur}</span>`);
    }
  }
  wrap.appendChild(H(`<div class="legend-years">${legend.join('')}</div>`));
  return wrap;
}
function yearBlocks(rec, r, frt) {
  const by = yearSeries(rec, 'cdi', frt);
  const years = [...by.keys()].sort();
  const f = rec.fc[route.frt]?.cdi || [];
  const W = 1240, ml = 62, rowH = 26, mt = 6;
  const H0 = mt + years.length * rowH + 24;
  const step = (W - ml - 10) / 53;
  const svg = S('svg', { viewBox: `0 0 ${W} ${H0}`, role: 'img', 'aria-label': 'Trockenheitsindex, Jahresvergleich' });
  years.forEach((yr, j) => {
    const yy = mt + j * rowH;
    S('text', { x: 4, y: yy + 16, class: 'ax' }, svg).textContent = yr;
    for (const [w, v] of by.get(yr)) if (v != null) {
      const rc = S('rect', { x: ml + (w - 1) * step, y: yy, width: step - 1.5, height: rowH - 4, style: `fill:${cssv(`--cdi-${v}`)}` }, svg);
      bindTip(rc, () => `<b>${yr} · KW ${w}</b><br>${swatch(cssv(`--cdi-${v}`))}${LEVELS[v - 1]}`);
    }
    if (yr === isoYear(frt - WEEK)) f.forEach((v, l) => {
      const w = isoWeek(frt + l * WEEK); if (v == null || isoYear(frt + l * WEEK) !== yr) return;
      const rc = S('rect', { x: ml + (w - 1) * step, y: yy, width: step - 1.5, height: rowH - 4, style: `fill:url(#hatch-lv${v})` }, svg);
      bindTip(rc, () => `<b>${yr} · KW ${w}</b> <span class="m">Prognose</span><br>${swatch(cssv(`--cdi-${v}`))}${LEVELS[v - 1]}`);
    });
  });
  for (let m = 0; m < 12; m++) {
    const w = isoWeek(Date.UTC(2026, m, 15));
    S('text', { x: ml + (w - 0.5) * step, y: H0 - 6, 'text-anchor': 'middle', class: 'ax-m' }, svg).textContent = MONTHS[m];
  }
  return svg;
}

/* ---------------------------------------------------------------- icons */
function infoIcon() { return '<svg class="icon" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="none" stroke="currentColor"/><path d="M8 7v5M8 4.2v.6" stroke="currentColor" stroke-width="1.4"/></svg>'; }
function extIcon() { return '<svg class="icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M9 2h5v5M14 2L7 9M12 10v4H2V4h4" fill="none" stroke="currentColor" stroke-width="1.2"/></svg>'; }
function listIcon() { return '<svg class="icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M5 4h10M5 8h10M5 12h10M1 4h1.5M1 8h1.5M1 12h1.5" stroke="currentColor" stroke-width="1.5"/></svg>'; }
function dotIcon() { return '<svg viewBox="0 0 22 6" aria-hidden="true"><path d="M2 4L11 2L20 4" stroke="currentColor" stroke-width="1.2" fill="none"/><circle cx="11" cy="2.5" r="2.3" fill="currentColor"/></svg>'; }
function dotLine() { return '<svg viewBox="0 0 22 6" aria-hidden="true"><path d="M1 3h20" stroke="currentColor" stroke-width="2" stroke-dasharray="2 2"/></svg>'; }
function solidLine() { return '<svg viewBox="0 0 22 6" aria-hidden="true"><path d="M1 3h20" stroke="currentColor" stroke-width="2"/></svg>'; }

/* ---------------------------------------------------------------- boot */
let prevKey = null;
function render() {
  route = parseRoute();
  hideTip();
  $('#nav-home').classList.toggle('on', route.page === 'home');
  // Keep the scroll position when only the issue date, week or view changes
  const key = route.page === 'region' ? `r${route.rid}/${route.tab}` : 'home';
  const keepScroll = key === prevKey;
  prevKey = key;
  const y = scrollY;
  const done = route.page === 'region' ? renderRegion(keepScroll) : (renderHome(), Promise.resolve());
  done.then(() => { if (keepScroll) scrollTo(0, y); else if (!route.f) scrollTo(0, 0); });
}
async function boot() {
  try {
    [DATA.overview, DATA.geo] = await Promise.all([getJSON('data/overview.json'), getJSON('data/regions.json')]);
  } catch (e) {
    $('#app').innerHTML = `<div class="wrap loading">Die Daten konnten nicht geladen werden (${esc(e.message)}). Starten Sie den Prototyp über einen lokalen Webserver, siehe README.</div>`;
    return;
  }
  makePatterns();
  addEventListener('hashchange', render);
  render();
}
boot();
})();
