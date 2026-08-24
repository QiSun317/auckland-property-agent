<title>大奥克兰房价热力图 · Auckland House Price Heat Map</title>
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

  .titlerow { display:flex; align-items:flex-start; gap:14px; }
  .titlerow h1 { flex:1; }
  .langseg { flex:0 0 auto; margin-top:2px; }
  .langseg button { padding:5px 11px; font-size:12.5px; }
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

  #changed {
    display:flex; gap:9px; align-items:baseline; flex-wrap:wrap;
    font-size:12.5px; color:var(--ink-2); margin:-6px 0 16px;
    padding:9px 12px; border-left:3px solid var(--accent);
    background:var(--surface); border-radius:0 6px 6px 0;
  }
  #changed[hidden] { display:none; }
  #changed b { color:var(--ink); font-weight:600; }
  #changed .lab {
    font-size:11px; letter-spacing:.06em; text-transform:uppercase;
    color:var(--accent); font-weight:650; flex:0 0 auto;
  }
  /* Not .up/.down — those already mean "house value rose" elsewhere on this
     page and are coloured the other way round. A rate going up is bad news;
     the same class name meaning the opposite thing a screen apart is how a
     later edit gets it backwards. */
  #changed .worse { color:#d03b3b; } #changed .better { color:#0ca30c; }

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
  #map path.faded { opacity:.25; }
  #map path.focus {
    stroke:var(--ink); stroke-width:2.5; paint-order:stroke;
    filter:drop-shadow(0 0 6px var(--accent));
  }
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
  .smoothseg { margin-left:auto; }
  .smoothseg button { padding:5px 11px; font-size:12px; }
  .dname { font-size:24px; font-weight:650; letter-spacing:-.01em; }
  .dkind { font-size:12.5px; color:var(--muted); }

  .dgrid { display:grid; grid-template-columns:minmax(0,1.25fr) minmax(0,1fr); gap:18px; align-items:start; }
  .dstage {
    position:relative; background:var(--surface); border:1px solid var(--ring);
    border-radius:10px; overflow:hidden;
  }
  #dmap { display:block; width:100%; aspect-ratio:1/1; max-height:62vh;
          touch-action:none; cursor:grab; }
  #dmap.dragging { cursor:grabbing; }
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


  /* ---- 选房助手 ---- */
  #aiToggle {
    position:fixed; right:20px; bottom:20px; z-index:40;
    font:inherit; font-size:14px; font-weight:600; padding:11px 18px;
    border:0; border-radius:24px; cursor:pointer;
    background:var(--accent); color:#fff; box-shadow:0 6px 22px var(--shadow);
  }
  #aiToggle:hover { filter:brightness(1.08); }
  #aiPanel {
    position:fixed; right:20px; bottom:20px; z-index:41;
    width:min(420px, calc(100vw - 40px)); max-height:min(760px, calc(100vh - 40px));
    display:flex; flex-direction:column;
    background:var(--surface); border:1px solid var(--ring); border-radius:14px;
    box-shadow:0 12px 44px var(--shadow); overflow:hidden;
  }
  #aiPanel[hidden], #aiToggle[hidden] { display:none; }
  .aihead {
    display:flex; align-items:center; gap:9px; padding:12px 14px;
    border-bottom:1px solid var(--hair); flex:0 0 auto;
  }
  .aihead b { font-size:14.5px; }
  .aihead .tag {
    font-size:11px; color:var(--accent); border:1px solid currentColor;
    border-radius:4px; padding:1px 6px;
  }
  .aihead .sp { flex:1; }
  .aihead button {
    font:inherit; font-size:16px; line-height:1; padding:4px 7px; cursor:pointer;
    border:0; background:transparent; color:var(--muted); border-radius:5px;
  }
  .aihead button:hover { color:var(--ink); background:var(--hair); }

  #aiLog { flex:1 1 auto; overflow-y:auto; padding:14px; display:flex;
           flex-direction:column; gap:12px; font-size:13px; }
  .msg-user {
    align-self:flex-end; max-width:85%; background:var(--accent); color:#fff;
    padding:8px 12px; border-radius:12px 12px 3px 12px; line-height:1.5;
  }
  .msg-ai { line-height:1.6; color:var(--ink-2); }
  .msg-ai b { color:var(--ink); }
  .msg-ai .warn { color:#d03b3b; }
  .msg-ai .muted-note { color:var(--muted); font-size:11.5px; }

  .rec {
    border:1px solid var(--ring); border-radius:10px; padding:11px 12px;
    background:var(--plane); margin-top:9px;
  }
  .rec .top { display:flex; align-items:baseline; gap:8px; }
  .rec .nm { font-size:15px; font-weight:650; color:var(--ink); }
  .rec .zn { font-size:11.5px; color:var(--muted); }
  .rec .rank {
    margin-left:auto; font-size:11px; color:var(--muted);
    font-variant-numeric:tabular-nums;
  }
  .rec .price { font-size:12.5px; color:var(--ink-2); margin:5px 0 1px;
                font-variant-numeric:tabular-nums; }
  .rec .price b { color:var(--ink); font-size:16px; }
  .rec .price2 { font-size:11px; color:var(--muted); margin:0 0 7px;
                 font-variant-numeric:tabular-nums; }
  .fitbar {
    height:6px; border-radius:3px; background:var(--hair); overflow:hidden; margin:6px 0 3px;
  }
  .fitbar i { display:block; height:100%; background:var(--accent); }
  .fitcap { font-size:11px; color:var(--muted); margin-bottom:8px; }
  .rec .why { margin:2px 0 8px; line-height:1.6; color:var(--ink-2); }
  .rec ul { margin:0 0 6px; padding-left:16px; }
  .rec li { margin:2px 0; line-height:1.5; }
  .rec li.pro::marker { content:"＋ "; color:#0ca30c; }
  .rec li.con::marker { content:"－ "; color:#d03b3b; }
  .rec .go {
    font:inherit; font-size:12px; padding:5px 11px; margin-top:4px; cursor:pointer;
    border:1px solid var(--ring); border-radius:6px;
    background:var(--surface); color:var(--accent); font-weight:600;
  }
  .rec .go:hover { background:var(--accent); color:#fff; border-color:transparent; }

  #aiChips { display:flex; gap:6px; flex-wrap:wrap; padding:0 14px 10px; }
  #aiChips button {
    font:inherit; font-size:11.5px; padding:5px 10px; cursor:pointer;
    border:1px solid var(--ring); border-radius:14px;
    background:var(--surface); color:var(--ink-2);
  }
  #aiChips button:hover { color:var(--ink); border-color:var(--accent); }

  #aiForm { display:flex; gap:8px; padding:10px 14px; border-top:1px solid var(--hair);
            flex:0 0 auto; align-items:flex-end; }
  #aiInput {
    flex:1; font:inherit; font-size:13px; padding:8px 10px; resize:none;
    border:1px solid var(--ring); border-radius:8px; min-height:38px; max-height:110px;
    background:var(--plane); color:var(--ink); line-height:1.45;
  }
  #aiInput:focus { outline:2px solid var(--accent); outline-offset:-1px; }
  #aiForm button {
    font:inherit; font-size:13px; font-weight:600; padding:9px 14px; cursor:pointer;
    border:0; border-radius:8px; background:var(--accent); color:#fff;
  }
  #aiForm button:disabled { opacity:.5; cursor:default; }
  .aifoot {
    padding:0 14px 11px; font-size:11px; color:var(--muted);
    display:flex; align-items:center; gap:8px;
  }
  .aifoot button {
    font:inherit; font-size:11px; padding:3px 8px; cursor:pointer;
    border:1px solid var(--ring); border-radius:5px;
    background:var(--surface); color:var(--ink-2);
  }
  .aifoot .on { color:#0ca30c; }

  @media (max-width:520px) {
    #aiPanel { right:10px; left:10px; bottom:10px; width:auto; }
    #aiToggle { right:12px; bottom:12px; }
  }

  /* ---- 房贷与地税试算 ---- */
  .calcwrap { margin-top:16px; }
  .calcwrap > summary {
    cursor:pointer; font-size:13px; color:var(--ink-2); list-style:none;
    display:flex; align-items:center; gap:8px; padding:9px 12px;
    background:var(--surface); border:1px solid var(--ring); border-radius:8px;
  }
  .calcwrap > summary::-webkit-details-marker { display:none; }
  .calcwrap > summary::before { content:"▸"; color:var(--muted); font-size:11px; }
  .calcwrap[open] > summary::before { content:"▾"; }
  .calcwrap > summary:hover { color:var(--ink); }
  .calcwrap > summary b { color:var(--ink); font-weight:600; }
  .calcwrap[open] > summary { border-radius:8px 8px 0 0; border-bottom:0; }
  .calcwrap .card { border-radius:0 0 8px 8px; }

  .calcin { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px 12px; }
  .calcin label { display:block; font-size:11.5px; color:var(--muted); margin-bottom:3px; }
  .calcin .fld { min-width:0; }
  .calcin .fld.wide { grid-column:1 / -1; }
  .calcin input[type=number], .calcin select {
    font:inherit; font-size:13px; width:100%; padding:6px 9px;
    border:1px solid var(--ring); border-radius:7px;
    background:var(--plane); color:var(--ink); font-variant-numeric:tabular-nums;
  }
  .calcin input:focus, .calcin select:focus { outline:2px solid var(--accent); outline-offset:-1px; }
  .calcin .unit { position:relative; }
  .calcin .unit input { padding-right:26px; }
  .calcin .unit i {
    position:absolute; right:9px; top:50%; transform:translateY(-50%);
    font-style:normal; font-size:12px; color:var(--muted); pointer-events:none;
  }
  .ratechips { display:flex; gap:5px; flex-wrap:wrap; margin-top:6px; grid-column:1 / -1; }
  .ratechips button {
    font:inherit; font-size:11px; padding:4px 8px; cursor:pointer;
    border:1px solid var(--ring); border-radius:13px;
    background:var(--surface); color:var(--ink-2);
    font-variant-numeric:tabular-nums; white-space:nowrap;
  }
  .ratechips button:hover { color:var(--ink); border-color:var(--accent); }
  .ratechips button[aria-pressed="true"] { background:var(--accent); color:#fff; border-color:transparent; }

  .calcout { margin-top:13px; padding-top:12px; border-top:1px solid var(--hair); }
  .calcbig { display:flex; align-items:baseline; gap:9px; flex-wrap:wrap; }
  .calcbig .v { font-size:27px; font-weight:600; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }
  .calcbig .k { font-size:12px; color:var(--muted); }
  .calcrows { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:6px 18px;
              font-size:12.5px; margin-top:10px; }
  .calcrows div { display:flex; justify-content:space-between; gap:10px;
                  border-bottom:1px solid var(--hair); padding-bottom:4px; }
  .calcrows span:first-child { color:var(--muted); font-size:12px; }
  .calcrows span:last-child { font-variant-numeric:tabular-nums; white-space:nowrap; }
  .calcrows .full { grid-column:1 / -1; }

  .calctot {
    margin-top:11px; padding:9px 11px; border-radius:8px; background:var(--plane);
    border:1px solid var(--ring); display:flex; align-items:baseline; gap:8px;
    flex-wrap:wrap; font-variant-numeric:tabular-nums;
  }
  .calctot .v { font-size:18px; font-weight:650; }
  .calctot .k { font-size:11.5px; color:var(--muted); }
  .calctot .k b { color:var(--ink-2); font-weight:500; }

  .calcflag { margin-top:9px; font-size:11.5px; line-height:1.6; color:#b3701c; }
  .calcflag.bad { color:#d03b3b; }
  .calcbreak { margin-top:10px; font-size:11.5px; }
  .calcbreak summary { cursor:pointer; color:var(--muted); }
  .calcbreak summary:hover { color:var(--ink-2); }
  .calcbreak .calcrows { margin-top:8px; font-size:12px; }
  .calcnote { margin:10px 0 0; font-size:11px; line-height:1.65; color:var(--muted); }
  .calcnote a { color:var(--accent); }
  .rec .cost { font-size:11px; color:var(--muted); margin:0 0 7px;
               font-variant-numeric:tabular-nums; }
  .rec .cost b { color:var(--ink-2); font-weight:600; }

  .rec.assess .verdict { margin:6px 0 8px; font-size:12.5px; color:var(--ink-2); }
  .rec.assess .verdict b { color:var(--ink); }
  .astats { grid-template-columns:repeat(2,minmax(0,1fr)); gap:5px 14px;
            font-size:12px; margin:8px 0 10px; }
  .astats div { border-bottom:1px solid var(--hair); padding-bottom:4px; }

  .cmp { margin-top:9px; }
  .cmp table { border-collapse:collapse; width:100%; font-size:12.5px; min-width:340px; }
  .cmp th, .cmp td { padding:6px 10px; border-bottom:1px solid var(--hair); text-align:right;
                     font-variant-numeric:tabular-nums; white-space:nowrap; }
  .cmp thead th { text-align:right; font-weight:650; color:var(--ink); font-size:13px; }
  .cmp thead th em { display:block; font-style:normal; font-size:10.5px;
                     color:var(--muted); font-weight:400; }
  .cmp tbody th { text-align:left; font-weight:400; color:var(--muted); font-size:11.5px; }
  .cmp td.win { color:var(--ink); font-weight:650; background:var(--hair); border-radius:3px; }
  .cmpnote { font-size:11px; color:var(--muted); line-height:1.55; margin:8px 0 0; }

  .ranktbl { border-collapse:collapse; width:100%; font-size:12.5px; }
  .ranktbl td { padding:5px 9px; border-bottom:1px solid var(--hair); }
  .ranktbl td.n { color:var(--muted); width:1.6em; font-variant-numeric:tabular-nums; }
  .ranktbl td.z { color:var(--muted); font-size:11px; }
  .ranktbl td.v { text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }
  #aiLog .tw { overflow-x:auto; margin:6px 0; }

  @media (max-width:560px) {
    .calcin, .calcrows { grid-template-columns:1fr; }
  }

  .prov { border-collapse:collapse; font-size:12px; margin:0 0 4px;
          font-variant-numeric:tabular-nums; }
  .prov td { padding:3px 16px 3px 0; border-bottom:1px solid var(--hair); }
  .prov td:first-child { color:var(--ink-2); }
  .prov td:last-child { color:var(--muted); }
  .stale { color:#d03b3b; margin:8px 0 0; }

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
  <div class="titlerow">
    <h1 data-zh="大奥克兰房价热力图" data-en="Auckland House Price Heat Map">大奥克兰房价热力图</h1>
    <div class="seg langseg" role="group" aria-label="Language">
      <button data-lang="zh" aria-pressed="true">中文</button>
      <button data-lang="en" aria-pressed="false">EN</button>
    </div>
  </div>
  <p class="sub">
    <span id="subCopy"></span>
  </p>

  <div class="tiles" id="tiles"></div>
  <div id="changed" hidden></div>

  <div class="bar">
    <div class="seg" role="group" data-zh-aria="配色标准" data-en-aria="Colour scale">
      <button data-mode="ratio" aria-pressed="true" data-zh="相对中位数" data-en="Vs median">相对中位数</button>
      <button data-mode="rank" aria-pressed="false" data-zh="分位排名" data-en="Percentile">分位排名</button>
    </div>
    <div class="seg" role="group" data-zh-aria="视野" data-en-aria="Extent">
      <button data-view="urban" aria-pressed="true" data-zh="城区" data-en="Urban">城区</button>
      <button data-view="full" aria-pressed="false" data-zh="全区" data-en="Whole region">全区</button>
    </div>
    <input type="search" id="q" data-zh-ph="搜索郊区，例如 Remuera / Albany" data-en-ph="Search a suburb, e.g. Remuera" list="names" autocomplete="off">
    <datalist id="names"></datalist>
    <span class="spacer"></span>
    <div class="seg"><button id="toggleCalc" aria-pressed="false" data-zh="房贷 / 地税" data-en="Mortgage">房贷 / 地税</button></div>
    <div class="seg"><button id="toggleTable" aria-pressed="false" data-zh="数据表" data-en="Table">数据表</button></div>
  </div>

  <div class="stage">
    <svg id="map" role="img" data-zh-aria="大奥克兰各郊区平均房产估值热力图" data-en-aria="Heat map of average house value by Auckland suburb"></svg>
    <div class="hint" data-zh="滚轮缩放 · 拖拽平移 · 悬停看数据 · 点击进入该区详情" data-en="Scroll to zoom · drag to pan · hover for figures · click a suburb">滚轮缩放</div>
    <div id="tip" role="status"></div>
  </div>

  <div class="legend">
    <div class="cap" id="legendCap"></div>
    <div class="lbar" id="lbar"><div class="cursor" id="lcursor"></div></div>
    <div class="ticks" id="lticks"></div>
  </div>

  <details class="calcwrap" id="calcMain">
    <summary id="calcSummary"></summary>
    <div id="calcMainSlot"></div>
  </details>

  <div id="detail" hidden>
    <div class="dbar">
      <button id="back" data-zh="← 返回全区地图" data-en="← Back to the region">← 返回全区地图</button>
      <span class="dname" id="dName"></span>
      <span class="dkind" id="dKind"></span>
      <div class="seg smoothseg" role="group" data-zh-aria="渲染方式" data-en-aria="Rendering">
        <button id="smOn" data-zh="平滑" data-en="Smooth">平滑</button>
        <button id="smOff" data-zh="网格" data-en="Grid">网格</button>
      </div>
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
        <th data-k="n" data-zh="郊区" data-en="Suburb">郊区</th>
        <th data-k="p" aria-sort="descending" data-zh="平均估值" data-en="Avg value">平均估值</th>
        <th data-k="y" data-zh="年变化" data-en="1yr change">年变化</th>
        <th data-k="g" data-zh="长期年增长" data-en="Long-term growth">长期年增长</th>
        <th data-k="r" data-zh="周租金中位" data-en="Median rent/wk">周租金中位</th>
        <th data-k="i" data-zh="估算租金回报" data-en="Est. yield">估算租金回报</th>
        <th data-k="s" data-zh="中位售出天数" data-en="Days to sell">中位售出天数</th>
        <th data-k="c" data-zh="近 12 月成交" data-en="Sold 12m">近 12 月成交</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="notes" id="notes"></div>
</div>

<button id="aiToggle" data-zh="🏠 选房助手" data-en="🏠 Suburb finder">🏠 选房助手</button>
<div id="aiPanel" hidden>
  <div class="aihead">
    <b data-zh="选房助手" data-en="Suburb finder">选房助手</b><span class="tag" data-zh="预算优先" data-en="Budget first">预算优先</span><span class="sp"></span>
    <button id="aiClose" data-zh-title="收起" data-en-title="Close">×</button>
  </div>
  <div id="aiLog"></div>
  <div id="aiChips">
    <button data-zh="预算 110 万，三房，北岸" data-en="Budget $1.1m, 3 bedrooms, North Shore">预算 110 万，三房，北岸</button>
    <button data-zh="预算 90 万投资，看重租金回报" data-en="$900k to invest, want rental yield">预算 90 万投资，看重租金回报</button>
    <button data-zh="预算 150 万，要大院子，离市中心 20 公里内" data-en="$1.5m, big section, within 20 km of the city">预算 150 万，要大院子，离市中心 20 公里内</button>
    <button data-zh="Remuera 怎么样" data-en="What is Remuera like?">Remuera 怎么样</button>
    <button data-zh="Papakura 和 Manurewa 哪个好" data-en="Papakura or Manurewa?">Papakura 和 Manurewa 哪个好</button>
    <button data-zh="哪个区涨得最快" data-en="Which suburbs grew fastest?">哪个区涨得最快</button>
  </div>
  <div class="aifoot" id="aiFoot"></div>
  <form id="aiForm">
    <textarea id="aiInput" rows="1" data-zh-ph="例：预算 120 万，三房，上班在市中心" data-en-ph="e.g. $1.2m, 3 bedrooms, I work in the CBD"></textarea>
    <button id="aiSend" type="submit" data-zh="推荐" data-en="Find">推荐</button>
  </form>
  </div>
</div>

<script>
const DATA = /*__DATA__*/null;

const $ = s => document.querySelector(s);
const svg = $('#map'), tip = $('#tip');
const fmt = n => '$' + Math.round(n).toLocaleString('en-NZ');
const fmtK = n => n >= 1e6 ? '$' + (n/1e6).toFixed(2) + 'M' : '$' + Math.round(n/1000) + 'k';

/* ---------- language ----------
   Both strings sit at the call site rather than in a key table: a key table
   drifts the moment someone edits one language and not the other. */
const LANG_KEY = 'akl_lang';
function detectLang() {
  const saved = localStorage.getItem(LANG_KEY);
  if (saved === 'zh' || saved === 'en') return saved;
  // Honour the priority order. ["en-GB","en-NZ","zh-Hans-NZ"] is an English
  // speaker who also reads Chinese, not a Chinese speaker — matching "any zh
  // anywhere in the list" gets that backwards.
  const tags = (navigator.languages && navigator.languages.length)
    ? navigator.languages : [navigator.language || 'en'];
  for (const tag of tags) {
    if (/^zh\b/i.test(tag)) return 'zh';
    if (/^en\b/i.test(tag)) return 'en';
  }
  return 'en';
}
let LANG = detectLang();
const L = (zh, en) => (LANG === 'zh' ? zh : en);
const ZONE_L = {
  '北岸': 'North Shore', '西区': 'West', '中区': 'Central', '东区': 'East',
  '南区': 'South', '北部乡村': 'Rodney / rural north', '海岛': 'Gulf islands',
};
const zoneL = z => (LANG === 'zh' ? z : (ZONE_L[z] || z || ''));

function applyLang() {
  document.documentElement.lang = LANG === 'zh' ? 'zh-CN' : 'en';
  for (const el of document.querySelectorAll('[data-zh]'))
    el.textContent = el.dataset[LANG];
  for (const el of document.querySelectorAll('[data-zh-html]'))
    el.innerHTML = LANG === 'zh' ? el.dataset.zhHtml : el.dataset.enHtml;
  for (const el of document.querySelectorAll('[data-zh-ph]'))
    el.placeholder = LANG === 'zh' ? el.dataset.zhPh : el.dataset.enPh;
  for (const el of document.querySelectorAll('[data-zh-title]'))
    el.title = LANG === 'zh' ? el.dataset.zhTitle : el.dataset.enTitle;
  for (const el of document.querySelectorAll('[data-zh-aria]'))
    el.setAttribute('aria-label', LANG === 'zh' ? el.dataset.zhAria : el.dataset.enAria);
  document.querySelectorAll('[data-lang]').forEach(b =>
    b.setAttribute('aria-pressed', String(b.dataset.lang === LANG)));
}

function setLang(next) {
  // Persist first: clicking the language you are already on is still an
  // explicit choice, and it has to outrank auto-detection next visit.
  localStorage.setItem(LANG_KEY, next);
  if (next === LANG) return;
  LANG = next;
  applyLang();
  fillStats();          // the notes carry spans that applyLang just rebuilt
  tiles();
  redrawCalc();
  paint();              // redraws the legend caption
  if (!$('#tableWrap').hidden) drawTable();
  if (D) { drawDetailLegend(); sidePanel(D.s); enterDetailChrome(D.s); }
  resetAssistant();
}

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
    t.textContent = s.p ? `${s.n} — ${fmt(s.p)}` : `${s.n} — ${L('无数据', 'no data')}`;
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
    if (s.dt) rows.push([L('入门价（25% 分位）', 'entry price (25th pct)'), fmt(s.dt.q[1])]);
    rows.push([L('相对全区中位', 'vs regional median'), '×' + rel.toFixed(2)]);
    if (s.y != null) rows.push([L('过去一年', 'past year'), `<span class="${s.y >= 0 ? 'up' : 'down'}">${pct(s.y)}</span>`]);
    if (s.g != null) rows.push([L('长期年增长', 'long-term growth'), s.g.toFixed(1) + '%']);
    if (s.r) rows.push([L('周租金中位', 'median rent/wk'), '$' + s.r]);
    if (s.i) rows.push([L('估算租金回报', 'est. yield'), s.i.toFixed(1) + '%']);
    if (s.s) rows.push([L('中位售出天数', 'days to sell'), s.s + L(' 天', ' days')]);
    if (s.c) rows.push([L('近 12 月成交', 'sold, 12m'), s.c + L(' 套', '')]);
  }
  tip.innerHTML =
    `<div class="t">${s.n}</div>` +
    (s.p ? `<div class="big">${fmt(s.p)}</div>` : `<div class="big" style="font-size:14px;color:var(--muted)">${L('暂无价格数据', 'no price data')}</div>`) +
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
    ? L(`平均房产估值 — 中点 ${fmt(MID)}（全区郊区中位值），色阶两端为中位数的 ½ 与 2 倍，超出部分取端点色`,
        `Average house value — centred on ${fmt(MID)}, the median suburb. The ends are half and double that; beyond them the colour clamps.`)
    : L(`平均房产估值 — 按 ${sortedPrices.length} 个郊区的排名百分位展开（0% 最便宜 → 100% 最贵）`,
        `Average house value — spread across the rank of all ${sortedPrices.length} suburbs (0% cheapest → 100% dearest)`))
    + `<span class="nd"><span class="ndsw"></span>${L('无价格数据', 'no price data')}</span>`;
}

/* ---------- tiles ---------- */
function tiles() {
  const hi = priced[priced.length - 1], lo = priced[0];
  const items = [
    [L('全区郊区估值中位', 'Median suburb value'), fmt(MID), L(`${priced.length} 个郊区有数据`, `${priced.length} suburbs with data`)],
    [L('最贵', 'Dearest'), fmt(hi.p), hi.n],
    [L('最便宜', 'Cheapest'), fmt(lo.p), lo.n],
    [L('最贵 ÷ 最便宜', 'Dearest ÷ cheapest'), '×' + (hi.p / lo.p).toFixed(1), L('区内价差倍数', 'spread across the region')],
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
let SMOOTH = localStorage.getItem('akl_smooth') !== '0';
// Three box passes of radius 1 approximate a gaussian of sigma sqrt(w^2-1)/2
// = 1.41 cells, about 50 m. That is enough to lose the cell edges and no more:
// the data really is 35 m resolution, and smoothing past it would draw
// structure that was never measured. Radius 2 (~86 m) turned suburbs into ink
// blots and erased the street-level pattern the map exists to show.
const SMOOTH_RADIUS = 1;
const SMOOTH_PASSES = 3;

/* ---------- smooth field rendering ----------
   The grid is 35 m cells, which drawn as rects reads as mosaic. Smoothing has
   to happen on the VALUES, never on the pixels: this is a diverging ramp, so
   blending its blue and its red in RGB lands on the neutral grey that means
   "at the median" — a reading that exists nowhere in the data.

   Blur and hole-filling are one operation, a normalised convolution: box-blur
   (value x mask) and (mask) separately, then divide. Cells with no parcel
   contribute nothing instead of contributing zero, and small gaps close
   themselves with correctly weighted neighbours. */
function boxBlur1D(src, dst, n, stride, count, r) {
  for (let line = 0; line < count; line++) {
    const off = stride === 1 ? line * n : line;
    let sum = 0;
    for (let i = -r; i <= r; i++) sum += src[off + Math.min(n - 1, Math.max(0, i)) * stride];
    for (let i = 0; i < n; i++) {
      dst[off + i * stride] = sum / (2 * r + 1);
      const add = src[off + Math.min(n - 1, i + r + 1) * stride];
      const sub = src[off + Math.max(0, i - r) * stride];
      sum += add - sub;
    }
  }
}

function smoothField(dt, cells, radius, passes) {
  const nx = dt.nx, ny = dt.ny, n = nx * ny;
  const v = new Float32Array(n), m = new Float32Array(n);
  for (const c of cells) {
    const i = c.gy * nx + c.gx;
    v[i] = c.v;
    m[i] = 1;
  }
  const vt = new Float32Array(n), mt = new Float32Array(n);
  for (let p = 0; p < passes; p++) {
    boxBlur1D(v, vt, nx, 1, ny, radius);      // rows
    boxBlur1D(m, mt, nx, 1, ny, radius);
    boxBlur1D(vt, v, ny, nx, nx, radius);     // columns
    boxBlur1D(mt, m, ny, nx, nx, radius);
  }
  return { v, m, nx, ny };
}

function rampRGB() {
  const out = new Uint8Array(ramp.length * 3);
  for (let i = 0; i < ramp.length; i++) {
    const h = ramp[i];
    out[i * 3] = parseInt(h.slice(1, 3), 16);
    out[i * 3 + 1] = parseInt(h.slice(3, 5), 16);
    out[i * 3 + 2] = parseInt(h.slice(5, 7), 16);
  }
  return out;
}

// One RGBA image sampled per output pixel: bilinear on the value field, then
// coloured. Painting cell-by-cell and letting the browser smooth would be
// interpolating colour again — and it is this per-pixel resample that keeps
// the picture smooth at any zoom instead of magnifying a bitmap.
function fieldImage(field, dt, view, w, h, sc) {
  const img = new ImageData(w, h);
  const px = img.data, rgb = rampRGB(), last = ramp.length - 1;
  const LO = 0.05, HI = 0.22;                     // coverage feather band
  const { v, m, nx, ny } = field;
  const [vx, vy, vw, vh] = view;                  // view-unit box of the canvas
  const cs = dt.cs, bx = dt.bb[0], by = dt.bb[1];
  for (let y = 0; y < h; y++) {
    const worldY = vy + (y + 0.5) / h * vh;
    const gy = (worldY - by) / cs - 0.5;
    const y0 = Math.floor(gy), fy = gy - y0;
    for (let x = 0; x < w; x++) {
      const worldX = vx + (x + 0.5) / w * vw;
      const gx = (worldX - bx) / cs - 0.5;
      const x0 = Math.floor(gx), fx = gx - x0;
      if (x0 < -1 || y0 < -1 || x0 >= nx || y0 >= ny) continue;
      const cx0 = Math.max(0, Math.min(nx - 1, x0)), cx1 = Math.max(0, Math.min(nx - 1, x0 + 1));
      const cy0 = Math.max(0, Math.min(ny - 1, y0)), cy1 = Math.max(0, Math.min(ny - 1, y0 + 1));
      const i00 = cy0 * nx + cx0, i10 = cy0 * nx + cx1;
      const i01 = cy1 * nx + cx0, i11 = cy1 * nx + cx1;
      const wm = (m[i00] * (1 - fx) + m[i10] * fx) * (1 - fy)
               + (m[i01] * (1 - fx) + m[i11] * fx) * fy;
      if (wm < LO) continue;                      // genuinely no data nearby
      const wv = (v[i00] * (1 - fx) + v[i10] * fx) * (1 - fy)
               + (v[i01] * (1 - fx) + v[i11] * fx) * fy;
      // Interpolate along the ramp rather than snapping to one of its 101
      // entries: rounding put visible banding across every smooth gradient,
      // which reads as exactly the blockiness this is meant to remove.
      const g = sc.pos(wv / wm) * last;
      const k = Math.min(last - 1, Math.floor(g)), fk = g - k;
      const a = k * 3, b2 = a + 3;
      const o = (y * w + x) * 4;
      px[o] = rgb[a] + (rgb[b2] - rgb[a]) * fk;
      px[o + 1] = rgb[a + 1] + (rgb[b2 + 1] - rgb[a + 1]) * fk;
      px[o + 2] = rgb[a + 2] + (rgb[b2 + 2] - rgb[a + 2]) * fk;
      // Feather where the data thins out, so the edge of coverage is not a
      // hard cut either.
      px[o + 3] = wm >= HI ? 255 : Math.round(255 * (wm - LO) / (HI - LO));
    }
  }
  return img;
}

function fitView(rect) {
  const [bx, by, bw, bh] = D.s.bx, pad = 8;
  const k = Math.min((rect.width - pad * 2) / bw, (rect.height - pad * 2) / bh);
  return { k, min: k, cx: bx + bw / 2, cy: by + bh / 2 };
}

function drawDetailMap(quick) {
  if (!D || !D.dt) return;
  const cv = $('#dmap'), rect = cv.getBoundingClientRect();
  if (!rect.width) return;
  if (!D.view || D.view.w !== Math.round(rect.width)) {
    D.view = { ...fitView(rect), w: Math.round(rect.width) };
  }
  const dpr = Math.min(2, devicePixelRatio || 1);
  cv.width = Math.round(rect.width * dpr);
  cv.height = Math.round(rect.height * dpr);
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);

  const { k, cx, cy } = D.view;
  const vx = cx - rect.width / (2 * k);       // view-unit coords of the top-left
  const vy = cy - rect.height / (2 * k);
  Object.assign(D, { scale: k, vx, vy });

  const world = () => {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.translate(-vx * k, -vy * k);
    ctx.scale(k, k);
  };

  const shape = new Path2D(D.s.d);
  ctx.save();
  world();
  ctx.fillStyle = cssVar('--nodata');
  ctx.fill(shape, 'evenodd');
  ctx.restore();

  // Clip to the suburb: a 35 m cell whose centre sits just outside the boundary,
  // and the smoothing halo, would otherwise bleed past the coastline.
  ctx.save();
  world();
  ctx.clip(shape, 'evenodd');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  if (SMOOTH) {
    // Half resolution while the pointer is moving, full when it settles: the
    // per-pixel resample is what makes this stay smooth at any zoom, and it is
    // also the only expensive part.
    const q = quick ? 0.5 : 1;
    const iw = Math.max(1, Math.round(rect.width * q));
    const ih = Math.max(1, Math.round(rect.height * q));
    const view = [vx, vy, rect.width / k, rect.height / k];
    const img = fieldImage(D.field, D.dt, view, iw, ih, D.sc);
    const off = document.createElement('canvas');
    off.width = iw; off.height = ih;
    off.getContext('2d').putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(off, 0, 0, rect.width, rect.height);
  } else {
    world();
    const [gx0, gy0] = D.dt.bb, cs = D.dt.cs;
    for (const c of D.cells) {
      ctx.fillStyle = D.sc.color(c.v);
      ctx.fillRect(gx0 + c.gx * cs, gy0 + c.gy * cs, cs * 1.02, cs * 1.02);
    }
  }
  ctx.restore();

  ctx.save();
  world();
  ctx.lineWidth = 1.4 / k;
  ctx.strokeStyle = cssVar('--ink-2');
  ctx.stroke(shape);
  ctx.restore();
}

/* ---------- detail zoom & pan ---------- */
let dRedraw = 0;
function redrawDetail(quick) {
  if (dRedraw) return;
  dRedraw = requestAnimationFrame(() => { dRedraw = 0; drawDetailMap(quick); });
}
let settle = 0;
function settleDetail() {
  clearTimeout(settle);
  settle = setTimeout(() => drawDetailMap(false), 140);   // full-res pass
}

function zoomDetailAt(clientX, clientY, factor) {
  if (!D || !D.view) return;
  const cv = $('#dmap'), r = cv.getBoundingClientRect();
  const k0 = D.view.k;
  // Cap zoom where one 35 m cell fills ~40 screen px. Past that you are
  // magnifying air: the data has no more detail to give, and a smooth blur
  // blown up further just looks like precision that was never measured.
  const maxK = Math.max(D.view.min * 2, 40 / D.dt.cs);
  const k = Math.max(D.view.min, Math.min(maxK, k0 * factor));
  if (k === k0) return;
  // keep whatever is under the pointer pinned there
  const wx = D.vx + (clientX - r.left) / k0;
  const wy = D.vy + (clientY - r.top) / k0;
  D.view.cx = wx + (r.width / 2 - (clientX - r.left)) / k;
  D.view.cy = wy + (r.height / 2 - (clientY - r.top)) / k;
  D.view.k = k;
  clampDetail(r);
  redrawDetail(true);
  settleDetail();
}

// Keep the suburb from being dragged off screen entirely.
function clampDetail(r) {
  const [bx, by, bw, bh] = D.s.bx, k = D.view.k;
  const halfW = r.width / (2 * k), halfH = r.height / (2 * k);
  D.view.cx = Math.max(bx - halfW * 0.6, Math.min(bx + bw + halfW * 0.6, D.view.cx));
  D.view.cy = Math.max(by - halfH * 0.6, Math.min(by + bh + halfH * 0.6, D.view.cy));
}

{
  const cv = $('#dmap');
  cv.addEventListener('wheel', e => {
    if (!D || !D.dt) return;
    e.preventDefault();
    zoomDetailAt(e.clientX, e.clientY, Math.exp(-e.deltaY * 0.0016));
  }, { passive: false });

  const pts = new Map();
  let pan = null, pinch = null;
  cv.addEventListener('pointerdown', e => {
    if (!D || !D.dt) return;
    cv.setPointerCapture(e.pointerId);
    pts.set(e.pointerId, e);
    if (pts.size === 1) {
      pan = { x: e.clientX, y: e.clientY, cx: D.view.cx, cy: D.view.cy };
      cv.classList.add('dragging');
    } else if (pts.size === 2) {
      const [a, b] = [...pts.values()];
      pinch = { d: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) };
      pan = null;
    }
  });
  cv.addEventListener('pointermove', e => {
    if (!D || !D.dt || !pts.has(e.pointerId)) return;
    pts.set(e.pointerId, e);
    if (pinch && pts.size === 2) {
      const [a, b] = [...pts.values()];
      const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      if (pinch.d > 0) zoomDetailAt((a.clientX + b.clientX) / 2,
                                    (a.clientY + b.clientY) / 2, d / pinch.d);
      pinch.d = d;
    } else if (pan) {
      const r = cv.getBoundingClientRect();
      D.view.cx = pan.cx - (e.clientX - pan.x) / D.view.k;
      D.view.cy = pan.cy - (e.clientY - pan.y) / D.view.k;
      clampDetail(r);
      redrawDetail(true);
      settleDetail();
    }
  });
  const release = e => {
    pts.delete(e.pointerId);
    if (pts.size < 2) pinch = null;
    if (pts.size === 0) { pan = null; cv.classList.remove('dragging'); }
  };
  cv.addEventListener('pointerup', release);
  cv.addEventListener('pointercancel', release);
  cv.addEventListener('dblclick', () => {
    if (!D || !D.dt) return;
    D.view = { ...fitView(cv.getBoundingClientRect()), w: D.view.w };
    drawDetailMap(false);
  });
}

function cellAt(clientX, clientY) {
  if (!D || !D.dt || D.vx === undefined) return null;
  const r = $('#dmap').getBoundingClientRect();
  const wx = D.vx + (clientX - r.left) / D.scale;
  const wy = D.vy + (clientY - r.top) / D.scale;
  const gx = Math.floor((wx - D.dt.bb[0]) / D.dt.cs);
  const gy = Math.floor((wy - D.dt.bb[1]) / D.dt.cs);
  return D.lookup.get(gy * 256 + gx) || null;
}

$('#dmap').addEventListener('pointermove', e => {
  if (!D || !D.dt) return;
  const c = cellAt(e.clientX, e.clientY);
  const tip = $('#dtip'), cur = $('#dLcursor');
  if (!c) { tip.style.opacity = 0; cur.style.opacity = 0; return; }
  tip.innerHTML = `<div class="big">${fmt(c.v)}</div>` +
    `<div class="sm">${L('该网格 CV 中位', 'median CV in this cell')} · ×${(c.v / D.dt.med).toFixed(2)} ${L('区内中位', 'of suburb median')}</div>`;
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
  const [y0, vals] = h, W = 320, H = 108, PAD = 6, R = 6, T = 8, B = 16;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const sx = i => PAD + i / (vals.length - 1) * (W - PAD - R);
  const sy = v => T + (1 - (v - lo) / Math.max(1, hi - lo)) * (H - T - B);
  const pts = vals.map((v, i) => `${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join(' ');
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" height="108">
    <polygon class="area" points="${sx(0)},${H - B} ${pts} ${sx(vals.length - 1)},${H - B}"/>
    <polyline class="line" points="${pts}"/>
    <text x="${PAD}" y="${H - 4}">${y0}</text>
    <text x="${W - R}" y="${H - 4}" text-anchor="end">${y0 + vals.length - 1}</text>
    <text x="${PAD}" y="${T + 4}">${LANG === 'zh' ? '峰值' : 'peak'} ${fmtK(hi * 1000)}</text>
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
      `fill="${sc.color(mid)}"><title>${fmtK(mid)} · ${c}${LANG === 'zh' ? ' 套' : ''}</title></rect>`;
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
  if (s.p) hero.push(`<div><div class="k">${L('平均房产估值', 'Average house value')}</div><div class="v">${fmt(s.p)}</div>
    <div class="m">×${(s.p / MID).toFixed(2)} ${L('全区中位', 'of regional median')}${s.y == null ? '' :
      ` · <span class="${s.y >= 0 ? 'up' : 'down'}">${pct(s.y)}</span> ${L('近一年', 'past year')}`}</div></div>`);
  if (dt) hero.push(`<div><div class="k">${L('政府估价 CV 中位', 'Median council CV')}</div><div class="v">${fmt(dt.med)}</div>
    <div class="m">${dt.n.toLocaleString('en-NZ')} ${L('个计税单元', 'rating units')}${dt.chg == null ? '' :
      ` · <span class="${dt.chg >= 0 ? 'up' : 'down'}">${pct(dt.chg * 100)}</span> vs ${DATA.prevValuationDate.slice(0, 4)}`}</div></div>`);
  if (hero.length) out.push(`<div class="card dhero">${hero.join('')}</div>`);

  if (s.w) out.push(`<div class="card"><h3>${L('简介（英文）', 'About')}</h3><p class="dintro">${s.w.extract}
    <a href="${s.w.url}" target="_blank" rel="noopener">Wikipedia ↗</a></p></div>`);

  const stats = [
    row(L('人口', 'Population'), s.o ? s.o.toLocaleString('en-NZ') : null),
    row(L('租房人口占比', 'Renters'), s.rp == null ? null : s.rp.toFixed(1) + '%'),
    row(L('周租金中位', 'Median rent/wk'), s.r ? '$' + s.r : null),
    row(L('估算租金回报', 'Est. gross yield'), s.i == null ? null : s.i.toFixed(1) + '%'),
    row(L('长期年化增长', 'Long-term growth'), s.g == null ? null : s.g.toFixed(1) + '%'),
    row(L('中位售出天数', 'Median days to sell'), s.s ? s.s + L(' 天', ' days') : null),
    row(L('近 12 月成交', 'Sold, last 12m'), s.c ? s.c + L(' 套', '') : null),
    row(L('上月挂牌', 'Listed last month'), s.lf ? s.lf + L(' 套', '') : null),
    row(L('中位出租天数', 'Median days to rent'), s.dr ? s.dr + L(' 天', ' days') : null),
    dt ? row(L('CV 四分位区间', 'CV interquartile range'), `${fmtK(dt.q[1])} – ${fmtK(dt.q[3])}`) : '',
  ].join('');
  if (stats) out.push(`<div class="card"><h3>${L('市场概况', 'Market')}</h3><div class="dstats">${stats}</div></div>`);

  // Seeded from this suburb's entry price; anything the reader has already
  // typed wins over the seed. Skipped where there is nothing to seed from —
  // a water catchment with no rating units and no price gets the "there is
  // nothing here" note below instead, which pushing a card would suppress.
  if (dt || s.p) {
    seedCalc(s);
    out.push(calcCard());
  }

  if (s.bm) {
    const labels = LANG === 'zh' ? ['1 房', '2 房', '3 房', '4 房', '5+ 房']
                                  : ['1 bed', '2 bed', '3 bed', '4 bed', '5+ bed'];
    const bars = s.bm.map((v, i) => v ?
      `<i style="flex:${v};background:${BEDC[i]}" title="${labels[i]} ${v}%">${v >= 12 ? v + '%' : ''}</i>` : '').join('');
    const key = s.bm.map((v, i) => v ?
      `<span><i style="background:${BEDC[i]}"></i><b>${labels[i]}</b> ${v}%${
        s.br && s.br[i] ? ` · $${s.br[i]}${L('/周', '/wk')}` : ''}</span>` : '').join('');
    out.push(`<div class="card"><h3>${L('户型结构（附该户型周租金）', 'Bedroom mix (with weekly rent)')}</h3><div class="beds">${bars}</div>
      <div class="bedkey">${key}</div></div>`);
  }

  if (s.h) out.push(`<div class="card"><h3>${L('房价走势', 'Value trend')} ${s.h[0]}–${s.h[0] + s.h[1].length - 1}</h3>${lineChart(s.h)}</div>`);
  if (dt) out.push(`<div class="card"><h3>${L('区内 CV 分布（虚线 = 中位）', 'CV distribution (dashed = median)')}</h3>${histChart(dt, D.sc)}</div>`);
  if (!out.length) out.push(`<div class="card"><p class="dintro">${L('该地区没有任何计税单元与市场数据 —— 通常是集水区、林地或保护区。', 'No rating units and no market data here — usually a water catchment, forest or reserve.')}</p></div>`);

  $('#dSide').innerHTML = out.join('');
  renderCalcAll();
}

function drawDetailLegend() {
  $('#dLbar').style.background = `linear-gradient(to right, ${ramp.join(',')})`;
  $('#dLticks').innerHTML = [0, .25, .5, .75, 1].map((t, i) => {
    const v = D.sc.at(t);
    const lead = i === 0 ? '≤' : i === 4 ? '≥' : '';
    return `<span>${lead}${fmtK(v)}<br><em>×${(v / D.sc.med).toFixed(2)}</em></span>`;
  }).join('');
  $('#dLegendCap').textContent =
    L(`政府估价 CV（${DATA.valuationDate} 估值）— 中点是该区中位 ${fmt(D.sc.med)}，两端为区内 10 / 90 分位。`
      + (SMOOTH ? `画面由 35 米网格平滑而来（约 50 米），实际分辨率仍是 35 米。` : `按 35 米原始网格显示。`),
      `Council CV (valued ${DATA.valuationDate}) — centred on this suburb's median ${fmt(D.sc.med)}; the ends are its 10th and 90th percentiles. `
      + (SMOOTH ? `Smoothed (~50 m) from the underlying 35 m grid, which is still the real resolution.` : `Shown at the raw 35 m grid.`));
}

/* ---------- enter / leave ---------- */
const HIDE = ['#tiles', '.bar', '.stage', '.legend', '#calcMain', '#tableWrap'];

function enterDetail(name, push = true) {
  const s = byName.get(name);
  if (!s) return false;
  const dt = s.dt || null;
  D = { s, dt };
  if (dt) {
    D.cells = decodeCells(dt.cells);
    D.sc = localScale(dt);
    D.lookup = new Map(D.cells.map(c => [c.gy * 256 + c.gx, c]));
    D.field = smoothField(dt, D.cells, SMOOTH_RADIUS, SMOOTH_PASSES);
  }

  $('#dName').textContent = name;
  $('#dKind').textContent = [zoneL(s.z), L(s.t === 'Suburb' ? '郊区' : '地区',
                              s.t === 'Suburb' ? 'suburb' : 'locality')].filter(Boolean).join(' · ');
  // Catchments and reserves hold no rating units, so there is no grid to draw.
  $('#dGeo').hidden = !dt;
  if (dt) {
    $('#dKind').textContent += L(` · 每格约 ${Math.round(dt.cs * DATA.metresPerUnit)} 米`,
                                 ` · ~${Math.round(dt.cs * DATA.metresPerUnit)} m per cell`);
    $('#dHint').textContent = L('滚轮缩放 · 拖拽平移 · 双击复位 · 悬停看该网格 CV 中位数',
                                'Scroll to zoom · drag to pan · double-click to reset · hover for a cell\u2019s median CV');
    // let the canvas take the suburb's own shape rather than letterboxing it
    $('#dmap').style.aspectRatio = Math.max(0.72, Math.min(2, s.bx[2] / s.bx[3])).toFixed(3);
  }
  HIDE.forEach(sel => { const el = document.querySelector(sel); if (el) el.style.display = 'none'; });
  $('#detail').hidden = false;
  $('#smOn').setAttribute('aria-pressed', String(SMOOTH));
  $('#smOff').setAttribute('aria-pressed', String(!SMOOTH));
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


/* ==========================================================================
   房贷与地税试算
   Two sums that share one question: what does holding this place cost. The
   mortgage half is ordinary amortisation; the rates half is a model of the
   council's own bill. Both print the date their inputs were read — a
   repayment computed off a rate that moved in June still looks exactly like
   a repayment, which is why the stale case has to announce itself.
   ========================================================================== */
const FIN = DATA.fin;

// State lives outside the DOM. sidePanel() is re-rendered on a language switch
// and again on a theme change, and losing half-typed numbers to a colour
// change is the sort of thing that makes a tool feel broken. `touched` stops a
// suburb's seed values from overwriting figures someone entered by hand.
const CALC = {
  price: null, cv: null, dep: 20, years: 30, rate: FIN.m.default,
  freq: 12, io: false, rural: false, touched: { price: false, cv: false },
};

const PER_L = { 12: ['每月', 'a month'], 26: ['每两周', 'a fortnight'], 52: ['每周', 'a week'] };
const perL = f => L(PER_L[f][0], PER_L[f][1]);
// Always two decimals: a rate typed as 6 is the same rate as 6.00, but "6%"
// next to "4.65%" reads like a different kind of number.
const pctL = v => (Number.isFinite(v) ? v : 0).toFixed(2) + '%';

/* Ordinary table mortgage. NZ banks accrue interest daily but quote the
   repayment off the nominal periodic rate, which is what every bank's own
   calculator shows — matching that matters more here than being marginally
   more correct than the number people will check this against. */
function repayment(principal, annualPct, years, periods, interestOnly) {
  const i = annualPct / 100 / periods;
  const n = Math.round(years * periods);
  if (!(principal > 0) || n <= 0 || !Number.isFinite(i)) return 0;
  if (interestOnly) return principal * i;
  if (i === 0) return principal / n;
  return principal * i / (1 - Math.pow(1 + i, -n));
}

/* The council's bill, component by component. General and the three
   environment targeted rates are charged on capital value; the UAGC and the
   waste charges are fixed per rating unit, which is why a cheap house pays a
   much larger share of its rates as flat fees. */
function councilRates(cv, rural) {
  const c = FIN.c, v = Math.max(0, cv || 0);
  const general = v * (rural ? c.generalRural : c.general);
  const env = v * c.env;
  return { general, env, uagc: c.uagc, waste: c.waste,
           total: general + env + c.uagc + c.waste };
}

const rateAgeDays = () => Math.floor(
  (Date.now() - Date.parse(FIN.m.asAt + 'T00:00:00Z')) / 86400000);

// A suburb seeds the calculator from its own numbers: the entry price (the
// 25th percentile) rather than the average, for the same reason the
// recommendation cards lead with it.
//
// CV seeds to the same figure rather than to the suburb's median CV, and the
// distinction matters. Entry price *is* a council valuation — the 25th
// percentile of the same distribution the median comes from — so an entry
// level house has an entry level CV, not the suburb's middle one. Seeding the
// median against the entry price paired two different houses and then made
// the rates note explain the gap as if the reader had overpaid by $460k.
// The gap the note is for is the real one: a purchase price above or below
// the council's valuation of that same house.
function seedCalc(s) {
  const dt = s && s.dt;
  if (!CALC.touched.price) CALC.price = (dt && dt.q[1]) || (s && s.p) || MID;
  if (!CALC.touched.cv) CALC.cv = CALC.price;
}

function calcCard() {
  const m = FIN.m;
  const termL = { '6m': ['6 个月', '6 months'], '1y': ['1 年', '1 year'],
                  '18m': ['18 个月', '18 months'],
                  '2y': ['2 年', '2 years'], '3y': ['3 年', '3 years'],
                  '4y': ['4 年', '4 years'], '5y': ['5 年', '5 years'] };
  const chip = (lab, v, banks) => `<button type="button" data-rate="${v}" aria-pressed="${
    Math.abs(CALC.rate - v) < 1e-9}" title="${L(`${(banks || []).join('、')} 的挂牌利率`,
      `carded by ${(banks || []).join(', ')}`)}">${lab} · ${v.toFixed(2)}%</button>`;
  const opt = (v, cur, lab) => `<option value="${v}"${v === cur ? ' selected' : ''}>${lab}</option>`;
  return `<div class="card calc">
    <h3>${L('房贷与地税试算', 'Mortgage and council rates')}</h3>
    <div class="calcin">
      <div class="fld"><label>${L('买价（NZD）', 'Purchase price (NZD)')}</label>
        <input type="number" data-cf="price" min="0" step="10000" value="${Math.round(CALC.price)}"></div>
      <div class="fld"><label>${L('首付比例', 'Deposit')}</label>
        <div class="unit"><input type="number" data-cf="dep" min="0" max="100" step="1" value="${CALC.dep}"><i>%</i></div></div>
      <div class="fld"><label>${L('贷款年限', 'Loan term')}</label>
        <div class="unit"><input type="number" data-cf="years" min="1" max="40" step="1" value="${CALC.years}"><i>${L('年', 'yr')}</i></div></div>
      <div class="fld"><label>${L('年利率', 'Interest rate')}</label>
        <div class="unit"><input type="number" data-cf="rate" min="0" max="20" step="0.01" value="${CALC.rate}"><i>%</i></div></div>
      <div class="ratechips">
        ${m.terms.map(([t, v, banks]) => chip(L(termL[t][0], termL[t][1]), v, banks)).join('')}
        ${m.floating ? chip(L('浮动', 'Floating'), m.floating, m.floatingBanks) : ''}
      </div>
      <div class="fld"><label>${L('还款频率', 'Repayment frequency')}</label>
        <select data-cf="freq">${[12, 26, 52].map(f =>
          opt(String(f), String(CALC.freq), L(PER_L[f][0], { 12: 'Monthly', 26: 'Fortnightly', 52: 'Weekly' }[f]))).join('')}</select></div>
      <div class="fld"><label>${L('还款方式', 'Repayment type')}</label>
        <select data-cf="mode">${opt('pi', CALC.io ? 'io' : 'pi', L('本息同还', 'Principal and interest'))}${
          opt('io', CALC.io ? 'io' : 'pi', L('只还利息', 'Interest only'))}</select></div>
      <div class="fld"><label>${L('政府估价 CV（算地税用）', 'Council CV (rates are charged on this)')}</label>
        <input type="number" data-cf="cv" min="0" step="10000" value="${Math.round(CALC.cv)}"></div>
      <div class="fld"><label>${L('地税差别税率', 'Rating differential')}</label>
        <select data-cf="diff">${opt('urban', CALC.rural ? 'rural' : 'urban', L('住宅 · 城区', 'Residential urban'))}${
          opt('rural', CALC.rural ? 'rural' : 'urban', L('住宅 · 乡村', 'Residential rural'))}</select></div>
    </div>
    <div class="calcout"></div>
  </div>`;
}

function renderCalcOut() {
  const price = Math.max(0, CALC.price || 0);
  const dep = Math.min(100, Math.max(0, CALC.dep || 0));
  const deposit = price * dep / 100;
  const loan = Math.max(0, price - deposit);
  const f = CALC.freq;
  const pay = repayment(loan, CALC.rate, CALC.years, f, CALC.io);
  const n = Math.round(CALC.years * f);
  const paid = CALC.io ? pay * n + loan : pay * n;
  const stress = repayment(loan, (CALC.rate || 0) + 2, CALC.years, f, CALC.io);
  const r = councilRates(CALC.cv, CALC.rural);
  const perYear = pay * f, ratesPer = r.total / f;

  const row = (k, v, cls = '') => `<div class="${cls}"><span>${k}</span><span>${v}</span></div>`;
  const c = FIN.c;
  const anchor = councilRates(c.avgCv, false);

  const flags = [];
  if (dep < 20 && price > 0) flags.push(`<div class="calcflag">${L(
    `首付 ${dep}%（贷款价值比 ${((loan / price) * 100).toFixed(0)}%）。低于 20% 时多数银行要额外的低首付利率加点，通常 0.25–1.5 个百分点，这里没有算进去 —— 加点多少各行不同，编一个数字不如说明白它存在。`,
    `A ${dep}% deposit is an LVR of ${((loan / price) * 100).toFixed(0)}%. Under 20%, most banks add a low-equity margin — usually 0.25–1.5 percentage points — which is not included above, because the size of it varies by bank and inventing a figure would be worse than naming the gap.`)}</div>`);
  const age = rateAgeDays();
  if (age > 60) flags.push(`<div class="calcflag bad">${L(
    `利率是 ${FIN.m.asAt} 读取的，距今 ${age} 天。请自行核对当前挂牌利率再用这个数字。`,
    `These rates were read on ${FIN.m.asAt}, ${age} days ago. Check the current carded rates before relying on this figure.`)}</div>`);
  if (CALC.cv > 0 && price > 0 && Math.abs(CALC.cv - price) / price > 0.15)
    flags.push(`<div class="calcflag">${L(
      `地税是按政府估价 CV ${fmt(CALC.cv)} 算的，不是买价 ${fmt(price)}。买贵了不会立刻涨地税 —— CV 要等下一轮全区重估（约 2027 年）才会变。`,
      `Rates are charged on the council valuation of ${fmt(CALC.cv)}, not the ${fmt(price)} you pay. Paying above CV does not raise your rates bill — the CV only moves at the next region-wide revaluation, due around 2027.`)}</div>`);

  return `
    <div class="calcbig">
      <span class="v">${fmt(pay)}</span>
      <span class="k">${L(`${perL(f)}还款${CALC.io ? '（只还利息）' : ''}`,
                          `${perL(f)}${CALC.io ? ' · interest only' : ''}`)} ·
        ${pctL(CALC.rate)} · ${CALC.years}${L(' 年', 'yr')}</span>
    </div>
    <div class="calcrows">
      ${row(L('首付', 'Deposit'), fmt(deposit))}
      ${row(L('贷款额', 'Loan'), fmt(loan))}
      ${row(L('利率 +2% 时', 'If the rate rose 2%'), `${fmt(stress)} (+${fmt(stress - pay)})`)}
      ${row(L(CALC.io ? '每年利息' : '每年还款', CALC.io ? 'Interest per year' : 'Repayments per year'), fmt(perYear))}
      ${row(L(CALC.io ? '期末仍欠本金' : '利息总额', CALC.io ? 'Principal still owing at the end' : 'Total interest'),
            fmt(CALC.io ? loan : paid - loan))}
      ${row(L('还款总额', 'Total paid'), fmt(paid))}
      ${row(L(`地税估算（${FIN.c.year}）`, `Council rates (${FIN.c.year})`), `${fmt(r.total)}${L('/年', '/yr')}`, 'full')}
    </div>
    <div class="calctot">
      <span class="v">${fmt(pay + ratesPer)}</span>
      <span class="k">${L(`${perL(f)}持有成本 = 房贷 <b>${fmt(pay)}</b> ＋ 地税 <b>${fmt(ratesPer)}</b>`,
                          `${perL(f)} to hold = mortgage <b>${fmt(pay)}</b> + rates <b>${fmt(ratesPer)}</b>`)}</span>
    </div>
    ${flags.join('')}
    <details class="calcbreak"><summary>${L('地税是怎么算出来的', 'How the rates figure is built')}</summary>
      <div class="calcrows">
        ${row(L(`一般地税 · CV × ${(c.general * 100).toFixed(3)}%`, `General rate · CV × ${(c.general * 100).toFixed(3)}%`), fmt(r.general))}
        ${row(L(`环境类目标税 · CV × ${(c.env * 100).toFixed(3)}%`, `Environment targeted rates · CV × ${(c.env * 100).toFixed(3)}%`), fmt(r.env))}
        ${row(L('统一年度费 UAGC（固定）', 'Uniform annual general charge (fixed)'), fmt(r.uagc))}
        ${row(L('垃圾收运（固定）', 'Waste collection (fixed)'), fmt(r.waste))}
        ${row(L('合计', 'Total'), fmt(r.total), 'full')}
      </div>
      <p class="calcnote">${L(
        `议会公布的是平均账单，不是税率明细，所以上面这四项是按它逐项公布的涨跌反推、再钉在它唯一说死的那个数上：均价住宅 CV ${fmt(c.avgCv)} 今年缴 ${fmt(c.avgTotal)}。本模型在这个 CV 上给 ${fmt(anchor.total)} —— 锚点上是准的，离开锚点是估算。环境类三项（水质、自然环境、气候行动）按 CV 计所以随房价缩放；UAGC 和垃圾费是固定的，所以越便宜的房子，地税里固定费用占比越高。`,
        `The council publishes the average bill rather than the schedule of rates, so these four lines are reconstructed from the year-on-year movements it does publish and pinned to the one total it states outright: the average residential property at CV ${fmt(c.avgCv)} pays ${fmt(c.avgTotal)} this year. This model returns ${fmt(anchor.total)} at that CV — exact at the anchor, an estimate away from it. The three environment rates are charged on CV and so scale with it; the UAGC and waste charges are flat, which is why a cheaper house pays a larger share of its rates as fixed fees.`)}</p>
    </details>
    <p class="calcnote">${L(
      `估算，不是报价，也不构成任何理财建议。利率是 ${FIN.m.banks.join(' / ')} 五大行挂牌利率中<b>每个期限的最低值</b>（${FIN.m.asAt} 读取，<a href="${FIN.m.src}" target="_blank" rel="noopener">来源 ↗</a>），把鼠标放在利率按钮上能看到是哪家给的。<b>这不是你能拿到的利率</b> —— 实际利率取决于银行、首付比例和收入，低于 20% 首付通常拿不到挂牌的特惠价。<b>水费和污水费由 Watercare 另行收取</b>，不在地税里，也不在上面这个数里；保险、维护、body corp 同样没算。以自己的房子为准请查<a href="https://www.aucklandcouncil.govt.nz/property-rates-valuations" target="_blank" rel="noopener">议会的地税查询 ↗</a>。`,
      `An estimate, not a quote, and not financial advice. The rates offered are the <b>lowest carded rate at each term</b> across ${FIN.m.banks.join(', ')} (read ${FIN.m.asAt}, <a href="${FIN.m.src}" target="_blank" rel="noopener">source ↗</a>); hover a rate button to see which bank is quoting it. <b>This is not the rate you will be offered</b> — that depends on the bank, your deposit and your income, and a deposit under 20% usually does not qualify for the carded special at all. <b>Water and wastewater are billed separately by Watercare</b> — they are not part of council rates and are not in the figure above, and neither are insurance, maintenance or body corporate levies. For a specific property, look it up on <a href="https://www.aucklandcouncil.govt.nz/property-rates-valuations" target="_blank" rel="noopener">the council's own rates search ↗</a>.`)}</p>`;
}

function renderCalcAll() {
  document.querySelectorAll('.calcout').forEach(el => { el.innerHTML = renderCalcOut(); });
  const sum = $('#calcSummary');
  if (sum) {
    const r = councilRates(CALC.cv, CALC.rural);
    const pay = repayment(Math.max(0, (CALC.price || 0) * (1 - CALC.dep / 100)),
                          CALC.rate, CALC.years, CALC.freq, CALC.io);
    sum.innerHTML = L(
      `<b>房贷与地税试算</b> — ${fmt(CALC.price)} 的房子，首付 ${CALC.dep}%、${pctL(CALC.rate)}，${perL(CALC.freq)}还 <b>${fmt(pay)}</b>，地税约 ${fmt(r.total)}/年`,
      `<b>Mortgage and rates</b> — a ${fmt(CALC.price)} home at ${CALC.dep}% down and ${pctL(CALC.rate)} costs <b>${fmt(pay)}</b> ${perL(CALC.freq)}, plus about ${fmt(r.total)}/yr in rates`);
  }
}

// Inputs are rendered once and left alone; only the output half redraws on
// every keystroke, so the caret never jumps out of the field being typed in.
function setCalc(k, raw) {
  const num = v => (Number.isFinite(v) ? v : 0);
  if (k === 'price') {
    CALC.price = num(raw); CALC.touched.price = true;
    if (!CALC.touched.cv) syncField('cv', Math.round(CALC.cv = CALC.price));
  } else if (k === 'cv') { CALC.cv = num(raw); CALC.touched.cv = true; }
  else if (k === 'freq') CALC.freq = +raw;
  else if (k === 'mode') CALC.io = raw === 'io';
  else if (k === 'diff') CALC.rural = raw === 'rural';
  else CALC[k] = num(raw);
  renderCalcAll();
}

// The page can hold two copies of the card (the region one and the suburb
// one), so a value set in either has to land in both.
function syncField(k, v) {
  document.querySelectorAll(`[data-cf="${k}"]`).forEach(el => {
    if (el !== document.activeElement) el.value = v;
  });
}

const calcHandler = e => {
  const f = e.target.closest('[data-cf]');
  if (f) setCalc(f.dataset.cf, f.tagName === 'SELECT' ? f.value : parseFloat(f.value));
};
document.addEventListener('input', calcHandler);
document.addEventListener('change', calcHandler);
document.addEventListener('click', e => {
  const b = e.target.closest('.ratechips button');
  if (!b) return;
  CALC.rate = parseFloat(b.dataset.rate);
  document.querySelectorAll('[data-cf="rate"]').forEach(el => { el.value = CALC.rate; });
  document.querySelectorAll('.ratechips button').forEach(x =>
    x.setAttribute('aria-pressed', String(x.dataset.rate === b.dataset.rate)));
  renderCalcAll();
});

// Redraw the region copy of the card. Called on boot and on a language
// switch; it deliberately does not re-seed, so switching language mid-sum
// keeps the numbers on screen.
function redrawCalc() {
  $('#calcMainSlot').innerHTML = calcCard();
  renderCalcAll();
}

function mountCalc() {
  seedCalc(null);
  redrawCalc();
}

// The panel sits under the map and the legend, which on a 720px viewport puts
// it 1.4 screens down — far enough that the first person to look for it asked
// where it was. The map is the point of the page and should not be pushed down
// for this, so the toolbar gets a way in instead. Kept in sync both ways: the
// details element can also be opened by clicking it directly.
const calcPanel = () => $('#calcMain');
$('#toggleCalc').addEventListener('click', () => {
  const d = calcPanel();
  d.open = !d.open;
  if (d.open) d.scrollIntoView({ behavior: 'smooth', block: 'start' });
});
calcPanel().addEventListener('toggle', () =>
  $('#toggleCalc').setAttribute('aria-pressed', String(calcPanel().open)));

/* ==========================================================================
   选房助手
   Budget is a hard gate, not a weight. Every claim a recommendation makes is
   computed from the payload — the optional LLM only reads the request and
   writes the intro sentence; it never picks suburbs and never states a number.
   ========================================================================== */
const AI = { busy: false };

/* ---------- budget: share of a suburb's stock within budget ---------- */
// The detail payload carries a 24-bin log-spaced histogram of council capital
// values per suburb, so "what fraction of this suburb costs at most B" is a
// CDF lookup rather than a guess off the median.
function affordShare(s, budget) {
  const dt = s.dt;
  if (!dt || !dt.hist || !budget) return null;
  const { hist, histLo: lo, histHi: hi, n } = dt;
  if (budget <= lo) return hist[0] / n * Math.max(0, budget / lo);
  const span = Math.log(hi / lo), bins = hist.length;
  const pos = Math.log(budget / lo) / span * bins;
  if (pos >= bins) return 1;
  const whole = Math.floor(pos);
  let cum = 0;
  for (let i = 0; i < whole; i++) cum += hist[i];
  cum += hist[whole] * (pos - whole);
  return Math.min(1, cum / n);
}

// Enough choice to be worth recommending, and not so much that the budget is
// being wasted on an area far below it.
function budgetScore(a) {
  if (a === null) return 0.4;
  if (a < 0.20) return 0;
  if (a <= 0.70) return 0.55 + 0.45 * (a - 0.20) / 0.50;
  return 1 - 0.30 * (a - 0.70) / 0.30;
}

/* ---------- request parsing ---------- */
const CN_NUM = { 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8 };
// Bare English zone names ("south", "the east") are matched on a word
// boundary, not as substrings — the reason they were missing is that
// `includes('west')` also matches Westmere. Without them an English reader
// typing "south" had their zone silently dropped: 157 suburbs came back where
// the same question in Chinese returned 35.
const zoneHit = (t, w) => /^[a-z ]+$/.test(w)
  ? new RegExp(`\\b${w}\\b`).test(t) : t.includes(w);
const ZONE_WORDS = {
  '北岸': ['北岸', 'north shore', 'northshore'],
  '西区': ['西区', '西奥克兰', 'west auckland', '西边', 'west'],
  '中区': ['中区', '市中心', '中心区', 'central', 'cbd', '市区', '城里'],
  '东区': ['东区', '东奥克兰', 'east auckland', '东边', 'east'],
  '南区': ['南区', '南奥克兰', 'south auckland', '南边', 'south'],
  '北部乡村': ['rodney', '北部', '乡村'],
  '海岛': ['waiheke', '激流岛', '海岛'],
};
const WANT_WORDS = {
  invest: ['投资', '出租', '回报', '收益', 'yield', 'rental', 'investment'],
  quiet: ['安静', '清静', '不吵', 'quiet', '宜居'],
  land: ['大地', '院子', '花园', '地大', '独立屋', 'section', 'land', 'house'],
  apartment: ['公寓', 'apartment', 'unit', '小户型'],
  commute: ['通勤', '上班', '方便', '交通', 'commute'],
  coastal: ['海边', '海景', '靠海', 'beach', 'coastal', '沙滩'],
  growth: ['升值', '增值', '涨', 'growth', 'potential'],
  liquid: ['好卖', '好脱手', '流动'],
  cheap: ['便宜', '实惠', '划算', '经济', '入门', '低价', 'cheap', 'cheapest', 'affordable', 'low price', 'entry level', 'bargain'],
};
// Things people ask for that this dataset genuinely cannot answer. Saying so is
// the point — a confident guess about school zones is worse than no answer.
const UNSUPPORTED = {
  school: ['学区', '学校', 'school', 'decile', 'zone in', '教育'],
  crime: ['治安', '安全', 'crime', 'safe'],
  ethnicity: ['华人', '亚裔', '族裔', 'chinese community', 'asian'],
  hazard: ['洪水', '水浸', '滑坡', 'flood', 'landslide'],
};

function parseRequest(text) {
  const t = text.toLowerCase();
  const c = { budget: null, beds: null, zones: [], suburbs: [], maxKm: null,
              wants: [], missing: [] };

  // budget — take the largest figure mentioned, that is the ceiling people mean
  const cands = [];
  for (const m of t.matchAll(/(\d+(?:\.\d+)?)\s*万/g)) cands.push(+m[1] * 1e4);
  for (const m of t.matchAll(/(\d+(?:\.\d+)?)\s*m(?:il)?\b/g)) cands.push(+m[1] * 1e6);
  for (const m of t.matchAll(/(\d+(?:\.\d+)?)\s*k\b/g)) cands.push(+m[1] * 1e3);
  for (const m of t.matchAll(/\$?\s*(\d[\d,]{5,})/g)) cands.push(+m[1].replace(/,/g, ''));
  const money = cands.filter(v => v >= 1e5 && v <= 2e7);
  if (money.length) c.budget = Math.max(...money);

  // bedrooms
  const bed = t.match(/([一二两三四五六七八\d])\s*(?:房|室|卧|b(?:ed)?r?(?:oom)?s?\b)/);
  if (bed) c.beds = CN_NUM[bed[1]] || +bed[1] || null;

  // distance to town
  const km = t.match(/(\d+)\s*(?:公里|km)/);
  if (km) c.maxKm = +km[1];
  else if (/离市中心近|靠近市中心|close to (the )?(cbd|city)/.test(t)) c.maxKm = 12;

  for (const [zone, words] of Object.entries(ZONE_WORDS))
    if (words.some(w => zoneHit(t, w))) c.zones.push(zone);
  // "市中心" is usually a reference point, not a destination: "离市中心 25 公里"
  // and "上班在市中心" are both distance constraints, not "I want to live there".
  const asReference = /(离|距|到|near|from)\s*(市中心|cbd|city)/.test(t)
                   || /(上班|工作|通勤|work)/.test(t);
  const asHome = /住在?\s*(市中心|中区|cbd)|walk to (the )?(cbd|city)|走路.*市中心/.test(t);
  if (c.zones.includes('中区') && asReference && !asHome) {
    c.zones = c.zones.filter(z => z !== '中区');
    c.maxKm = c.maxKm || 15;
    c.wants.push('commute');
  }
  for (const s of all) if (s.p && t.includes(s.n.toLowerCase())) c.suburbs.push(s.n);
  for (const [w, words] of Object.entries(WANT_WORDS))
    if (words.some(x => t.includes(x))) c.wants.push(w);
  for (const [key, words] of Object.entries(UNSUPPORTED))
    if (words.some(x => t.includes(x))) c.missing.push(key);
  c.wants = [...new Set(c.wants)];
  // Financing is not a filter — it does not change which suburbs fit. It only
  // changes what gets said afterwards, so the model never has to touch it.
  c.finance = /房贷|按揭|月供|还款|贷款|首付|利率|地税|市政费|mortgage|repayment|instal|deposit|interest rate|council rates/i.test(text);
  return c;
}

const MISSING_LABEL = {
  school: ['学区 / 学校', 'school zones'], crime: ['治安', 'crime'],
  ethnicity: ['族裔构成', 'ethnic makeup'], hazard: ['洪水 / 地质风险', 'flood and landslide risk'],
};
const missingLabels = keys => keys.map(k => MISSING_LABEL[k][LANG === 'zh' ? 0 : 1])
  .join(L('、', ', ')) + L('的数据目前不在这个数据集里', ' is not in this dataset');

/* ---------- scoring ---------- */
const REF = DATA.ref;
const density = s => (s.o && s.ar) ? s.o / s.ar : null;   // people per km2

function scoreSuburb(s, c) {
  if (!s.p || !s.dt) return null;
  const a = affordShare(s, c.budget);
  if (c.budget && (a === null || a < 0.20)) return null;
  if (c.zones.length && !c.zones.includes(s.z)) return null;
  if (c.suburbs.length && !c.suburbs.includes(s.n)) return null;
  if (c.maxKm && s.km > c.maxKm) return null;
  // Asking for a house with a yard rules out a suburb that is essentially all
  // flats, however well it fits the budget.
  if (c.wants.includes('land') && (s.hs ?? 0) < 0.20) return null;
  if (s.dt.n < 150) return null;                 // too few homes to say anything

  let pref = 0, weight = 0;
  const add = (v, w = 1) => { pref += v * w; weight += w; };

  if (c.beds) {
    const share = (s.bm || [])[Math.min(4, c.beds - 1)] || 0;
    add(Math.min(1, share / 35), 1.4);
  }
  for (const w of c.wants) {
    if (w === 'invest' && s.i != null)
      add(clamp01((s.i - REF.yield.p25) / Math.max(0.1, REF.yield.p75 - REF.yield.p25)), 1.5);
    if (w === 'growth' && s.g != null)
      add(clamp01((s.g - REF.growth.p25) / Math.max(0.1, REF.growth.p75 - REF.growth.p25)), 1.2);
    if (w === 'liquid' && s.s != null)
      add(clamp01((REF.days.p75 - s.s) / Math.max(1, REF.days.p75 - REF.days.p25)), 1);
    if (w === 'commute' && s.km != null) add(clamp01((30 - s.km) / 25), 1.3);
    if (w === 'land') {
      add(clamp01(((s.hs ?? 0) - 0.2) / 0.6), 1.6);
      add(clamp01(((s.la || 0) - 250) / 500), 0.8);
    }
    if (w === 'apartment') add(clamp01(1 - (s.hs ?? 0.5) / 0.5), 1.4);
    if (w === 'quiet') {
      const d = density(s);
      add(d === null ? 0.5 : clamp01(1 - d / 4000), 1.0);
    }
    if (w === 'coastal') {
      // Was guessing from the name alone, which scored Mission Bay and missed
      // Muriwai. The intro says it outright where there is one.
      const about = s.w ? s.w.extract : '';
      const named = /bay|beach|point|heads|coast|island/i.test(s.n);
      const said = /beach|coast|harbour|harbor|shore|seaside|waterfront|gulf|bay/i.test(about);
      add(said ? 1 : named ? 0.8 : 0.15, 0.9);
    }
  }
  const prefScore = weight ? pref / weight : 0.5;
  const bs = c.budget ? budgetScore(a) : 0.6;
  return { s, a, bs, prefScore, total: 0.6 * bs + 0.4 * prefScore };
}
const clamp01 = v => Math.max(0, Math.min(1, v));

/* ---------- pros and cons, every one attached to a number ---------- */
function prosCons(r, c) {
  const s = r.s, dt = s.dt, pro = [], con = [];
  const pctS = v => (v * 100).toFixed(0) + '%';

  if (r.a !== null) {
    if (r.a >= 0.35)
      pro.push(L(`预算内可选约 ${pctS(r.a)} 的房子（区内 ${dt.n.toLocaleString('en-NZ')} 个计税单元）`,
                 `About ${pctS(r.a)} of homes here fit the budget (${dt.n.toLocaleString('en-NZ')} rating units)`));
    else
      con.push(L(`预算内只有约 ${pctS(r.a)} 的房子，选择面窄`,
                 `Only about ${pctS(r.a)} of homes here fit the budget — a thin choice`));
    if (r.a > 0.93 && c.budget)
      con.push(L(`预算高出这个区不少，${pctS(r.a)} 的房子都在预算内，可能买得比需要的更便宜`,
                 `Your budget sits well above this suburb — ${pctS(r.a)} of it is affordable, so you may be buying below what you could`));
  }
  const spread = dt.q[3] / dt.q[1];
  if (spread > 2.2)
    con.push(L(`区内价差大（中间 50% 落在 ${fmtK(dt.q[1])}–${fmtK(dt.q[3])}），街区选择很关键`,
               `Wide spread inside the suburb (middle 50% runs ${fmtK(dt.q[1])}–${fmtK(dt.q[3])}) — which street matters a lot`));

  if (s.y != null && s.y <= -4) con.push(L(`过去一年估值下跌 ${Math.abs(s.y).toFixed(1)}%`,
                                           `Down ${Math.abs(s.y).toFixed(1)}% over the past year`));
  if (s.y != null && s.y >= 1.5) pro.push(L(`过去一年估值上涨 ${s.y.toFixed(1)}%`,
                                           `Up ${s.y.toFixed(1)}% over the past year`));
  if (s.g != null && s.g >= REF.growth.p75) pro.push(L(`长期年化增长 ${s.g.toFixed(1)}%，全区前 25%`,
                                                      `Long-term growth ${s.g.toFixed(1)}%/yr — top quartile for the region`));
  if (s.g != null && s.g <= REF.growth.p25) con.push(L(`长期年化增长 ${s.g.toFixed(1)}%，全区后 25%`,
                                                      `Long-term growth ${s.g.toFixed(1)}%/yr — bottom quartile for the region`));

  if (s.i != null && s.i >= REF.yield.p75)
    pro.push(L(`租金回报 ${s.i.toFixed(1)}%，全区前 25%（周租中位 $${s.r}）`,
               `Gross yield ${s.i.toFixed(1)}% — top quartile (median rent $${s.r}/wk)`));
  if (s.i != null && s.i <= REF.yield.p25 && c.wants.includes('invest'))
    con.push(L(`租金回报 ${s.i.toFixed(1)}%，全区后 25%，不适合收租`,
               `Gross yield ${s.i.toFixed(1)}% — bottom quartile; poor for renting out`));

  if (s.s != null && s.s <= REF.days.p25) pro.push(L(`中位 ${s.s} 天售出，比全区快`,
                                                     `Sells in ${s.s} days at the median — faster than the region`));
  if (s.s != null && s.s >= REF.days.p75) con.push(L(`中位 ${s.s} 天才售出，市场偏冷`,
                                                    `Takes ${s.s} days to sell at the median — a slow market`));
  if (s.c != null && s.c < 25) con.push(L(`近 12 个月只成交 ${s.c} 套，流动性低、可比案例少`,
                                          `Only ${s.c} sales in 12 months — thin, and few comparables`));
  else if (s.c != null && s.c >= REF.sold.p75) pro.push(L(`近 12 个月成交 ${s.c} 套，选择多`,
                                                         `${s.c} sales in 12 months — plenty comes up`));

  if (s.km != null) {
    if (s.km <= 12) pro.push(L(`离市中心 ${s.km} km`, `${s.km} km from the city centre`));
    else if (s.km >= 28) con.push(L(`离市中心 ${s.km} km，通勤是主要代价`,
                                    `${s.km} km out — the commute is the real cost`));
  }
  if (s.hs != null) {
    const hp = (s.hs * 100).toFixed(0);
    if (s.hs >= 0.65)
      pro.push(L(`${hp}% 的房源是 ≥300 m² 的独立地块${s.la ? `（中位 ${s.la} m²）` : ''}`,
                 `${hp}% of homes sit on a section of 300 m² or more${s.la ? ` (median ${s.la} m²)` : ''}`));
    else if (s.hs <= 0.30) {
      const line = L(`只有 ${hp}% 的房源有独立地块，绝大多数是公寓或单元房`,
                     `Only ${hp}% of homes have their own section — this is apartments and units`);
      // Which side of the ledger that sits on depends on what was asked for.
      (c.wants.includes('apartment') ? pro : con).push(line);
    }
    else if (s.la && s.la <= 300)
      con.push(L(`地块中位仅 ${s.la} m²，多为联排`, `Median section just ${s.la} m² — mostly terraces`));
  }
  const dn = density(s);
  if (dn !== null && dn >= 4000) con.push(L(`人口密度 ${Math.round(dn).toLocaleString('en-NZ')} 人/km²，居住密集`,
                                            `${Math.round(dn).toLocaleString('en-NZ')} people/km² — densely built`));
  else if (dn !== null && dn <= 700 && c.wants.includes('quiet'))
    pro.push(L(`人口密度仅 ${Math.round(dn)} 人/km²，安静`, `Just ${Math.round(dn)} people/km² — quiet`));
  const flats = ((s.bm || [])[0] || 0) + ((s.bm || [])[1] || 0);
  if (c.beds >= 3 && flats >= 55)
    con.push(L(`一两房占 ${flats.toFixed(0)}%，${c.beds} 房选择相对少`,
               `${flats.toFixed(0)}% is one and two bedroom — fewer ${c.beds}-bed options`));
  if (c.beds && (s.bm || [])[Math.min(4, c.beds - 1)] >= 32)
    pro.push(L(`${c.beds} 房占 ${s.bm[Math.min(4, c.beds - 1)].toFixed(0)}%，主力户型`,
               `${c.beds}-bed is ${s.bm[Math.min(4, c.beds - 1)].toFixed(0)}% of stock — the main type here`));
  if (s.rp != null && s.rp >= 45)
    con.push(L(`租房人口占 ${s.rp.toFixed(0)}%，自住氛围偏弱`,
               `${s.rp.toFixed(0)}% renters — less of an owner-occupier feel`));
  if (dt.chg != null && dt.chg <= -0.12)
    con.push(L(`2021→2024 政府重估下调 ${Math.abs(dt.chg * 100).toFixed(0)}%`,
               `Council revaluation cut ${Math.abs(dt.chg * 100).toFixed(0)}% from 2021 to 2024`));

  return { pro: pro.slice(0, 4), con: con.slice(0, 4) };
}

// Which single constraint is doing the excluding? Relax each in turn and see.
function diagnose(c) {
  const count = cc => all.map(s => scoreSuburb(s, cc)).filter(Boolean).length;
  const trials = [
    [L('区域限制', 'the area'), { ...c, zones: [], suburbs: [] }],
    [L('通勤距离', 'the distance'), { ...c, maxKm: null }],
    [L('独立地块要求', 'needing a section'), { ...c, wants: c.wants.filter(w => w !== 'land') }],
    [L('房型要求', 'the bedroom count'), { ...c, beds: null }],
  ].filter(([, cc]) => JSON.stringify(cc) !== JSON.stringify(c));

  const helps = trials.map(([label, cc]) => [label, count(cc)]).filter(([, n]) => n > 0);
  const out = [];
  if (helps.length)
    out.push(L('<br>放宽其中一条就有结果：', '<br>Relaxing any one of these opens it up: ') +
      helps.map(([l, n]) => L(`<b>${l}</b>（${n} 个）`, `<b>${l}</b> (${n})`)).join(L('、', ', ')));

  // cheapest entry point that satisfies everything except the budget
  const noBudget = all.map(s => scoreSuburb(s, { ...c, budget: null })).filter(Boolean);
  if (noBudget.length) {
    const best = noBudget.map(r => r.s).sort((a, b) => a.dt.q[1] - b.dt.q[1])[0];
    out.push(L(`<br>其余条件不变的话，最低门槛在 <b>${best.n}</b>，那里 25% 分位的 CV 是 ${fmt(best.dt.q[1])} —— 预算要到这个量级才有得选。`,
               `<br>Keeping everything else, the cheapest way in is <b>${best.n}</b>, where the 25th-percentile CV is ${fmt(best.dt.q[1])} — that is the budget this needs.`));
  }
  return out.join('') || L('<br>把预算或区域放宽一些再试。', '<br>Try a larger budget or a wider area.');
}


/* ---------- scope guard ----------
   This answers one question: which Auckland suburb fits a budget. Anything
   else gets declined rather than half-answered, both because a property tool
   guessing at unrelated topics is worse than useless and because an open
   model endpoint on a public page is a standing invitation to use it as a
   free general-purpose chatbot.

   Deliberately permissive: "which area suits a family?" carries no budget and
   no keyword but is plainly on topic. Only a request with no property signal
   at all AND a clear off-topic shape is refused. */
const TOPIC_WORDS = [
  '房', '屋', '住', '买', '購', '租', '预算', '預算', '首付', '贷款', '按揭', '地段',
  '区', '區', '郊区', '学区', '通勤', '上班', '投资', '回报', '楼', '公寓', '别墅',
  '院子', '地块', '装修', '房价', '估价', '中介', 'suburb', 'house', 'home', 'flat',
  'apartment', 'property', 'buy', 'buying', 'rent', 'rental', 'budget', 'mortgage',
  'deposit', 'yield', 'invest', 'live', 'living', 'move', 'area', 'neighbourhood',
  'neighborhood', 'commute', 'school', 'section', 'land', 'bedroom', 'auckland',
];
const OFFTOPIC_SHAPES = [
  /写(一[首篇段]|个|下)|翻译|代码|程序|作文|故事|笑话|食谱|菜谱|歌词|论文|简历/,
  /\b(write|translate|code|program|debug|script|poem|story|joke|recipe|essay|resume|summar[iy])\b/i,
  /\b(who|what|when|where|why)\s+(is|are|was|were)\b(?!.*\b(suburb|area|price|budget)\b)/i,
  /python|javascript|sql|html|api|regex/i,
  /天气|新闻|股票|币|翻译成|怎么做菜/,
];

function topicSignals(text, c) {
  const t = text.toLowerCase();
  let n = 0;
  if (c.budget) n += 2;
  if (c.beds) n++;
  if (c.zones.length || c.suburbs.length) n += 2;
  if (c.maxKm) n++;
  n += c.wants.length;
  // Asking about schools, crime or flood risk IS a property question — it is one
  // this dataset cannot answer, which is a different thing from off topic.
  n += c.missing.length * 2;
  for (const w of TOPIC_WORDS) if (t.includes(w)) { n++; break; }
  return n;
}

function offTopic(text, c) {
  if (topicSignals(text, c) >= 2) return false;
  if (OFFTOPIC_SHAPES.some(re => re.test(text))) return true;
  return topicSignals(text, c) === 0 && text.trim().length > 4;
}

function refuse() {
  say(L('我只做一件事：<b>按预算帮你在奥克兰挑 suburb</b>，别的问题我不回答。<br>' +
        '可以这样问我：「预算 110 万，三房，北岸」「90 万投资，看重租金回报」' +
        '「150 万要大院子，离市中心 20 公里内」。',
        'I do one thing: <b>shortlist Auckland suburbs against a budget</b>. ' +
        'Anything else I will not answer.<br>Try: "$1.1m, 3 bedrooms, North Shore", ' +
        '"$900k to invest, want yield", "$1.5m, big section, within 20 km of the city".'));
}

// Outline a recommendation on the region map while the pointer is on its card.
// Pan only when it is off screen, and never zoom: a map that jumps under the
// cursor costs more orientation than it gives.
function focusOnMap(name) {
  if (D) return;                                   // detail view is showing instead
  const el = nodes.get(name);
  if (!el) return;
  clearMapFocus();
  document.querySelectorAll('#map path').forEach(p => p.classList.add('faded'));
  el.classList.remove('faded');
  el.classList.add('focus');
  el.parentNode.appendChild(el);                   // raise above its neighbours

  const b = el.getBBox(), v = svg.viewBox.baseVal;
  const cx = b.x + b.width / 2, cy = b.y + b.height / 2;
  const margin = 0.08;
  const outside = cx < v.x + v.width * margin || cx > v.x + v.width * (1 - margin)
               || cy < v.y + v.height * margin || cy > v.y + v.height * (1 - margin);
  if (outside) {
    vb = { x: cx - v.width / 2, y: cy - v.height / 2, w: v.width, h: v.height };
    writeVB(vb.x, vb.y, vb.w, vb.h);
  }
}

function clearMapFocus() {
  document.querySelectorAll('#map path.faded, #map path.focus')
    .forEach(p => p.classList.remove('faded', 'focus'));
}

/* ---------- rendering ---------- */
function say(html, cls = 'msg-ai') {
  const d = document.createElement('div');
  d.className = cls;
  d.innerHTML = html;
  $('#aiLog').appendChild(d);
  $('#aiLog').scrollTop = $('#aiLog').scrollHeight;
  return d;
}

// "Can I buy here" and "can I carry it every month" are different questions,
// and the second is the one that actually stops people. Quoted at the entry
// price, on whatever assumptions the calculator currently holds, so the two
// features never disagree on screen.
function costLine(s) {
  const price = s.dt.q[1];
  const pay = repayment(price * (1 - CALC.dep / 100), CALC.rate, CALC.years, 12, false);
  // Rates on the same house, not on the suburb's middle one: entry price is a
  // council valuation itself, so an entry level home is rated on an entry
  // level CV. Quoting the median here overstated the bill by a third.
  const rates = councilRates(price, false).total / 12;
  return L(`${fmt(price)}、首付 ${CALC.dep}%、${pctL(CALC.rate)} ${CALC.years} 年 → 每月约 <b>${fmt(pay)}</b> ＋ 地税 ${fmt(rates)}`,
           `${fmt(price)} at ${CALC.dep}% down, ${pctL(CALC.rate)} over ${CALC.years}yr → about <b>${fmt(pay)}</b>/month plus ${fmt(rates)} rates`);
}

function renderRec(r, c, rank, why) {
  const s = r.s, pc = prosCons(r, c);
  const el = document.createElement('div');
  el.className = 'rec';
  el.innerHTML = `
    <div class="top"><span class="nm">${s.n}</span>
      <span class="zn">${zoneL(s.z)} · ${s.km} km</span>
      <span class="rank">#${rank}</span></div>
    <div class="price"><b>${fmt(s.dt.q[1])}</b> ${L('起', 'and up')} ·
      ${L('中位', 'median')} ${fmt(s.dt.med)}</div>
    <div class="price2">${L(`区内 25% 的房子在 ${fmt(s.dt.q[1])} 以下 · 平均估值 ${fmt(s.p)}`,
                            `a quarter of homes here are under ${fmt(s.dt.q[1])} · average value ${fmt(s.p)}`)}</div>
    <div class="cost">${costLine(s)}</div>
    ${r.a === null ? '' : `<div class="fitbar"><i style="width:${(r.a * 100).toFixed(0)}%"></i></div>
      <div class="fitcap">${L(`预算内可选 ${(r.a * 100).toFixed(0)}% 的房子`, `${(r.a * 100).toFixed(0)}% of homes fit the budget`)}</div>`}
    ${why ? `<p class="why">${why.replace(/</g, '&lt;')}</p>` : ''}
    <ul>${pc.pro.map(x => `<li class="pro">${x}</li>`).join('')}
        ${pc.con.map(x => `<li class="con">${x}</li>`).join('')}</ul>
    <button class="go">${L(`打开 ${s.n} 热力图 →`, `Open ${s.n} heat map →`)}</button>`;
  el.querySelector('.go').addEventListener('click', () => {
    enterDetail(s.n);
    if (innerWidth < 900) closePanel();
  });
  el.addEventListener('pointerenter', () => focusOnMap(s.n));
  el.addEventListener('pointerleave', clearMapFocus);
  return el;
}

function describeCriteria(c) {
  const bits = [];
  if (c.budget) bits.push(L(`预算 <b>${fmt(c.budget)}</b>`, `budget <b>${fmt(c.budget)}</b>`));
  if (c.beds) bits.push(L(`${c.beds} 房`, `${c.beds} bed`));
  if (c.zones.length) bits.push(c.zones.map(zoneL).join(' / '));
  if (c.suburbs.length) bits.push(c.suburbs.join(' / '));
  if (c.maxKm) bits.push(L(`离市中心 ≤ ${c.maxKm} km`, `within ${c.maxKm} km of the city`));
  const labels = LANG === 'zh'
    ? { invest: '投资收租', quiet: '安静', land: '大地块', apartment: '公寓',
        commute: '通勤方便', coastal: '近海', growth: '看重升值', liquid: '好脱手',
        cheap: '越便宜越好' }
    : { invest: 'rental yield', quiet: 'quiet', land: 'a section', apartment: 'apartment',
        commute: 'easy commute', coastal: 'near the coast', growth: 'capital growth',
        liquid: 'easy to resell', cheap: 'as cheap as possible' };
  c.wants.forEach(w => labels[w] && bits.push(labels[w]));
  return bits.length ? bits.join(L('、', ', ')) : L('（没读出具体条件）', '(nothing specific read)');
}

/* ==========================================================================
   Answer shapes
   A shortlist was the only thing this could say, so every question came out as
   one — "how is Remuera" produced a ranked recommendation of Remuera, which is
   an odd way to answer a question nobody asked. Four shapes now, chosen by
   local rules before the model is involved:

     shortlist  criteria -> ranked suburbs           (what it always did)
     assess     one suburb -> what it is like
     compare    two or more -> where they differ
     explain    a question about the data -> computed here, not by the model

   The verification contract is untouched, deliberately. assess and compare
   still come back as picks[].why, one paragraph per suburb, so every figure is
   still checked against that suburb's own row. explain is computed from the
   dataset and never asks the model for a number at all.
   ========================================================================== */
const ASK_WORDS = /怎么样|怎样|如何|值得|好不好|评价|介绍|说说|讲讲|了解|what.?s .* like|how is|how's|tell me about|worth|describe/i;
const CMP_WORDS = /哪个|那个|对比|比较|相比|还是|vs\.?|versus|compare|better|which of/i;
const AGG_WORDS = /最贵|最便宜|最高|最低|最快|最好卖|排名|平均|中位|整体|多少|哪些区|什么价|价位|贵不贵|dearest|cheapest|highest|lowest|fastest|average|median|overall|how many|how much|rank|what does .{0,12}cost/i;

function readIntent(text, c) {
  const named = c.suburbs.length;
  if (named >= 2 && CMP_WORDS.test(text)) return 'compare';
  if (named >= 2) return 'compare';
  if (named === 1 && (ASK_WORDS.test(text) || !(c.budget || c.beds || c.wants.length)))
    return 'assess';
  // A stated budget means they want somewhere to buy, not a statistic —
  // "预算 110 万" contains 多少-shaped words often enough to matter.
  if (!named && !c.budget && AGG_WORDS.test(text)) return 'explain';
  return 'shortlist';
}

// Where a suburb sits in the region, in words. A price means little without
// knowing that it is the 12th dearest of 205.
function standing(s) {
  const rank = sortedPrices.filter(p => p < s.p).length;
  const pct = Math.round(rank / sortedPrices.length * 100);
  return { rank: sortedPrices.length - rank, of: sortedPrices.length, pct };
}

function assessBlock(s, c) {
  const dt = s.dt, st = s.p ? standing(s) : null;
  const r = { s, a: affordShare(s, c.budget), bs: 0, prefScore: 0, total: 0 };
  const pc = prosCons(r, c);
  const row = (k, v) => v == null ? '' : `<div><span>${k}</span><span>${v}</span></div>`;

  const verdict = st
    ? L(`全区 ${st.of} 个有价格的郊区里排第 <b>${st.rank}</b> 贵（高于 ${st.pct}% 的郊区）。`,
        `The <b>${st.rank}</b> dearest of ${st.of} priced suburbs — above ${st.pct}% of them.`)
    : L('这个区没有市场价格数据。', 'No market price data for this suburb.');

  const stats = [
    row(L('入门价（25% 分位 CV）', 'Entry price (25th pct CV)'), dt ? fmt(dt.q[1]) : null),
    row(L('政府估价中位', 'Median council CV'), dt ? fmt(dt.med) : null),
    row(L('平均估值', 'Average value'), s.p ? fmt(s.p) : null),
    row(L('近一年变化', 'Past year'), s.y == null ? null : pct(s.y)),
    row(L('长期年化增长', 'Long-term growth'), s.g == null ? null : s.g.toFixed(1) + '%'),
    row(L('估算租金回报', 'Est. gross yield'), s.i == null ? null : s.i.toFixed(1) + '%'),
    row(L('周租金中位', 'Median rent/wk'), s.r ? '$' + s.r : null),
    row(L('中位售出天数', 'Days to sell'), s.s ? s.s + L(' 天', '') : null),
    row(L('近 12 月成交', 'Sold, 12m'), s.c ? s.c + L(' 套', '') : null),
    row(L('离市中心', 'To the city'), s.km == null ? null : s.km + ' km'),
  ].join('');

  return { verdict, stats, pc, r };
}

function renderAssess(s, c, why) {
  const b = assessBlock(s, c);
  const el = document.createElement('div');
  el.className = 'rec assess';
  el.innerHTML = `
    <div class="top"><span class="nm">${s.n}</span>
      <span class="zn">${zoneL(s.z)}${s.km == null ? '' : ' · ' + s.km + ' km'}</span></div>
    <p class="verdict">${b.verdict}</p>
    ${why ? `<p class="why">${why.replace(/</g, '&lt;')}</p>` : ''}
    <div class="dstats astats">${b.stats}</div>
    <ul>${b.pc.pro.map(x => `<li class="pro">${x}</li>`).join('')}
        ${b.pc.con.map(x => `<li class="con">${x}</li>`).join('')}</ul>
    <div class="cost">${costLine(s)}</div>
    <button class="go">${L(`打开 ${s.n} 热力图 →`, `Open ${s.n} heat map →`)}</button>`;
  el.querySelector('.go').addEventListener('click', () => {
    enterDetail(s.n);
    if (innerWidth < 900) closePanel();
  });
  el.addEventListener('pointerenter', () => focusOnMap(s.n));
  el.addEventListener('pointerleave', clearMapFocus);
  return el;
}

// Only the rows where they actually differ. A table where every line reads
// "about the same" is a table nobody finishes.
const CMP_ROWS = [
  ['入门价', 'Entry price', s => s.dt && s.dt.q[1], fmt, 'low'],
  ['政府估价中位', 'Median CV', s => s.dt && s.dt.med, fmt, 'low'],
  ['平均估值', 'Average value', s => s.p, fmt, 'low'],
  ['近一年变化', 'Past year', s => s.y, v => pct(v), 'high'],
  ['长期年化增长', 'Long-term growth', s => s.g, v => v.toFixed(1) + '%', 'high'],
  ['租金回报', 'Gross yield', s => s.i, v => v.toFixed(1) + '%', 'high'],
  ['周租金中位', 'Median rent/wk', s => s.r, v => '$' + v, 'high'],
  ['售出天数', 'Days to sell', s => s.s, v => v + L(' 天', ''), 'low'],
  ['近 12 月成交', 'Sold, 12m', s => s.c, v => String(v), 'high'],
  ['离市中心', 'To the city', s => s.km, v => v + ' km', 'low'],
  ['典型地块', 'Typical section', s => s.la, v => v + ' m²', 'high'],
];

function renderCompare(list, c) {
  const el = document.createElement('div');
  el.className = 'cmp';
  const head = list.map(s => `<th>${s.n}<em>${zoneL(s.z)}</em></th>`).join('');
  const rows = CMP_ROWS.map(([zh, en, get, fmtv, better]) => {
    const vals = list.map(get);
    if (vals.every(v => v == null)) return '';
    const nums = vals.filter(v => v != null);
    // Nothing is "best" if they are within a rounding error of each other.
    const spread = Math.max(...nums) - Math.min(...nums);
    const win = spread / Math.max(...nums.map(Math.abs), 1) < 0.02 ? null
      : (better === 'high' ? Math.max(...nums) : Math.min(...nums));
    return `<tr><th>${L(zh, en)}</th>` + vals.map(v =>
      `<td class="${v != null && v === win ? 'win' : ''}">${v == null ? '—' : fmtv(v)}</td>`
    ).join('') + '</tr>';
  }).join('');
  el.innerHTML = `<div class="tw"><table><thead><tr><th></th>${head}</tr></thead>
    <tbody>${rows}</tbody></table></div>
    <p class="cmpnote">${L('高亮的是该行更有利的一侧。价格类越低越有利，增长、回报、成交量越高越有利——但「有利」取决于你是自住还是投资。',
      'Highlighted is the more favourable side of each row. Lower is better for prices, higher for growth, yield and turnover — though which of those counts as better depends on whether you are living in it or renting it out.')}</p>`;
  return el;
}

/* ---------- questions the page can answer by itself ---------- */
// Not `priced` — that name is already a module-level array up top, and
// shadowing it at the top level is a page-wide SyntaxError, not a scoping bug.
const rankable = () => all.filter(s => s.p && s.dt);

const AGGS = [
  { re: /最贵|dearest|most expensive|priciest/i,
    run: () => rank('p', -1, L('平均估值最高', 'highest average value'), fmt) },
  { re: /最便宜|cheapest|least expensive/i,
    run: () => rank('q1', 1, L('入门价最低', 'lowest entry price'), fmt) },
  { re: /涨得最快|增长最快|升值最快|fastest[- ]?grow|grew (the )?(fastest|most)|highest growth|best growth/i,
    run: () => rank('g', -1, L('长期年化增长最高', 'highest long-term growth'), v => v.toFixed(1) + '%') },
  { re: /回报最高|收益最高|highest yield|best yield/i,
    run: () => rank('i', -1, L('估算租金回报最高', 'highest estimated gross yield'), v => v.toFixed(1) + '%') },
  { re: /最好卖|卖得最快|fastest.*sell|quickest.*sell|sell.*fastest/i,
    run: () => rank('s', 1, L('中位售出天数最少', 'fewest median days to sell'), v => v + L(' 天', ' days')) },
  { re: /成交最多|最活跃|most sold|most active/i,
    run: () => rank('c', -1, L('近 12 个月成交最多', 'most sales in the past 12 months'), v => v + L(' 套', '')) },
];

const GETTERS = { p: s => s.p, g: s => s.g, i: s => s.i, s: s => s.s, c: s => s.c,
                  q1: s => s.dt.q[1] };

function rank(key, dir, label, fmtv) {
  const get = GETTERS[key];
  const list = rankable().filter(s => get(s) != null)
                       .sort((a, b) => (get(a) - get(b)) * dir).slice(0, 8);
  if (!list.length) return null;
  const rows = list.map((s, i) =>
    `<tr><td class="n">${i + 1}</td><td>${s.n}</td><td class="z">${zoneL(s.z)}</td>` +
    `<td class="v">${fmtv(get(s))}</td></tr>`).join('');
  return `<p>${L(`${label}的 8 个郊区（共 ${rankable().length} 个有数据）：`,
                 `The 8 suburbs with the ${label} (of ${rankable().length} with data):`)}</p>
    <div class="tw"><table class="ranktbl"><tbody>${rows}</tbody></table></div>`;
}

// "How much is the East" — an aggregate over one of the seven zones.
function zoneAnswer(text) {
  const lower = text.toLowerCase();
  const zone = Object.entries(ZONE_WORDS).find(([, ws]) =>
    ws.some(w => zoneHit(lower, w)));
  if (!zone) return null;
  const list = rankable().filter(s => s.z === zone[0]);
  if (!list.length) return null;
  const med = a => { const v = a.slice().sort((x, y) => x - y); return v[Math.floor(v.length / 2)]; };
  return `<p>${L(`<b>${zoneL(zone[0])}</b>：${list.length} 个有数据的郊区。`,
                 `<b>${zoneL(zone[0])}</b>: ${list.length} suburbs with data.`)}</p>
    <div class="dstats astats">
      <div><span>${L('入门价中位', 'Median entry price')}</span><span>${fmt(med(list.map(s => s.dt.q[1])))}</span></div>
      <div><span>${L('平均估值中位', 'Median average value')}</span><span>${fmt(med(list.map(s => s.p)))}</span></div>
      <div><span>${L('最便宜', 'Cheapest')}</span><span>${[...list].sort((a, b) => a.dt.q[1] - b.dt.q[1])[0].n}</span></div>
      <div><span>${L('最贵', 'Dearest')}</span><span>${[...list].sort((a, b) => b.p - a.p)[0].n}</span></div>
    </div>`;
}

function explainAnswer(text) {
  for (const a of AGGS) if (a.re.test(text)) { const r = a.run(); if (r) return r; }
  return zoneAnswer(text);
}

async function handle(text) {
  if (AI.busy) return;
  AI.busy = true;
  $('#aiSend').disabled = true;
  say(text.replace(/</g, '&lt;'), 'msg-user');

  const c = parseRequest(text);
  const intent = readIntent(text, c);
  const done = () => { AI.busy = false; $('#aiSend').disabled = false; };

  // An aggregate is arithmetic over the dataset, and the page can do it
  // exactly. So it does — rather than asking the model for a number and then
  // having to check whether it made it up.
  //
  // Tried before the off-topic gate, deliberately: a question this page can
  // answer from its own data is on topic by definition, and "how much is the
  // East" was being refused for want of a budget or a suburb name.
  if (intent === 'explain') {
    const ans = explainAnswer(text);
    if (ans) {
      say(ans);
      say(`<span class="muted-note">${L(
        '这是页面直接算的，没有经过模型。想看某个区的详细评价，直接说区名；想比较，说两个区名。',
        'Computed straight from the dataset, no model involved. Name a suburb for a full assessment, or two to compare them.')}</span>`);
      return done();
    }
    // Not one of the shapes it can compute — fall through and treat it as a
    // request for suburbs, which is usually what it turns out to be.
  }

  if (offTopic(text, c)) { refuse(); return done(); }

  let picks = null, lead = null, modelWhy = new Map(), dropped = 0;
  if (MODEL_ON) {
    const out = await askModel(text).catch(() => null);
    // Advisory only. The model tends to read "I have no school data" as "not my
    // subject"; a stated budget or area says otherwise, and the local signal is
    // the more reliable judge of whether this is a property question at all.
    if (out && out.on_topic === false && topicSignals(text, c) < 2) {
      refuse();
      AI.busy = false; $('#aiSend').disabled = false; return;
    }
    if (out && out.picks && out.picks.length) {
      if (out.criteria) Object.assign(c, {
        budget: c.budget ?? out.criteria.budget ?? null,
        beds: c.beds ?? out.criteria.beds ?? null,
        maxKm: c.maxKm ?? out.criteria.maxKm ?? null,
        zones: c.zones.length ? c.zones : (out.criteria.zones || []),
        wants: [...new Set([...(c.wants || []), ...(out.criteria.wants || [])])],
      });
      lead = (out.lead && claimsCheckOut(out.lead, null)) ? out.lead : null;
      picks = [];
      for (const p of out.picks) {
        const x = byName.get(p.name);
        if (!x || !x.dt || !x.p) continue;
        // A budget is the one constraint worth re-checking here: it is exact,
        // and offering something out of reach is the failure that matters most.
        if (c.budget && x.dt.q[1] > c.budget * 1.02) { dropped++; continue; }
        const r = scoreSuburb(x, { ...c, zones: [], suburbs: [], maxKm: null, wants: [] })
                  || { s: x, a: affordShare(x, c.budget), bs: 0, prefScore: 0, total: 0 };
        picks.push(r);
        if (p.why && figuresCheckOut(p.why, factsFor(p.name)) && claimsCheckOut(p.why, p.name))
          modelWhy.set(p.name, p.why);
      }
      if (!picks.length) picks = null;
    } else if (!out) {
      say(`<span class="muted-note">${L('（AI 暂时不可用，已用本地规则推荐）',
                                        '(AI unavailable right now — using local rules)')}</span>`);
    }
  }

  say(L(`读到的条件：${describeCriteria(c)}`, `What I read: ${describeCriteria(c)}`));
  // Repayments are arithmetic the page does itself, so answer it here rather
  // than letting the model near a number it has no source for.
  if (c.finance)
    say(L(`每张卡片下面那行就是按<b>首付 ${CALC.dep}%、${pctL(CALC.rate)}、${CALC.years} 年</b>算的月供加地税。` +
          `想换首付比例、利率或年限，用页面上的「房贷与地税试算」，卡片会跟着变。`,
          `The line under each card is the monthly repayment plus rates at <b>${CALC.dep}% down, ` +
          `${pctL(CALC.rate)} over ${CALC.years} years</b>. Change the deposit, rate or term in ` +
          `"Mortgage and council rates" on the page and the cards follow.`));
  if (c.missing.length)
    say(`<span class="warn">${missingLabels(c.missing)}</span>` +
        L('，所以下面的推荐<b>没有</b>把它纳入考虑，我也不会替你猜。',
          ' — so the shortlist below does <b>not</b> account for it, and I will not guess.'));
  if (dropped)
    say(`<span class="muted-note">${L(`（有 ${dropped} 个模型给的区入门价超出预算，已剔除）`,
                                      `(${dropped} suggestion(s) priced above the budget were dropped)`)}</span>`);

  const usable = c.budget || c.beds || c.zones.length || c.maxKm || c.wants.length;
  if (!picks && !usable && c.missing.length) {
    say(L('我能按<b>价格、户型、地块大小、离市中心距离、租金回报、成交活跃度</b>帮你筛。' +
          '给个预算或大致区域，我就能开始。',
          'What I can filter on: <b>price, bedroom mix, section size, distance to the city, ' +
          'rental yield and how actively a suburb trades</b>. Give me a budget or an area and I can start.'));
    AI.busy = false; $('#aiSend').disabled = false; return;
  }

  // A named suburb is a question about that suburb, not a request to have it
  // recommended back. The model's prose is reused where it wrote any, and it
  // is verified exactly as before — one paragraph checked against one row.
  if (intent === 'assess' || intent === 'compare') {
    const list = c.suburbs.map(n => byName.get(n)).filter(s => s && s.dt);
    if (list.length) {
      if (intent === 'compare' && list.length >= 2) {
        say(lead || L(`<b>${list.map(s => s.n).join(' vs ')}</b>，按这个数据集能比的都在下面：`,
                      `<b>${list.map(s => s.n).join(' vs ')}</b> — everything this dataset can compare them on:`));
        say('').appendChild(renderCompare(list, c));
      } else {
        say(lead || L(`关于 <b>${list[0].n}</b>：`, `About <b>${list[0].n}</b>:`));
      }
      const box = say('');
      list.forEach(s => box.appendChild(renderAssess(s, c, modelWhy.get(s.n))));
      if (c.missing.length)
        say(`<span class="warn">${missingLabels(c.missing)}</span>` +
            L('，所以上面<b>没有</b>包含这一维。', ' — so none of the above accounts for it.'));
      say(`<span class="muted-note">${L(
        '数字全部来自本页数据集，跟郊区详情页是同一份。',
        'Every figure comes from this page\u2019s own dataset — the same one behind the suburb detail view.')}</span>`);
      return done();
    }
  }

  // Rules produce the answer whenever the model did not.
  if (!picks) {
    const scored = all.map(x => scoreSuburb(x, c)).filter(Boolean)
                      .sort((x, y) => y.total - x.total);
    if (!scored.length) {
      say(L('按这些条件<b>没有</b>匹配的郊区。', '<b>No</b> suburb matches all of that.') + diagnose(c));
      AI.busy = false; $('#aiSend').disabled = false; return;
    }
    if (c.wants.includes('cheap') && !c.budget) {
      picks = [...scored].sort((x, y) => x.s.dt.q[1] - y.s.dt.q[1]).slice(0, 3);
      lead = lead || L(`按<b>最便宜</b>排的（比的是各区 25% 分位的 CV，也就是入门价）。符合条件的有 ${scored.length} 个区：`,
                       `Sorted <b>cheapest first</b>, by each suburb's 25th-percentile CV — its entry price. ${scored.length} suburbs match:`);
    } else if (c.budget) {
      picks = scored.slice(0, 3);
      lead = lead || L(`按预算优先筛下来，${scored.length} 个郊区够得着，这 3 个最合适：`,
                       `Budget first: ${scored.length} suburbs are within reach. These three fit best:`);
    } else {
      const spread = scored.slice(0, Math.max(3, Math.ceil(scored.length * 0.6)))
                           .sort((x, y) => x.s.p - y.s.p);
      picks = [spread[0], spread[Math.floor(spread.length / 2)], spread[spread.length - 1]]
                .filter((r, i, arr) => r && arr.indexOf(r) === i);
      lead = lead || L(`没给预算，所以这几个是按你其它条件挑的，并<b>拉开了价位</b>，让你看到这一带的区间。给个预算我能筛得准得多。`,
                       `No budget given, so these match your other criteria and are <b>spread across the price range</b> to show what the area costs. Give me a budget and I can be far more precise.`);
    }
  }

  say(lead || L('按你的条件，这几个最合适：', 'These fit what you described:'));
  const box = say('');
  picks.forEach((r, i) => box.appendChild(renderRec(r, c, i + 1, modelWhy.get(r.s.n))));
  say(L('把鼠标放在上面任一个区，会在奥克兰地图上圈出它的位置；点按钮才进入该区的热力图。',
        'Hover any of them to outline it on the Auckland map; click the button to open that suburb’s heat map.'));

  AI.busy = false;
  $('#aiSend').disabled = false;
}

/* ---------- model layer ----------
   The model is given the reader's question and a shortlist this page has already
   filtered from its own data, with the real figures attached. It chooses among
   them and explains why — that is genuine analysis, not phrasing.

   What it still cannot do is invent. It only ever sees names from the shortlist,
   and every figure it writes is checked against that suburb's own data before
   the page will show it. A card whose reasoning fails the check falls back to
   the rule-generated pros and cons, which are exact by construction. */
const MODEL_ON = !!DATA.proxy;

// Every suburb with data, as a field list plus one array each — about 21 kB,
// roughly 7k tokens. Sending the lot is the point: a suburb should not be ruled
// out because a regex here failed to notice "east" or "cheap".
const TABLE_FIELDS = ['name', 'zone', 'entry_price', 'median_cv', 'avg_value',
  'cbd_km', 'change_1y_pct', 'long_term_growth_pct', 'gross_yield_pct',
  'median_rent_wk', 'days_to_sell', 'sold_12m', 'population', 'renter_pct',
  'own_section_pct', 'median_section_m2', 'bedroom_mix_1_to_5_pct', 'about'];

function tableRow(x) {
  const r1 = v => v == null ? null : Math.round(v);
  return [x.n, zoneL(x.z), x.dt.q[1], x.dt.med, x.p, x.km,
          x.y == null ? null : +x.y.toFixed(1),
          x.g == null ? null : +x.g.toFixed(1),
          x.i == null ? null : +x.i.toFixed(1),
          x.r || null, x.s || null, x.c || null, x.o || null, r1(x.rp),
          x.hs == null ? null : Math.round(x.hs * 100), x.la || null,
          (x.bm || []).map(v => Math.round(v || 0)).join('/') || null,
          // The Wikipedia opening paragraph. Costs ~23k tokens across the whole
          // table and buys the model an actual sense of place, instead of the
          // page guessing "coastal" from whether the name contains "bay".
          x.w ? x.w.extract : null];
}
const suburbTable = () => ({
  fields: TABLE_FIELDS,
  rows: all.filter(x => x.p && x.dt).map(tableRow),
});

// A row keyed by field name, for checking what the model wrote about it.
function factsFor(name) {
  const x = byName.get(name);
  if (!x || !x.dt) return null;
  const row = tableRow(x), out = {};
  TABLE_FIELDS.forEach((f, i) => { if (row[i] != null) out[f] = row[i]; });
  return out;
}

// Every figure the model wrote has to match one it was given — including bare
// numbers, which is where the first version leaked: "entry_price为790000" carries
// no $ and no %, so a regex looking only for currency and percentages waved it
// straight through.
const SAYS_UP = /上涨|涨了|涨幅|增长|升值|增值|rose|risen|increase|gain|up by/i;
const SAYS_DOWN = /下跌|跌了|跌幅|下降|回调|下调|减少|fell|fallen|decrease|decline|drop|down by/i;

function figuresCheckOut(text, facts) {
  if (!facts) return false;
  const nums = Object.values(facts).filter(v => typeof v === 'number');
  // 0.15, not 0.6. The tolerance exists to absorb rounding — one decimal
  // place is at most 0.05 out — and 0.6 was wide enough to reach the next
  // field along. Remuera yields 2.0% and grows 6.3%, so an invented "租金回报
  // 5.8%" landed within 0.6 of the growth figure and passed as if it had been
  // copied from the row. A checker that does not care which field a number
  // came from has to be tight enough that it cannot arrive at a different one.
  const tolFor = v => (v >= 1000 ? Math.max(5000, v * 0.02) : 0.15);

  for (const m of text.matchAll(/(\$\s?)?(\d[\d,]*(?:\.\d+)?)\s*([kKmM]\b|%|公里|km)?/g)) {
    const unit = m[3] || '';
    let v = parseFloat(m[2].replace(/,/g, ''));
    if (!isFinite(v)) continue;
    if (/[kK]/.test(unit)) v *= 1e3;
    if (/[mM]/.test(unit)) v *= 1e6;
    if (unit !== '%' && v >= 1900 && v <= 2100 && !m[1]) continue;   // a year
    if (unit !== '%' && v < 100 && !m[1]) continue;                  // "3 房", "12 个月"

    if (nums.some(x => Math.abs(x - v) <= tolFor(x))) continue;      // signs agree

    // "下跌了 2.3%" states -2.3 correctly: direction in words, magnitude as a
    // positive number. Rejecting that threw away most of the model's reasoning.
    // Accept the magnitude, but only when the words point the same way as the
    // sign — saying a fall of 2.3% "rose" is the error worth catching.
    const neg = nums.filter(x => x < 0).some(x => Math.abs(-x - v) <= tolFor(-x));
    if (neg) {
      const lead = text.slice(Math.max(0, m.index - 16), m.index);
      if (SAYS_UP.test(lead) && !SAYS_DOWN.test(lead)) return false;
      continue;
    }
    return false;
  }
  return true;
}

// Two tiers. The hard list is what the page has told the reader it does not
// have: a confident line about school zones or crime is the failure that
// matters, and no encyclopaedia paragraph makes it sourced. The soft list is
// character — "affluent", "sought after" — which the intro genuinely can
// support, so it is allowed only when that suburb's own intro backs it.
const HARD_BLOCK = /学区|学校|名校|私校|校网|中学|小学|decile|school|治安|安全|犯罪|crime|safe|华人|亚裔|族裔|ethnic|chinese communit|洪水|水浸|滑坡|flood|landslide|地震|earthquake/i;
const SOFT_CLAIM = /富人区|高档|档次|口碑|声誉|富裕|上流|prestig|reputab|affluent|wealthy|desirable|sought.after|exclusive|upmarket/i;
const SOFT_SOURCE = /affluent|wealthy|prosperous|expensive|exclusive|prestigious|sought|upmarket|renowned|famous|noted for|known for|leafy|desirable/i;

function claimsCheckOut(text, name) {
  if (HARD_BLOCK.test(text)) return false;
  if (SOFT_CLAIM.test(text)) {
    const about = name && byName.get(name)?.w?.extract;
    if (!about || !SOFT_SOURCE.test(about)) return false;
  }
  return true;
}

async function askModel(text) {
  const res = await fetch(DATA.proxy, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text, ...suburbTable() }),
  });
  const j = await res.json().catch(() => ({}));
  if (!res.ok || j.error) throw new Error(j.error || `HTTP ${res.status}`);
  return j;
}

/* ---------- panel wiring ---------- */
$('#aiFoot').innerHTML = MODEL_ON
  ? L('选区、打分与优缺点全部由本页数据算出；AI 只负责读懂你的话。',
      'The shortlist, scoring and trade-offs are computed from this page\u2019s data; the AI only reads your request.')
  : L('全部由本页数据按规则算出。', 'Computed from this page\u2019s data by rule.');
function openPanel() { $('#aiPanel').hidden = false; $('#aiToggle').hidden = true; $('#aiInput').focus(); }
function closePanel() { $('#aiPanel').hidden = true; $('#aiToggle').hidden = false; }
$('#aiToggle').addEventListener('click', openPanel);
$('#aiClose').addEventListener('click', closePanel);
$('#aiForm').addEventListener('submit', e => {
  e.preventDefault();
  const v = $('#aiInput').value.trim();
  if (!v) return;
  $('#aiInput').value = '';
  handle(v);
});
$('#aiInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#aiForm').requestSubmit(); }
});
document.querySelectorAll('#aiChips button').forEach(b =>
  b.addEventListener('click', () => { $('#aiInput').value = b.textContent; $('#aiForm').requestSubmit(); }));

function resetAssistant() {
  $('#aiLog').innerHTML = '';
  say(L('告诉我你的<b>预算</b>和想住的大致区域，我按预算优先给你筛郊区，并说清每个区的好处和代价。<br>价格口径：平均估值与议会 CV，都不是成交价。',
        'Tell me your <b>budget</b> and roughly where you want to be. I shortlist suburbs budget-first and spell out what each one costs you.<br>All figures are estimates — automated valuations and council CVs, not sale prices.'));
}
resetAssistant();


/* ---------- long-form copy ---------- */
function notesHtml() {
  return LANG === 'zh' ? `
    <h2>免责声明</h2>
    <p style="margin:0 0 16px">个人研究项目，<b>不构成投资或购房建议</b>。页面上所有价格都是<b>估值</b>
      —— 自动估值模型与议会政府估价（CV）—— <b>不是成交价</b>，个体房产可能与之相差很大。
      选房助手的推荐来自公开数据上的统计规则，它不了解你的财务状况、也没有任何实地信息。
      做决定前请咨询持牌中介、注册估价师或财务顾问。</p>
    <h2>关于数据</h2>
    <ul>
      <li><b>指标：</b>各郊区「平均房产估值」（对区内全部住宅的自动估值取平均），<em>不是</em>成交价中位数。同期全奥克兰的成交中位价为 <b id="saleMed"></b>，两者口径不同，不可直接比较。</li>
      <li><b>价格来源：</b>Opes Partners 各郊区市场页（数据更新于 <span id="lu"></span>）。</li>
      <li><b>边界来源：</b>LINZ《NZ Suburbs and Localities》（CC BY 4.0），已做约 22 米的几何简化。</li>
      <li><b>配色：</b>发散色阶，中点 = 各郊区估值的中位数；「相对中位数」按与中位数的倍数取对数着色，「分位排名」按排名百分位着色。</li>
      <li><b>区内热力图：</b>点开某个郊区后看到的是<b>政府估价 CV</b>（Auckland Council 2024-05-01 估值，用于计算 rates），来自议会公开的逐地块估价图层，全区 <span id="nUnits"></span> 个计税单元落入郊区边界。每格约 35 米，取格内 CV 中位数；道路、绿地等格内无地块时，若周围有 3 个及以上相邻格有值，则用邻格中位数补齐，其余留空。色阶中点是<b>该郊区自身的</b> CV 中位数，所以每个区都用满整条色带，不同区之间的颜色不可横向比较。</li>
      <li><b>CV 的口径：</b>政府估价不是成交价，且包含全部计税单元——公寓单元、商铺、工业地都在内。所以公寓密集处会出现成片低值（那是"一套公寓多少钱"，不是"一栋房子多少钱"），Penrose 这类工业区的 CV 中位数也会明显高于住宅口径。</li>
      <li><b>郊区简介：</b>英文维基百科（CC BY-SA 4.0），按坐标距离核对后匹配，205 个郊区中 204 个有条目。<b>简介只有英文</b>，因为中文维基几乎没有奥克兰郊区条目。</li>
      <li><b>房贷试算：</b>标准等额本息公式，按名义周期利率计息（NZ 各行自己的计算器也是这么显示的）。利率取<b>各行当日最低挂牌利率</b>（<span id="rateAsAt"></span> 读取，来源 Opes Partners），<b>不是你能拿到的利率</b>——实际利率取决于银行、首付比例和收入。首付低于 20% 时银行通常加收低首付利率加点（约 0.25–1.5 个百分点），各行不同，页面只提示存在、不替它编一个数。</li>
      <li><b>地税估算：</b>Auckland Council <span id="rateYear"></span> 年度。议会公布的是<b>平均账单</b>而不是税率明细，所以页面上那四项是按它逐项公布的涨跌反推，并钉死在它唯一说明确的数上：均价住宅 CV <span id="rateAvgCv"></span> 今年缴 <span id="rateAvgTotal"></span>。<b>锚点上是准确的，离开锚点是估算。</b>另外两点常被搞混：地税按<b>政府估价 CV</b> 计，不按你的买价，买贵了不会立刻涨；<b>水费和污水费由 Watercare 单独收取</b>，不在地税里。以自己的房子为准请查议会的地税查询。</li>
      <li><b>覆盖范围：</b>共 <span id="nTotal"></span> 个郊区/地区，其中 <span id="nPriced"></span> 个有价格数据。斜纹区块无价格数据，多为农村、林地、机场、医院等，但也包含少数住宅区（如 Western Springs、Westgate、Hillpark、Wairau Valley）——价格源未收录。大堡岛（Aotea / Great Barrier）等外海岛屿不在 LINZ 郊区图层内，故未绘制。</li>
    </ul>
    <p style="margin:14px 0 0; color:var(--muted)">数据来源：LINZ（CC BY 4.0）· Auckland Council 公开估价图层 · Opes Partners · English Wikipedia（CC BY-SA 4.0）。页面为静态生成，无追踪、无 cookie、无后端。</p>
  ` : `
    <h2>Disclaimer</h2>
    <p style="margin:0 0 16px">A personal research project. <b>Not investment or property advice.</b>
      Every figure here is an <b>estimate</b> — an automated valuation model, or the council's
      rating valuation (CV) — <b>not a sale price</b>, and an individual property can sit a long way
      from it. The suburb finder applies statistical rules to public data; it knows nothing about your
      finances and has never seen the houses. Talk to a licensed agent, a registered valuer or a
      financial adviser before deciding anything.</p>
    <h2>About the data</h2>
    <ul>
      <li><b>The measure:</b> each suburb's <em>average house value</em> — the mean automated valuation
        across its housing stock — <em>not</em> a median sale price. Auckland's median sale price over the
        same period was <b id="saleMed"></b>; the two are different measures and are not comparable.</li>
      <li><b>Prices:</b> Opes Partners per-suburb market pages (source last refreshed <span id="lu"></span>).</li>
      <li><b>Boundaries:</b> LINZ <i>NZ Suburbs and Localities</i> (CC BY 4.0), simplified to about 22 m.</li>
      <li><b>Colour:</b> a diverging scale centred on the median of the suburb values. "Vs median" colours by
        the log of the ratio to that median; "Percentile" colours by rank.</li>
      <li><b>Inside a suburb:</b> opening a suburb shows <b>council capital values</b> (Auckland Council,
        valued 2024-05-01, the basis for rates), from the council's public per-parcel layer —
        <span id="nUnits"></span> rating units fall inside a suburb boundary. Cells are about 35 m and hold the
        median CV within them. Where a cell contains no parcel — roads, reserves — it is filled from the median
        of its neighbours if at least three of them have a value, and left blank otherwise. The scale is centred
        on <b>that suburb's own</b> median, so every suburb uses the full colour range and
        <b>colours are not comparable between suburbs</b>.</li>
      <li><b>What a CV is:</b> a rating valuation, not a sale price, and it covers every rating unit —
        apartments, shops and industrial land included. Apartment-dense areas therefore show blocks of low
        values (that is "what one apartment costs", not "what a house costs"), and an industrial suburb like
        Penrose reads far above what a residential-only figure would.</li>
      <li><b>Suburb intros:</b> English Wikipedia (CC BY-SA 4.0), matched by checking the article's coordinates
        against the suburb centroid; 204 of 205 suburbs have one. <b>Intros are English only</b> — Chinese
        Wikipedia has almost no articles on Auckland suburbs.</li>
      <li><b>Mortgage figures:</b> a standard table loan on the nominal periodic rate, which is how
        every NZ bank's own calculator quotes it. The rates offered are the <b>lowest carded rate</b>
        across the main banks (read <span id="rateAsAt"></span>, from Opes Partners) — <b>not the rate
        you will be offered</b>, which depends on the bank, your deposit and your income. Under a 20%
        deposit most banks add a low-equity margin of roughly 0.25–1.5 percentage points; it varies by
        bank, so the page names the gap rather than inventing a number for it.</li>
      <li><b>Council rates:</b> Auckland Council, <span id="rateYear"></span>. The council publishes the
        <b>average bill</b> rather than the schedule of rates, so the four components shown are
        reconstructed from the year-on-year movements it does publish, pinned to the one total it states
        outright: the average residential property at CV <span id="rateAvgCv"></span> pays
        <span id="rateAvgTotal"></span> this year. <b>Exact at that anchor, an estimate away from it.</b>
        Two things people commonly have backwards: rates are charged on the <b>council valuation</b>, not
        on what you paid, so paying above CV does not raise the bill; and <b>water and wastewater are
        billed separately by Watercare</b>, not included in rates. For a specific property, use the
        council's own rates search.</li>
      <li><b>Coverage:</b> <span id="nTotal"></span> suburbs and localities, <span id="nPriced"></span> of them with price
        data. Hatched areas have none: mostly rural land, forest, the airport and hospitals, but also a few
        genuinely residential suburbs (Western Springs, Westgate, Hillpark, Wairau Valley) that the price source
        does not cover. Aotea / Great Barrier and the outer gulf islands are not in the LINZ suburb layer and are
        not drawn.</li>
    </ul>
    <p style="margin:14px 0 0; color:var(--muted)">Sources: LINZ (CC BY 4.0) · Auckland Council public valuation
      layer · Opes Partners · English Wikipedia (CC BY-SA 4.0). Statically generated — no tracking, no cookies,
      no backend.</p>
  `;
}

// What moved since last week. Shown only when something did — a line reading
// "no change" every week for months is noise, and the notes explain the
// mechanism for anyone who wonders why it is sometimes absent.
function changesLine() {
  const ch = DATA.changed || {};
  const bits = [];
  if (ch.rates && ch.rates.moves.length) {
    const TERM = { '6m': L('6 个月','6m'), '1y': L('1 年','1yr'), '18m': L('18 个月','18m'),
                   '2y': L('2 年','2yr'), '3y': L('3 年','3yr'), '5y': L('5 年','5yr') };
    const parts = ch.rates.moves.map(([term, was, now]) => {
      const dir = now > was ? 'worse' : 'better';   // a rate rising is bad news
      return `${TERM[term] || term} <b>${was.toFixed(2)}% → <span class="${dir}">${now.toFixed(2)}%</span></b>`;
    });
    bits.push(L(`各行最低挂牌利率变动：${parts.join('、')}`,
                `Cheapest carded rates moved: ${parts.join(', ')}`));
  }
  if (ch.release && ch.release[0])
    bits.push(L(`价格源发布了新一期（${ch.release[0]} → <b>${ch.release[1]}</b>），全部郊区的估值已更新。`,
                `The price source published a new release (${ch.release[0]} → <b>${ch.release[1]}</b>); every suburb's valuation is updated.`));
  return bits;
}

// The source states a month, and the page has to say it in whichever language
// is on screen. It used to read DATA.asAtEn on the English branch — a key that
// was never in the payload — so English readers saw a hardcoded "June 2026"
// that would have stayed there through every refresh.
function monthLabel(iso) {
  const [y, m] = iso.split('-');
  return LANG === 'zh' ? `${y} 年 ${+m} 月`
    : new Date(+y, +m - 1, 1).toLocaleDateString('en-NZ',
        { month: 'long', year: 'numeric' });
}

const DAYS_STALE = 14;      // a weekly job, plus room for one missed run
const daysSince = iso => Math.floor((Date.now() - Date.parse(iso + 'T00:00:00')) / 864e5);

const SOURCE_L = {
  prices: ['房价', 'Prices'], valuations: ['政府估价', 'Council valuations'],
  boundaries: ['郊区边界', 'Suburb boundaries'], localboards: ['行政区划', 'Local boards'],
  wikipedia: ['简介', 'Intros'], mortgagerates: ['房贷利率', 'Mortgage rates'],
};

// When each source was last pulled, and when this page was built from them.
// A page that refreshes itself weekly and never says when is a page a reader
// has no way to date.
function provenance() {
  const b = DATA.built || {};
  const src = Object.entries(b.sources || {})
    .filter(([k]) => SOURCE_L[k])
    .sort((x, y) => (x[1] < y[1] ? 1 : -1));
  if (!src.length) return '';
  const newest = Math.min(...src.map(([, d]) => daysSince(d)));
  const rows = src.map(([k, d]) =>
    `<tr><td>${L(SOURCE_L[k][0], SOURCE_L[k][1])}</td><td>${d}</td>` +
    `<td>${L(`${daysSince(d)} 天前`, `${daysSince(d)}d ago`)}</td></tr>`).join('');
  // Rendered in whoever is reading's own timezone. The payload carries UTC
  // with an offset; a bare wall-clock time from whichever machine happened to
  // build it is not a fact about anything.
  const built = b.at
    ? new Date(b.at).toLocaleString(LANG === 'zh' ? 'zh-CN' : 'en-NZ',
        { dateStyle: 'medium', timeStyle: 'short' })
    : '';
  return `<h2>${L('数据是什么时候取的', 'When this was fetched')}</h2>
    <p style="margin:0 0 8px">${L(
      `本页构建于 <b>${built}</b>。每周一自动重跑一次，各源按自己的节奏抓 —— ` +
      `所以下面的日期本来就不该相同，房价季度级刷新，利率几天一变。`,
      `This page was built at <b>${built}</b>. It rebuilds itself every Monday and each ` +
      `source is pulled on its own cadence, so these dates are not meant to match: ` +
      `prices refresh quarterly, rates move within days.`)}</p>
    <table class="prov"><tbody>${rows}</tbody></table>
    ${newest > DAYS_STALE ? `<p class="stale">${L(
      `最近一次成功抓取已经是 ${newest} 天前 —— 定时任务可能停了，页面上的数字请当作过期处理。`,
      `The most recent successful fetch was ${newest} days ago — the scheduled job may have stopped, so treat these figures as stale.`)}</p>` : ''}`;
}

function subCopy() {
  return LANG === 'zh'
    ? `按郊区（suburb）着色的<b>平均房产估值</b>（Average House Value），数据截至 <b>${monthLabel(DATA.asAt)}</b>。
       颜色像气温图：<b>越红越贵，越蓝越便宜</b>，灰白色 = 接近全区中位水平。
       <b>点击任一郊区</b>可查看该区简介与区内逐街区的房价热力图。`
    : `<b>Average house value</b> by suburb, as at <b>${monthLabel(DATA.asAt)}</b>. The colour reads like a
       temperature map: <b>redder is dearer, bluer is cheaper</b>, near-neutral means close to the regional median.
       <b>Click any suburb</b> for an intro and a block-by-block heat map inside it.`;
}

function fillStats() {
  $('#notes').innerHTML = notesHtml() + provenance();
  $('#subCopy').innerHTML = subCopy();
  const set = (id, v) => { const e = $(id); if (e) e.textContent = v; };
  set('#saleMed', fmt(DATA.regionSaleMedian));
  set('#lu', DATA.lastUpdated);
  set('#nUnits', DATA.unitsMatched.toLocaleString('en-NZ'));
  set('#nTotal', all.length);
  set('#nPriced', priced.length);
  const bits = changesLine();
  const box = $('#changed');
  box.hidden = !bits.length;
  if (bits.length)
    box.innerHTML = `<span class="lab">${L('本周变化', 'What moved')}</span>` +
                    `<span>${bits.join(L('　', ' · '))}</span>`;
  set('#rateAsAt', DATA.fin.m.asAt);
  set('#rateYear', DATA.fin.c.year);
  set('#rateAvgCv', fmt(DATA.fin.c.avgCv));
  set('#rateAvgTotal', fmt(DATA.fin.c.avgTotal));
}

function enterDetailChrome(s) {
  $('#dName').textContent = s.n;
  $('#dKind').textContent = [zoneL(s.z), L(s.t === 'Suburb' ? '郊区' : '地区',
                             s.t === 'Suburb' ? 'suburb' : 'locality')].filter(Boolean).join(' · ');
  if (s.dt) {
    $('#dKind').textContent += L(` · 每格约 ${Math.round(s.dt.cs * DATA.metresPerUnit)} 米`,
                                 ` · ~${Math.round(s.dt.cs * DATA.metresPerUnit)} m per cell`);
    $('#dHint').textContent = L('滚轮缩放 · 拖拽平移 · 双击复位 · 悬停看该网格 CV 中位数',
                                'Scroll to zoom · drag to pan · double-click to reset · hover for a cell\u2019s median CV');
  }
}
document.querySelectorAll('[data-lang]').forEach(b =>
  b.addEventListener('click', () => setLang(b.dataset.lang)));

function setSmooth(on) {
  SMOOTH = on;
  localStorage.setItem('akl_smooth', on ? '1' : '0');
  $('#smOn').setAttribute('aria-pressed', String(on));
  $('#smOff').setAttribute('aria-pressed', String(!on));
  drawDetailMap();
}
$('#smOn').addEventListener('click', () => setSmooth(true));
$('#smOff').addEventListener('click', () => setSmooth(false));

/* ---------- boot ---------- */
applyLang();
fillStats();
tiles();
mountCalc();
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
