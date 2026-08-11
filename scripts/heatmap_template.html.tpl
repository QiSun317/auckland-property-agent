<title>大奥克兰房价热力图</title>
<style>
  :root {
    color-scheme: light dark;
    --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e;
    --muted:#898781; --hair:#e1e0d9; --ring:rgba(11,11,11,.10);
    --nodata:#eeede8; --nodata-ink:#c9c7bd; --sep:#fcfcfb;
    --accent:#2a78d6; --shadow:rgba(11,11,11,.14);
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) {
      --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink-2:#c3c2b7;
      --muted:#898781; --hair:#2c2c2a; --ring:rgba(255,255,255,.10);
      --nodata:#242422; --nodata-ink:#3d3d39; --sep:#1a1a19;
      --accent:#3987e5; --shadow:rgba(0,0,0,.5);
    }
  }
  :root[data-theme="dark"] {
    --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink-2:#c3c2b7;
    --muted:#898781; --hair:#2c2c2a; --ring:rgba(255,255,255,.10);
    --nodata:#242422; --nodata-ink:#3d3d39; --sep:#1a1a19;
    --accent:#3987e5; --shadow:rgba(0,0,0,.5);
  }

  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--plane); color:var(--ink);
    font:15px/1.55 system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    -webkit-font-smoothing:antialiased;
  }
  .wrap { max-width:1180px; margin:0 auto; padding:28px 20px 56px; }

  h1 { font-size:26px; line-height:1.25; margin:0 0 6px; font-weight:650; letter-spacing:-.01em; }
  .sub { color:var(--ink-2); margin:0 0 22px; font-size:14px; }
  .sub b { color:var(--ink); font-weight:600; }

  .tiles { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:18px; }
  .tile {
    background:var(--surface); border:1px solid var(--ring); border-radius:8px;
    padding:12px 14px;
  }
  .tile .k { font-size:12px; color:var(--muted); margin-bottom:4px; }
  .tile .v { font-size:22px; font-weight:600; letter-spacing:-.02em; }
  .tile .m { font-size:12px; color:var(--ink-2); margin-top:2px; }

  .bar {
    display:flex; flex-wrap:wrap; gap:10px; align-items:center;
    margin-bottom:12px;
  }
  .seg { display:flex; border:1px solid var(--ring); border-radius:7px; overflow:hidden; background:var(--surface); }
  .seg button {
    font:inherit; font-size:13px; padding:7px 13px; border:0; background:transparent;
    color:var(--ink-2); cursor:pointer; white-space:nowrap;
  }
  .seg button[aria-pressed="true"] { background:var(--accent); color:#fff; }
  .seg button + button { border-left:1px solid var(--ring); }
  input[type=search] {
    font:inherit; font-size:13px; padding:7px 11px; border-radius:7px;
    border:1px solid var(--ring); background:var(--surface); color:var(--ink);
    min-width:210px;
  }
  input[type=search]:focus { outline:2px solid var(--accent); outline-offset:-1px; }
  .spacer { flex:1 1 auto; }

  .stage {
    position:relative; background:var(--surface);
    border:1px solid var(--ring); border-radius:10px; overflow:hidden;
  }
  svg#map { display:block; width:100%; aspect-ratio:5/4; max-height:82vh; touch-action:none; cursor:grab; }
  svg#map.dragging { cursor:grabbing; }
  #map path { stroke:var(--sep); stroke-width:.6; vector-effect:non-scaling-stroke; }
  #map path.hi { stroke:var(--ink); stroke-width:2; }
  #map path.dim { opacity:.28; }
  #hatchLine { stroke:var(--nodata-ink); }
  #hatchBg { fill:var(--nodata); }

  .hint {
    position:absolute; left:12px; bottom:10px; font-size:11.5px; color:var(--muted);
    pointer-events:none;
  }

  #tip {
    position:absolute; pointer-events:none; opacity:0; transition:opacity .08s;
    background:var(--surface); border:1px solid var(--ring); border-radius:8px;
    box-shadow:0 6px 20px var(--shadow); padding:10px 12px; min-width:186px;
    font-size:12.5px; z-index:5;
  }
  #tip .t { font-weight:650; font-size:14px; margin-bottom:2px; }
  #tip .big { font-size:19px; font-weight:600; letter-spacing:-.02em; margin:2px 0 7px; }
  #tip dl { display:grid; grid-template-columns:auto auto; gap:2px 14px; margin:0; }
  #tip dt { color:var(--muted); }
  #tip dd { margin:0; text-align:right; font-variant-numeric:tabular-nums; }
  .up { color:#0ca30c; } .down { color:#d03b3b; }

  .legend { margin:14px 0 0; }
  .legend .lbar {
    position:relative; height:12px; border-radius:6px; border:1px solid var(--ring);
  }
  .legend .cursor {
    position:absolute; top:-3px; width:2px; height:18px; background:var(--ink);
    border-radius:1px; opacity:0; transform:translateX(-1px);
  }
  .legend .ticks {
    display:flex; justify-content:space-between; margin-top:5px;
    font-size:11.5px; color:var(--muted); font-variant-numeric:tabular-nums;
  }
  .legend .ticks span { text-align:center; }
  .legend .ticks span:first-child { text-align:left; }
  .legend .ticks span:last-child { text-align:right; }
  .legend .ticks em { font-style:normal; opacity:.75; }
  .legend .cap {
    font-size:12px; color:var(--ink-2); margin-bottom:6px;
    display:flex; gap:10px; align-items:center; flex-wrap:wrap;
  }
  .legend .cap .nd { margin-left:auto; display:inline-flex; align-items:center; gap:6px; white-space:nowrap; }
  .legend .cap .ndsw {
    width:14px; height:14px; border-radius:3px; border:1px solid var(--ring);
    background:
      repeating-linear-gradient(45deg, var(--nodata-ink) 0 1.5px, var(--nodata) 1.5px 5px);
  }

  table { border-collapse:collapse; width:100%; font-size:13px; margin-top:8px; }
  th, td { padding:7px 10px; text-align:right; border-bottom:1px solid var(--hair); }
  th:first-child, td:first-child { text-align:left; }
  th { color:var(--ink-2); font-weight:600; cursor:pointer; white-space:nowrap; user-select:none; position:sticky; top:0; background:var(--plane); }
  th[aria-sort]::after { content:" ▾"; color:var(--muted); }
  th[aria-sort="ascending"]::after { content:" ▴"; }
  td { font-variant-numeric:tabular-nums; }
  .swatch { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:8px; vertical-align:-1px; border:1px solid var(--ring); }
  .swatch.nodata { background:repeating-linear-gradient(45deg, var(--nodata-ink) 0 1.5px, var(--nodata) 1.5px 5px); }
  #tableWrap { max-height:520px; overflow:auto; border:1px solid var(--ring); border-radius:10px; padding:0 14px 12px; background:var(--surface); margin-top:14px; }
  #tableWrap[hidden] { display:none; }

  /* ---- suburb detail view ---- */
  #detail[hidden], #dGeo[hidden] { display:none; }
  .dbar { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; margin-bottom:12px; }
  .dbar button {
    font:inherit; font-size:13px; padding:7px 13px; border-radius:7px; cursor:pointer;
    border:1px solid var(--ring); background:var(--surface); color:var(--ink-2);
  }
  .dbar button:hover { color:var(--ink); }
  .dname { font-size:24px; font-weight:650; letter-spacing:-.01em; }
  .dkind { font-size:12.5px; color:var(--muted); }

  .dgrid { display:grid; grid-template-columns:minmax(0,1.25fr) minmax(0,1fr); gap:18px; align-items:start; }
  .dstage {
    position:relative; background:var(--surface); border:1px solid var(--ring);
    border-radius:10px; overflow:hidden;
  }
  #dmap { display:block; width:100%; aspect-ratio:1/1; max-height:62vh; }
  #dtip {
    position:absolute; pointer-events:none; opacity:0; transition:opacity .08s;
    background:var(--surface); border:1px solid var(--ring); border-radius:8px;
    box-shadow:0 6px 20px var(--shadow); padding:8px 11px; font-size:12.5px; z-index:5;
  }
  #dtip .big { font-size:17px; font-weight:600; letter-spacing:-.02em; }
  #dtip .sm { color:var(--muted); font-size:11.5px; }

  .dside { display:flex; flex-direction:column; gap:16px; min-width:0; }
  .card {
    background:var(--surface); border:1px solid var(--ring); border-radius:10px; padding:14px 16px;
  }
  .card h3 {
    font-size:12px; font-weight:650; color:var(--muted); margin:0 0 10px;
    letter-spacing:.04em; text-transform:uppercase;
  }
  .dhero { display:flex; gap:22px; flex-wrap:wrap; }
  .dhero > div { min-width:0; }
  .dhero .k { font-size:11.5px; color:var(--muted); }
  .dhero .v { font-size:24px; font-weight:600; letter-spacing:-.02em; }
  .dhero .m { font-size:12px; color:var(--ink-2); }
  .dintro { margin:0; font-size:13px; line-height:1.65; color:var(--ink-2); }
  .dintro a { color:var(--accent); text-decoration:none; }
  .dintro a:hover { text-decoration:underline; }

  .dstats { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px 18px; font-size:13px; }
  .dstats div { display:flex; justify-content:space-between; gap:10px; border-bottom:1px solid var(--hair); padding-bottom:5px; }
  .dstats dt, .dstats span:first-child { color:var(--muted); font-size:12px; }
  .dstats span:last-child { font-variant-numeric:tabular-nums; white-space:nowrap; }

  .beds { display:flex; height:22px; border-radius:5px; overflow:hidden; gap:2px; margin-top:2px; }
  .beds i {
    display:block; font-style:normal; font-size:10px; color:#fff; text-align:center;
    line-height:22px; overflow:hidden;
  }
  .bedkey { display:flex; gap:12px; font-size:11.5px; color:var(--muted); margin-top:6px; flex-wrap:wrap; }
  .bedkey b { font-weight:500; color:var(--ink-2); }
  .bedkey i { display:inline-block; width:9px; height:9px; border-radius:2px; font-style:normal; margin-right:4px; }

  .chart { width:100%; height:auto; display:block; overflow:visible; }
  .chart .grid { stroke:var(--hair); stroke-width:1; }
  .chart .line { fill:none; stroke:var(--accent); stroke-width:2; stroke-linejoin:round; }
  .chart .area { fill:var(--accent); opacity:.10; }
  .chart text { fill:var(--muted); font-size:10px; }
  .chart .med { stroke:var(--ink); stroke-width:1.5; stroke-dasharray:3 3; }

  @media (max-width:900px) {
    .dgrid { grid-template-columns:1fr; }
    #dmap { aspect-ratio:4/3; }
  }

  .notes { margin-top:22px; font-size:12.5px; color:var(--ink-2); line-height:1.7; }
  .notes h2 { font-size:13px; margin:0 0 6px; color:var(--ink); font-weight:650; }
  .notes ul { margin:0; padding-left:18px; }
  .notes a { color:var(--accent); }

  @media (max-width:720px) {
    .tiles { grid-template-columns:repeat(2,1fr); }
    h1 { font-size:21px; }
    input[type=search] { min-width:0; flex:1 1 100%; }
  }
</style>

<div class="wrap">
  <h1>大奥克兰房价热力图</h1>
  <p class="sub">
    按郊区（suburb）着色的<b>平均房产估值</b>（Average House Value），数据截至 <b id="asAt"></b>。
    颜色像气温图：<b>越红越贵，越蓝越便宜</b>，灰白色 = 接近全区中位水平。
    <b>点击任一郊区</b>可查看该区简介与区内逐街区的房价热力图。
  </p>

  <div class="tiles" id="tiles"></div>

  <div class="bar">
    <div class="seg" role="group" aria-label="配色标准">
      <button data-mode="ratio" aria-pressed="true">相对中位数</button>
      <button data-mode="rank" aria-pressed="false">分位排名</button>
    </div>
    <div class="seg" role="group" aria-label="视野">
      <button data-view="urban" aria-pressed="true">城区</button>
      <button data-view="full" aria-pressed="false">全区</button>
    </div>
    <input type="search" id="q" placeholder="搜索郊区，例如 Remuera / Albany" list="names" autocomplete="off">
    <datalist id="names"></datalist>
    <span class="spacer"></span>
    <div class="seg"><button id="toggleTable" aria-pressed="false">数据表</button></div>
  </div>

  <div class="stage">
    <svg id="map" role="img" aria-label="大奥克兰各郊区平均房产估值热力图"></svg>
    <div class="hint">滚轮缩放 · 拖拽平移 · 悬停看数据 · 点击进入该区详情</div>
    <div id="tip" role="status"></div>
  </div>

  <div class="legend">
    <div class="cap" id="legendCap"></div>
    <div class="lbar" id="lbar"><div class="cursor" id="lcursor"></div></div>
    <div class="ticks" id="lticks"></div>
  </div>

  <div id="detail" hidden>
    <div class="dbar">
      <button id="back">← 返回全区地图</button>
      <span class="dname" id="dName"></span>
      <span class="dkind" id="dKind"></span>
    </div>
    <div class="dgrid">
      <div id="dGeo">
        <div class="dstage">
          <canvas id="dmap"></canvas>
          <div class="hint" id="dHint"></div>
          <div id="dtip"></div>
        </div>
        <div class="legend">
          <div class="cap" id="dLegendCap"></div>
          <div class="lbar" id="dLbar"><div class="cursor" id="dLcursor"></div></div>
          <div class="ticks" id="dLticks"></div>
        </div>
      </div>
      <div class="dside" id="dSide"></div>
    </div>
  </div>

  <div id="tableWrap" hidden>
    <table id="tbl">
      <thead><tr>
        <th data-k="n">郊区</th>
        <th data-k="p" aria-sort="descending">平均估值</th>
        <th data-k="y">年变化</th>
        <th data-k="g">长期年增长</th>
        <th data-k="r">周租金中位</th>
        <th data-k="i">估算租金回报</th>
        <th data-k="s">中位售出天数</th>
        <th data-k="c">近 12 月成交</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="notes">
    <h2>关于数据</h2>
    <ul>
      <li><b>指标：</b>各郊区「平均房产估值」（对区内全部住宅的自动估值取平均），<em>不是</em>成交价中位数。同期全奥克兰的成交中位价为 <b id="saleMed"></b>，两者口径不同，不可直接比较。</li>
      <li><b>价格来源：</b>Opes Partners 各郊区市场页（数据更新于 <span id="lu"></span>）。</li>
      <li><b>边界来源：</b>LINZ《NZ Suburbs and Localities》（CC BY 4.0），已做约 22 米的几何简化。</li>
      <li><b>配色：</b>发散色阶，中点 = 各郊区估值的中位数；「相对中位数」按与中位数的倍数取对数着色，「分位排名」按排名百分位着色。</li>
      <li><b>区内热力图：</b>点开某个郊区后看到的是<b>政府估价 CV</b>（Auckland Council 2024-05-01 估值，用于计算 rates），
        来自议会公开的逐地块估价图层，全区 <span id="nUnits"></span> 个计税单元落入郊区边界。
        每格约 35 米，取格内 CV 中位数；道路、绿地等格内无地块时，若周围有 3 个及以上相邻格有值，则用邻格中位数补齐，其余留空。
        色阶中点是<b>该郊区自身的</b> CV 中位数，所以每个区都用满整条色带，不同区之间的颜色不可横向比较。</li>
      <li><b>CV 的口径：</b>政府估价不是成交价，且包含全部计税单元——公寓单元、商铺、工业地都在内。
        所以公寓密集处会出现成片低值（那是"一套公寓多少钱"，不是"一栋房子多少钱"），
        Penrose 这类工业区的 CV 中位数也会明显高于住宅口径。</li>
      <li><b>郊区简介：</b>英文维基百科（CC BY-SA 4.0），按坐标距离核对后匹配，205 个郊区中 204 个有条目。</li>
      <li><b>覆盖范围：</b>共 <span id="nTotal"></span> 个郊区/地区，其中 <span id="nPriced"></span> 个有价格数据。斜纹区块无价格数据，多为农村、林地、机场、医院等，但也包含少数住宅区（如 Western Springs、Westgate、Hillpark、Wairau Valley）——价格源未收录。大堡岛（Aotea / Great Barrier）等外海岛屿不在 LINZ 郊区图层内，故未绘制。</li>
    </ul>
  </div>
</div>

<script>
const DATA = /*__DATA__*/null;

const $ = s => document.querySelector(s);
const svg = $('#map'), tip = $('#tip');
const fmt = n => '$' + Math.round(n).toLocaleString('en-NZ');
const fmtK = n => n >= 1e6 ? '$' + (n/1e6).toFixed(2) + 'M' : '$' + Math.round(n/1000) + 'k';

const all = DATA.suburbs;
const priced = all.filter(s => s.p).sort((a,b) => a.p - b.p);
const sortedPrices = priced.map(s => s.p);
const MID = DATA.midPrice;
// Ramp ends at half and double the median. Round, readable, and it spends the
// colour range on the band almost every suburb actually falls in; the handful
// outside (Herne Bay at x2.58, Auckland Central at x0.41) clamp to the ends.
const K = 1;

let ramp = DATA.rampLight;
const isDark = () => {
  const t = document.documentElement.getAttribute('data-theme');
  return t === 'dark' || (t !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches);
};
const syncRamp = () => { ramp = isDark() ? DATA.rampDark : DATA.rampLight; };

let mode = 'ratio';

// value -> 0..1 position on the diverging ramp
function pos(p) {
  if (mode === 'ratio') {
    return 0.5 + 0.5 * Math.max(-1, Math.min(1, Math.log2(p / MID) / K));
  }
  let lo = 0, hi = sortedPrices.length;
  while (lo < hi) { const m = (lo + hi) >> 1; sortedPrices[m] < p ? lo = m + 1 : hi = m; }
  return sortedPrices.length > 1 ? lo / (sortedPrices.length - 1) : 0.5;
}
const colorOf = p => ramp[Math.round(pos(p) * (ramp.length - 1))];
// price at ramp position t, for the legend ticks
const priceAt = t => mode === 'ratio'
  ? MID * Math.pow(2, K * (2 * t - 1))
  : sortedPrices[Math.min(sortedPrices.length - 1, Math.round(t * (sortedPrices.length - 1)))];

/* ---------- map ---------- */
const NS = 'http://www.w3.org/2000/svg';
const nodes = new Map();
{
  // Suburbs with no price get a hatch, not a flat grey — a flat grey would be
  // indistinguishable from the neutral middle of the diverging ramp.
  svg.insertAdjacentHTML('afterbegin',
    '<defs><pattern id="nd" patternUnits="userSpaceOnUse" width="12" height="12"' +
    ' patternTransform="rotate(45)">' +
    '<rect id="hatchBg" width="12" height="12"/>' +
    '<line id="hatchLine" x1="0" y1="0" x2="0" y2="12" stroke-width="3"/>' +
    '</pattern></defs>');
  const frag = document.createDocumentFragment();
  for (const s of all) {
    const el = document.createElementNS(NS, 'path');
    el.setAttribute('d', s.d);
    el.dataset.n = s.n;
    const t = document.createElementNS(NS, 'title');
    t.textContent = s.p ? `${s.n} — ${fmt(s.p)}` : `${s.n} — 无数据`;
    el.appendChild(t);
    frag.appendChild(el);
    nodes.set(s.n, el);
  }
  svg.appendChild(frag);
}

function paint() {
  syncRamp();
  for (const s of all) nodes.get(s.n).setAttribute('fill', s.p ? colorOf(s.p) : 'url(#nd)');
  drawLegend();
}

// Keep the hatch at a constant on-screen size as the map zooms.
function sizeHatch() {
  const r = svg.getBoundingClientRect();
  if (!r.width) return;
  const unitsPerPx = svg.viewBox.baseVal.width / r.width;
  const tile = Math.max(2, 9 * unitsPerPx);
  const pat = svg.querySelector('#nd');
  pat.setAttribute('width', tile);
  pat.setAttribute('height', tile);
  const bg = svg.querySelector('#hatchBg');
  bg.setAttribute('width', tile);
  bg.setAttribute('height', tile);
  const ln = svg.querySelector('#hatchLine');
  ln.setAttribute('y2', tile);
  ln.setAttribute('stroke-width', tile / 4);
}

/* ---------- viewport ---------- */
const FULL = { x: 0, y: 0, w: DATA.viewW, h: DATA.viewH };
const URBAN = DATA.urbanView;
let vb = { ...URBAN };

function writeVB(x, y, w, h) {
  svg.setAttribute('viewBox', `${x} ${y} ${w} ${h}`);
  sizeHatch();
}
function applyVB() {
  const r = svg.getBoundingClientRect();
  const aspect = r.width / r.height;
  let { x, y, w, h } = vb;
  // letterbox the stored box into the element's aspect ratio
  if (w / h > aspect) { const nh = w / aspect; y -= (nh - h) / 2; h = nh; }
  else { const nw = h * aspect; x -= (nw - w) / 2; w = nw; }
  writeVB(x, y, w, h);
}
function setView(box, pad = 1.06) {
  const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
  vb = { x: cx - box.w * pad / 2, y: cy - box.h * pad / 2, w: box.w * pad, h: box.h * pad };
  applyVB();
}
addEventListener('resize', applyVB);

svg.addEventListener('wheel', e => {
  e.preventDefault();
  const r = svg.getBoundingClientRect();
  const box = svg.viewBox.baseVal;
  const px = box.x + (e.clientX - r.left) / r.width * box.width;
  const py = box.y + (e.clientY - r.top) / r.height * box.height;
  const f = Math.exp(e.deltaY * 0.0016);
  const w = Math.max(DATA.viewW / 400, Math.min(DATA.viewW * 1.4, box.width * f));
  const k = w / box.width;
  vb = { x: px - (px - box.x) * k, y: py - (py - box.y) * k, w, h: box.height * k };
  writeVB(vb.x, vb.y, vb.w, vb.h);
}, { passive: false });

let drag = null;
svg.addEventListener('pointerdown', e => {
  const b = svg.viewBox.baseVal;
  drag = { x: e.clientX, y: e.clientY, box: { x: b.x, y: b.y, w: b.width, h: b.height } };
  svg.setPointerCapture(e.pointerId);
  svg.classList.add('dragging');
});
svg.addEventListener('pointermove', e => {
  if (!drag) return;
  const r = svg.getBoundingClientRect();
  const dx = (e.clientX - drag.x) / r.width * drag.box.w;
  const dy = (e.clientY - drag.y) / r.height * drag.box.h;
  vb = { x: drag.box.x - dx, y: drag.box.y - dy, w: drag.box.w, h: drag.box.h };
  writeVB(vb.x, vb.y, vb.w, vb.h);
});
const endDrag = e => { if (drag) { drag = null; svg.classList.remove('dragging'); } };
svg.addEventListener('pointerup', endDrag);
svg.addEventListener('pointercancel', endDrag);

/* ---------- hover ---------- */
const byName = new Map(all.map(s => [s.n, s]));
const pct = v => (v > 0 ? '+' : '') + v.toFixed(1) + '%';

function showTip(s, e) {
  const rows = [];
  if (s.p) {
    const rel = s.p / MID;
    rows.push(['相对全区中位', (rel >= 1 ? '×' + rel.toFixed(2) : '×' + rel.toFixed(2))]);
    if (s.y != null) rows.push(['过去一年', `<span class="${s.y >= 0 ? 'up' : 'down'}">${pct(s.y)}</span>`]);
    if (s.g != null) rows.push(['长期年增长', s.g.toFixed(1) + '%']);
    if (s.r) rows.push(['周租金中位', '$' + s.r]);
    if (s.i) rows.push(['估算租金回报', s.i.toFixed(1) + '%']);
    if (s.s) rows.push(['中位售出天数', s.s + ' 天']);
    if (s.c) rows.push(['近 12 月成交', s.c + ' 套']);
  }
  tip.innerHTML =
    `<div class="t">${s.n}</div>` +
    (s.p ? `<div class="big">${fmt(s.p)}</div>` : `<div class="big" style="font-size:14px;color:var(--muted)">暂无价格数据</div>`) +
    (rows.length ? '<dl>' + rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('') + '</dl>' : '');
  tip.style.opacity = 1;
  const st = svg.parentElement.getBoundingClientRect();
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  let x = e.clientX - st.left + 16, y = e.clientY - st.top + 16;
  if (x + tw > st.width - 8) x = e.clientX - st.left - tw - 16;
  if (y + th > st.height - 8) y = Math.max(8, e.clientY - st.top - th - 16);
  tip.style.left = x + 'px';
  tip.style.top = y + 'px';
  if (s.p) {
    const c = $('#lcursor');
    c.style.opacity = 1;
    c.style.left = (pos(s.p) * 100) + '%';
  }
}

let hovered = null;
svg.addEventListener('pointermove', e => {
  if (drag) return;
  const el = e.target.closest('path');
  const name = el && el.dataset.n;
  if (name !== hovered) {
    if (hovered) nodes.get(hovered).classList.remove('hi');
    hovered = name || null;
    if (hovered) nodes.get(hovered).classList.add('hi');
  }
  if (hovered) showTip(byName.get(hovered), e);
  else { tip.style.opacity = 0; $('#lcursor').style.opacity = 0; }
});
svg.addEventListener('pointerleave', () => {
  if (hovered) { nodes.get(hovered).classList.remove('hi'); hovered = null; }
  tip.style.opacity = 0;
  $('#lcursor').style.opacity = 0;
});

/* ---------- legend ---------- */
function drawLegend() {
  $('#lbar').style.background = `linear-gradient(to right, ${ramp.join(',')})`;
  const ts = [0, .25, .5, .75, 1];
  $('#lticks').innerHTML = ts.map((t, i) => {
    const p = priceAt(t);
    const lead = mode === 'ratio' ? (i === 0 ? '≤' : i === ts.length - 1 ? '≥' : '') : '';
    const sub = mode === 'ratio'
      ? '×' + (p / MID).toFixed(2).replace(/0$/, '')
      : Math.round(t * 100) + '%';
    return `<span>${lead}${fmtK(p)}<br><em>${sub}</em></span>`;
  }).join('');
  $('#legendCap').innerHTML = (mode === 'ratio'
    ? `平均房产估值 — 中点 ${fmt(MID)}（全区郊区中位值），色阶两端为中位数的 ½ 与 2 倍，超出部分取端点色`
    : `平均房产估值 — 按 ${sortedPrices.length} 个郊区的排名百分位展开（0% 最便宜 → 100% 最贵）`)
    + `<span class="nd"><span class="ndsw"></span>无价格数据</span>`;
}

/* ---------- tiles ---------- */
function tiles() {
  const hi = priced[priced.length - 1], lo = priced[0];
  const items = [
    ['全区郊区估值中位', fmt(MID), `${priced.length} 个郊区有数据`],
    ['最贵', fmt(hi.p), hi.n],
    ['最便宜', fmt(lo.p), lo.n],
    ['最贵 ÷ 最便宜', '×' + (hi.p / lo.p).toFixed(1), '区内价差倍数'],
  ];
  $('#tiles').innerHTML = items.map(([k, v, m]) =>
    `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="m">${m}</div></div>`).join('');
}

/* ---------- table ---------- */
let sortK = 'p', sortAsc = false;
function drawTable() {
  const rows = [...all].sort((a, b) => {
    const av = a[sortK], bv = b[sortK];
    if (av == null && bv == null) return a.n.localeCompare(b.n);
    if (av == null) return 1;
    if (bv == null) return -1;
    const c = typeof av === 'string' ? av.localeCompare(bv) : av - bv;
    return sortAsc ? c : -c;
  });
  const num = (v, s = '', d = 0) => v == null ? '—' : (s === '$' ? '$' + v.toLocaleString('en-NZ') : v.toFixed(d) + s);
  $('#tbl tbody').innerHTML = rows.map(s => `<tr data-n="${s.n}" style="cursor:pointer">
    <td><span class="swatch${s.p ? '' : ' nodata'}" style="${s.p ? `background:${colorOf(s.p)}` : ''}"></span>${s.n}</td>
    <td>${s.p ? fmt(s.p) : '—'}</td>
    <td class="${s.y == null ? '' : s.y >= 0 ? 'up' : 'down'}">${s.y == null ? '—' : pct(s.y)}</td>
    <td>${num(s.g, '%', 1)}</td>
    <td>${s.r ? '$' + s.r : '—'}</td>
    <td>${num(s.i, '%', 1)}</td>
    <td>${s.s ?? '—'}</td>
    <td>${s.c ?? '—'}</td></tr>`).join('');
  document.querySelectorAll('#tbl th').forEach(th => {
    if (th.dataset.k === sortK) th.setAttribute('aria-sort', sortAsc ? 'ascending' : 'descending');
    else th.removeAttribute('aria-sort');
  });
}
$('#tbl tbody').addEventListener('click', e => {
  const tr = e.target.closest('tr');
  if (tr && tr.dataset.n) enterDetail(tr.dataset.n);
});
document.querySelectorAll('#tbl th').forEach(th => th.addEventListener('click', () => {
  const k = th.dataset.k;
  if (k === sortK) sortAsc = !sortAsc; else { sortK = k; sortAsc = k === 'n'; }
  drawTable();
}));
$('#toggleTable').addEventListener('click', e => {
  const open = $('#tableWrap').hidden;
  $('#tableWrap').hidden = !open;
  e.currentTarget.setAttribute('aria-pressed', String(open));
  if (open) drawTable();
});

/* ---------- controls ---------- */
document.querySelectorAll('[data-mode]').forEach(b => b.addEventListener('click', () => {
  mode = b.dataset.mode;
  document.querySelectorAll('[data-mode]').forEach(o => o.setAttribute('aria-pressed', String(o === b)));
  paint();
  if (!$('#tableWrap').hidden) drawTable();
}));
document.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('[data-view]').forEach(o => o.setAttribute('aria-pressed', String(o === b)));
  setView(b.dataset.view === 'full' ? FULL : URBAN);
}));

$('#names').innerHTML = all.filter(s => s.p).map(s => `<option value="${s.n}">`).join('');
$('#q').addEventListener('input', e => {
  const v = e.target.value.trim().toLowerCase();
  document.querySelectorAll('#map path').forEach(p => p.classList.remove('dim', 'hi'));
  if (!v) return;
  const hit = all.find(s => s.n.toLowerCase() === v) || all.find(s => s.n.toLowerCase().startsWith(v));
  if (!hit) return;
  document.querySelectorAll('#map path').forEach(p => { if (p.dataset.n !== hit.n) p.classList.add('dim'); });
  const el = nodes.get(hit.n);
  el.classList.add('hi');
  const bb = el.getBBox();
  setView({ x: bb.x, y: bb.y, w: bb.width, h: bb.height }, 3.2);
});

/* ---------- suburb detail ---------- */
const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const BEDC = ['#2a78d6', '#1baf7a', '#eda100', '#eb6834', '#4a3aa7'];

// 4 bytes per grid cell: gx, gy, then the median value as a little-endian
// uint16 in thousands of dollars.
function decodeCells(b64) {
  const bin = atob(b64), n = bin.length / 4, out = new Array(n);
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    out[i] = {
      gx: bin.charCodeAt(o), gy: bin.charCodeAt(o + 1),
      v: (bin.charCodeAt(o + 2) | (bin.charCodeAt(o + 3) << 8)) * 1000,
    };
  }
  return out;
}

// Inside a suburb the ramp re-centres on that suburb's own median CV, with the
// arms reaching its 10th/90th percentile — so every suburb uses the full range
// instead of a wealthy one reading as uniformly red.
function localScale(dt) {
  const med = dt.med;
  const K = Math.max(0.18,
    Math.abs(Math.log2(dt.q[0] / med)), Math.abs(Math.log2(dt.q[4] / med)));
  return {
    med, K,
    pos: v => 0.5 + 0.5 * Math.max(-1, Math.min(1, Math.log2(v / med) / K)),
    at: t => med * Math.pow(2, K * (2 * t - 1)),
    color(v) { return ramp[Math.round(this.pos(v) * (ramp.length - 1))]; },
  };
}

let D = null;   // active detail view

function drawDetailMap() {
  if (!D || !D.dt) return;
  const cv = $('#dmap'), rect = cv.getBoundingClientRect();
  if (!rect.width) return;
  const dpr = Math.min(2, devicePixelRatio || 1);
  cv.width = Math.round(rect.width * dpr);
  cv.height = Math.round(rect.height * dpr);
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);

  const [bx, by, bw, bh] = D.s.bx;
  const pad = 8;
  const scale = Math.min((rect.width - pad * 2) / bw, (rect.height - pad * 2) / bh);
  const offX = (rect.width - bw * scale) / 2, offY = (rect.height - bh * scale) / 2;
  Object.assign(D, { scale, offX, offY, bx, by });

  ctx.save();
  ctx.translate(offX, offY);
  ctx.scale(scale, scale);
  ctx.translate(-bx, -by);

  const shape = new Path2D(D.s.d);
  ctx.fillStyle = cssVar('--nodata');
  ctx.fill(shape, 'evenodd');

  // Clip to the suburb: a 35 m cell whose centre sits just outside the boundary,
  // and the gap-fill's one-cell halo, would otherwise bleed past the coastline.
  ctx.save();
  ctx.clip(shape, 'evenodd');
  const [gx0, gy0] = D.dt.bb, cs = D.dt.cs;
  const size = cs * 1.02;   // without the overlap the cells show hairline seams
  for (const c of D.cells) {
    ctx.fillStyle = D.sc.color(c.v);
    ctx.fillRect(gx0 + c.gx * cs, gy0 + c.gy * cs, size, size);
  }
  ctx.restore();

  ctx.lineWidth = 1.4 / scale;
  ctx.strokeStyle = cssVar('--ink-2');
  ctx.stroke(shape);
  ctx.restore();
}

function cellAt(clientX, clientY) {
  const r = $('#dmap').getBoundingClientRect();
  const vx = (clientX - r.left - D.offX) / D.scale + D.bx;
  const vy = (clientY - r.top - D.offY) / D.scale + D.by;
  const gx = Math.floor((vx - D.dt.bb[0]) / D.dt.cs);
  const gy = Math.floor((vy - D.dt.bb[1]) / D.dt.cs);
  return D.lookup.get(gy * 256 + gx) || null;
}

$('#dmap').addEventListener('pointermove', e => {
  if (!D || !D.dt) return;
  const c = cellAt(e.clientX, e.clientY);
  const tip = $('#dtip'), cur = $('#dLcursor');
  if (!c) { tip.style.opacity = 0; cur.style.opacity = 0; return; }
  tip.innerHTML = `<div class="big">${fmt(c.v)}</div>` +
    `<div class="sm">该网格 CV 中位 · ×${(c.v / D.dt.med).toFixed(2)} 区内中位</div>`;
  tip.style.opacity = 1;
  const st = $('#dmap').parentElement.getBoundingClientRect();
  let x = e.clientX - st.left + 14, y = e.clientY - st.top + 14;
  if (x + tip.offsetWidth > st.width - 6) x = e.clientX - st.left - tip.offsetWidth - 14;
  if (y + tip.offsetHeight > st.height - 6) y = e.clientY - st.top - tip.offsetHeight - 14;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
  cur.style.opacity = 1;
  cur.style.left = (D.sc.pos(c.v) * 100) + '%';
});
$('#dmap').addEventListener('pointerleave', () => {
  $('#dtip').style.opacity = 0; $('#dLcursor').style.opacity = 0;
});

/* ---------- detail charts ---------- */
function lineChart(h) {
  const [y0, vals] = h, W = 320, H = 108, L = 6, R = 6, T = 8, B = 16;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const sx = i => L + i / (vals.length - 1) * (W - L - R);
  const sy = v => T + (1 - (v - lo) / Math.max(1, hi - lo)) * (H - T - B);
  const pts = vals.map((v, i) => `${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join(' ');
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" height="108">
    <polygon class="area" points="${sx(0)},${H - B} ${pts} ${sx(vals.length - 1)},${H - B}"/>
    <polyline class="line" points="${pts}"/>
    <text x="${L}" y="${H - 4}">${y0}</text>
    <text x="${W - R}" y="${H - 4}" text-anchor="end">${y0 + vals.length - 1}</text>
    <text x="${L}" y="${T + 4}">峰值 ${fmtK(hi * 1000)}</text>
  </svg>`;
}

function histChart(dt, sc) {
  const W = 320, H = 92, B = 15, n = dt.hist.length;
  const max = Math.max(...dt.hist), bw = W / n;
  const span = Math.log(dt.histHi / dt.histLo);   // bins are log-spaced
  const bars = dt.hist.map((c, i) => {
    const hgt = (c / max) * (H - B - 4);
    const mid = dt.histLo * Math.exp(span * (i + 0.5) / n);
    return `<rect x="${(i * bw + 1).toFixed(1)}" y="${(H - B - hgt).toFixed(1)}" ` +
      `width="${(bw - 2).toFixed(1)}" height="${hgt.toFixed(1)}" rx="1.5" ` +
      `fill="${sc.color(mid)}"><title>${fmtK(mid)} · ${c} 套</title></rect>`;
  }).join('');
  const mx = Math.max(0, Math.min(W, Math.log(dt.med / dt.histLo) / span * W));
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" height="92">
    ${bars}
    <line class="med" x1="${mx.toFixed(1)}" y1="2" x2="${mx.toFixed(1)}" y2="${H - B}"/>
    <text x="2" y="${H - 3}">${fmtK(dt.histLo)}</text>
    <text x="${W - 2}" y="${H - 3}" text-anchor="end">${fmtK(dt.histHi)}+</text>
  </svg>`;
}

/* ---------- detail side panel ---------- */
function sidePanel(s) {
  const dt = s.dt, out = [];
  const row = (k, v) => v == null ? '' : `<div><span>${k}</span><span>${v}</span></div>`;

  const hero = [];
  if (s.p) hero.push(`<div><div class="k">平均房产估值</div><div class="v">${fmt(s.p)}</div>
    <div class="m">×${(s.p / MID).toFixed(2)} 全区中位${s.y == null ? '' :
      ` · <span class="${s.y >= 0 ? 'up' : 'down'}">${pct(s.y)}</span> 近一年`}</div></div>`);
  if (dt) hero.push(`<div><div class="k">政府估价 CV 中位</div><div class="v">${fmt(dt.med)}</div>
    <div class="m">${dt.n.toLocaleString('en-NZ')} 个计税单元${dt.chg == null ? '' :
      ` · <span class="${dt.chg >= 0 ? 'up' : 'down'}">${pct(dt.chg * 100)}</span> vs ${DATA.prevValuationDate.slice(0, 4)}`}</div></div>`);
  if (hero.length) out.push(`<div class="card dhero">${hero.join('')}</div>`);

  if (s.w) out.push(`<div class="card"><h3>简介</h3><p class="dintro">${s.w.extract}
    <a href="${s.w.url}" target="_blank" rel="noopener">维基百科 ↗</a></p></div>`);

  const stats = [
    row('人口', s.o ? s.o.toLocaleString('en-NZ') : null),
    row('租房人口占比', s.rp == null ? null : s.rp.toFixed(1) + '%'),
    row('周租金中位', s.r ? '$' + s.r : null),
    row('估算租金回报', s.i == null ? null : s.i.toFixed(1) + '%'),
    row('长期年化增长', s.g == null ? null : s.g.toFixed(1) + '%'),
    row('中位售出天数', s.s ? s.s + ' 天' : null),
    row('近 12 月成交', s.c ? s.c + ' 套' : null),
    row('上月挂牌', s.lf ? s.lf + ' 套' : null),
    row('中位出租天数', s.dr ? s.dr + ' 天' : null),
    dt ? row('CV 四分位区间', `${fmtK(dt.q[1])} – ${fmtK(dt.q[3])}`) : '',
  ].join('');
  if (stats) out.push(`<div class="card"><h3>市场概况</h3><div class="dstats">${stats}</div></div>`);

  if (s.bm) {
    const labels = ['1 房', '2 房', '3 房', '4 房', '5+ 房'];
    const bars = s.bm.map((v, i) => v ?
      `<i style="flex:${v};background:${BEDC[i]}" title="${labels[i]} ${v}%">${v >= 12 ? v + '%' : ''}</i>` : '').join('');
    const key = s.bm.map((v, i) => v ?
      `<span><i style="background:${BEDC[i]}"></i><b>${labels[i]}</b> ${v}%${
        s.br && s.br[i] ? ` · $${s.br[i]}/周` : ''}</span>` : '').join('');
    out.push(`<div class="card"><h3>户型结构（括号为该户型周租金）</h3><div class="beds">${bars}</div>
      <div class="bedkey">${key}</div></div>`);
  }

  if (s.h) out.push(`<div class="card"><h3>房价走势 ${s.h[0]}–${s.h[0] + s.h[1].length - 1}</h3>${lineChart(s.h)}</div>`);
  if (dt) out.push(`<div class="card"><h3>区内 CV 分布（虚线 = 中位）</h3>${histChart(dt, D.sc)}</div>`);
  if (!out.length) out.push(`<div class="card"><p class="dintro">该地区没有任何计税单元与市场数据 —— 通常是集水区、林地或保护区。</p></div>`);

  $('#dSide').innerHTML = out.join('');
}

function drawDetailLegend() {
  $('#dLbar').style.background = `linear-gradient(to right, ${ramp.join(',')})`;
  $('#dLticks').innerHTML = [0, .25, .5, .75, 1].map((t, i) => {
    const v = D.sc.at(t);
    const lead = i === 0 ? '≤' : i === 4 ? '≥' : '';
    return `<span>${lead}${fmtK(v)}<br><em>×${(v / D.sc.med).toFixed(2)}</em></span>`;
  }).join('');
  $('#dLegendCap').textContent =
    `政府估价 CV（${DATA.valuationDate} 估值）— 中点是该区中位 ${fmt(D.sc.med)}，两端为区内 10 / 90 分位`;
}

/* ---------- enter / leave ---------- */
const HIDE = ['#tiles', '.bar', '.stage', '.legend', '#tableWrap'];

function enterDetail(name, push = true) {
  const s = byName.get(name);
  if (!s) return false;
  const dt = s.dt || null;
  D = { s, dt };
  if (dt) {
    D.cells = decodeCells(dt.cells);
    D.sc = localScale(dt);
    D.lookup = new Map(D.cells.map(c => [c.gy * 256 + c.gx, c]));
  }

  $('#dName').textContent = name;
  $('#dKind').textContent = s.t === 'Suburb' ? '郊区' : '地区';
  // Catchments and reserves hold no rating units, so there is no grid to draw.
  $('#dGeo').hidden = !dt;
  if (dt) {
    $('#dKind').textContent += ` · 每格约 ${Math.round(dt.cs * DATA.metresPerUnit)} 米`;
    $('#dHint').textContent = '悬停查看该网格的 CV 中位数';
    // let the canvas take the suburb's own shape rather than letterboxing it
    $('#dmap').style.aspectRatio = Math.max(0.72, Math.min(2, s.bx[2] / s.bx[3])).toFixed(3);
  }
  HIDE.forEach(sel => { const el = document.querySelector(sel); if (el) el.style.display = 'none'; });
  $('#detail').hidden = false;
  if (dt) drawDetailLegend();
  sidePanel(s);
  drawDetailMap();
  if (push) location.hash = encodeURIComponent(name);
  scrollTo(0, 0);
  return true;
}

function exitDetail() {
  D = null;
  if (hovered) { nodes.get(hovered).classList.remove('hi'); hovered = null; }
  $('#detail').hidden = true;
  HIDE.forEach(sel => { const el = document.querySelector(sel); if (el) el.style.display = ''; });
  if (location.hash) history.replaceState(null, '', location.pathname + location.search);
  applyVB();
}

$('#back').addEventListener('click', () => exitDetail());
addEventListener('keydown', e => { if (e.key === 'Escape' && D) exitDetail(); });
addEventListener('resize', drawDetailMap);
addEventListener('hashchange', () => {
  const n = location.hash ? decodeURIComponent(location.hash.slice(1)) : '';
  if (!n) { if (D) exitDetail(); }
  else if (!D || D.s.n !== n) enterDetail(n, false);
});

// A click is a pointerup that didn't travel far — anything more was a pan.
let downAt = null;
svg.addEventListener('pointerdown', e => { downAt = { x: e.clientX, y: e.clientY }; });
svg.addEventListener('pointerup', e => {
  if (!downAt) return;
  const moved = Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y);
  downAt = null;
  if (moved > 5) return;
  // setPointerCapture retargets pointerup to the <svg>, so hit-test by point.
  const under = document.elementFromPoint(e.clientX, e.clientY);
  const el = (under && under.closest) ? under.closest('#map path') : null;
  const name = (el && el.dataset.n) || hovered;
  if (name) enterDetail(name);
});

/* ---------- boot ---------- */
$('#asAt').textContent = DATA.asAt;
$('#lu').textContent = DATA.lastUpdated;
$('#saleMed').textContent = fmt(DATA.regionSaleMedian);
$('#nTotal').textContent = all.length;
$('#nPriced').textContent = priced.length;
$('#nUnits').textContent = DATA.unitsMatched.toLocaleString('en-NZ');
tiles();
paint();
applyVB();
setView(URBAN);
function repaint() {
  paint();
  if (!$('#tableWrap').hidden) drawTable();
  if (D) { drawDetailLegend(); sidePanel(D.s); drawDetailMap(); }
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', repaint);
new MutationObserver(repaint)
  .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

if (location.hash) enterDetail(decodeURIComponent(location.hash.slice(1)), false);
</script>
