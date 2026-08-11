/**
 * Cloudflare Worker: the only place the Gemini key exists.
 *
 * A key embedded in the page cannot be hidden. The page is public, so view
 * source, devtools and the network tab all show it, and any obfuscation has to
 * be undone by the page itself before the call — a breakpoint gets it back in
 * seconds. Published from a public repo it also lives in git history forever,
 * and both Google and a steady population of scrapers scan for exactly that.
 *
 * So the key sits here as a secret, and the page calls this instead:
 *
 *   npx wrangler secret put GEMINI_API_KEY
 *
 * The page sends the question and every suburb it has data for — about 205 rows,
 * roughly 7k tokens as a field list plus arrays. The model does the choosing,
 * so a suburb is not ruled out by a regex in the page failing to notice "east"
 * or "cheap". It still cannot invent: names are checked against the table it was
 * given, and every figure it writes is checked against that suburb's own row
 * before the page will show the sentence.
 */

const MODEL = 'gemini-3.5-flash-lite';
const MAX_CHARS = 400;
const MAX_ROWS = 400;
const MAX_CELL = 60;

// This shortlists Auckland suburbs and declines everything else, so the endpoint
// cannot be farmed as a free general-purpose chatbot.
const TOPIC_WORDS = [
  '房', '屋', '住', '买', '購', '租', '预算', '預算', '首付', '贷款', '按揭', '地段',
  '区', '區', '郊区', '学区', '通勤', '上班', '投资', '回报', '楼', '公寓', '别墅',
  '院子', '地块', '房价', '估价', '中介', '便宜', '实惠', 'suburb', 'house', 'home',
  'flat', 'apartment', 'property', 'buy', 'buying', 'rent', 'rental', 'budget',
  'mortgage', 'deposit', 'yield', 'invest', 'live', 'living', 'move', 'area',
  'neighbourhood', 'neighborhood', 'commute', 'school', 'section', 'land',
  'bedroom', 'auckland', 'cheap', 'afford',
];
const OFFTOPIC = [
  /写(一[首篇段]|个|下)|翻译|代码|程序|作文|故事|笑话|食谱|菜谱|歌词|论文|简历/,
  /\b(write|translate|code|program|debug|script|poem|story|joke|recipe|essay|resume)\b/i,
  /python|javascript|sql|html|api|regex/i,
  /天气|新闻|股票|翻译成|怎么做菜/,
];

const SYS = `You advise on choosing an Auckland suburb, and nothing else.

You are given the reader's question and every Auckland suburb the page has data
for, as a field list and one array per suburb. All figures are real.

on_topic is false ONLY when the request has nothing to do with choosing where to
live in Auckland — code, translation, chit-chat, general knowledge. A property
question you can only partly answer is still on topic: answer the part the table
supports, say plainly which part it does not, and still return picks. Asking for
"the best school zone under $2m" means picking on price and housing type while
stating that school data is absent — not refusing.

Your job:
- Read the whole table and choose the suburbs that genuinely answer the question.
  Pick as few or as many as it deserves: one if one is clearly right, four or
  five if the reader is exploring. Never pad to a fixed number.
- If the reader gave a budget, entry_price is the test of whether they can buy
  there at all. Do not offer a suburb whose entry_price is above it.
- For each, say why it fits *this* question, and what it costs them. Name the
  real trade-off, not only the upside.
- Write a short lead sentence framing the set.

Hard rules:
- The table is your ONLY source. You may know things about these suburbs from
  elsewhere — schools, zoning, reputation, safety, who lives there, what the
  streets look like. Do not use any of it. If a claim cannot be read off the
  fields you were given, do not make it, even if you are confident it is true.
  Especially: say nothing about school zones or school quality. The page tells
  the reader plainly that it has no school data, and contradicting that two
  lines later is worse than saying nothing.
- Only ever name a suburb from the table. Never invent one.
- Every number you write must appear in that suburb's data, unchanged. If you
  are unsure of a figure, describe it in words instead. The page verifies every
  figure you write — including bare numbers, not just ones with a $ — and will
  discard your reasoning if one does not match.
- Write figures the way a person would: "入门价 $790,000", "租金回报 3.6%".
  Never quote a raw field name like entry_price or gross_yield_pct at the reader.
- entry_price is what it costs to get in (a quarter of homes are below it).
  avg_value and median_cv are typically much higher — do not present those as
  the price of buying there.
- No advice about mortgages, legal matters or whether to buy.
- Reply in the reader's language.

Output JSON only:
{"on_topic":true|false,
 "lead":"one or two sentences",
 "picks":[{"name":"exact name from the table","why":"2-3 sentences: fit, then trade-off"}],
 "criteria":{"budget":number|null,"beds":number|null,"zones":[],"maxKm":number|null,"wants":[]}}
zones must come from: 北岸, 西区, 中区, 东区, 南区, 北部乡村, 海岛.
wants must come from: invest, quiet, land, apartment, commute, coastal, growth, liquid, cheap.`;

function cors(origin, allowed) {
  const ok = allowed === '*' || (origin && allowed.split(',').map(s => s.trim()).includes(origin));
  return {
    'access-control-allow-origin': ok ? (origin || '*') : 'null',
    'access-control-allow-headers': 'content-type',
    'access-control-allow-methods': 'POST, OPTIONS',
    'access-control-max-age': '86400',
  };
}

function json(body, status, headers) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json', ...headers },
  });
}

function offTopic(text) {
  const t = text.toLowerCase();
  if (OFFTOPIC.some(re => re.test(text))) return true;
  return !(TOPIC_WORDS.some(w => t.includes(w)) || /\d/.test(t));
}

// The table arrives from a public page, so it is input, not something to trust:
// bounded rows, bounded cells, primitives only.
function cleanTable(body) {
  const fields = Array.isArray(body?.fields)
    ? body.fields.slice(0, 30).map(f => String(f).slice(0, 24)) : [];
  const rows = Array.isArray(body?.rows)
    ? body.rows.slice(0, MAX_ROWS)
        .filter(Array.isArray)
        .map(r => r.slice(0, fields.length).map(v =>
          v === null || v === undefined ? null
            : typeof v === 'number' ? v : String(v).slice(0, MAX_CELL)))
        .filter(r => r[0])
    : [];
  return { fields, rows };
}

export default {
  async fetch(request, env) {
    const allowed = env.ALLOWED_ORIGIN || '*';
    const headers = cors(request.headers.get('origin'), allowed);

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers });
    if (request.method !== 'POST') return json({ error: 'POST only' }, 405, headers);
    if (headers['access-control-allow-origin'] === 'null')
      return json({ error: 'origin not allowed' }, 403, headers);

    let body;
    try { body = await request.json(); } catch { return json({ error: 'bad json' }, 400, headers); }
    const text = String(body.text || '').slice(0, MAX_CHARS).trim();
    if (!text) return json({ error: 'empty request' }, 400, headers);
    if (offTopic(text)) return json({ on_topic: false }, 200, headers);

    if (env.RATE_LIMIT) {
      const ip = request.headers.get('cf-connecting-ip') || 'anon';
      const { success } = await env.RATE_LIMIT.limit({ key: ip });
      if (!success) return json({ error: 'rate limited, try again shortly' }, 429, headers);
    }
    if (!env.GEMINI_API_KEY) return json({ error: 'proxy not configured' }, 500, headers);

    const table = cleanTable(body);
    const prompt = table.rows.length
      ? `Reader's question:\n${text}\n\nfields: ${JSON.stringify(table.fields)}\n` +
        `rows (${table.rows.length} suburbs, all figures real):\n${
          table.rows.map(r => JSON.stringify(r)).join('\n')}`
      : `Reader's question:\n${text}\n\n(No suburb data was sent — say so.)`;

    const upstream = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${
        env.MODEL || MODEL}:generateContent?key=${env.GEMINI_API_KEY}`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          systemInstruction: { parts: [{ text: SYS }] },
          contents: [{ role: 'user', parts: [{ text: prompt }] }],
          generationConfig: { temperature: 0.5, maxOutputTokens: 1600,
                              responseMimeType: 'application/json' },
        }),
      });

    if (!upstream.ok) {
      const detail = await upstream.text();
      const safe = detail
        .replace(/AIza[0-9A-Za-z_\-]{10,}/g, '[redacted]')
        .replace(/key=[^&"'\s]+/g, 'key=[redacted]')
        .slice(0, 300);
      return json({ error: `upstream ${upstream.status}`, detail: safe }, 502, headers);
    }

    const j = await upstream.json();
    const raw = (j.candidates?.[0]?.content?.parts || []).map(p => p.text || '').join('');
    const m = raw.match(/\{[\s\S]*\}/);
    if (!m) return json({ error: 'model reply was not json' }, 502, headers);

    let parsed;
    try { parsed = JSON.parse(m[0]); } catch { return json({ error: 'bad model json' }, 502, headers); }

    const known = new Set(table.rows.map(r => r[0]));
    return json({
      on_topic: parsed.on_topic !== false,
      lead: typeof parsed.lead === 'string' ? parsed.lead.slice(0, 400) : '',
      // A name outside the shortlist is dropped here as well as in the page.
      picks: Array.isArray(parsed.picks)
        ? parsed.picks.filter(p => p && known.has(p.name)).slice(0, 6).map(p => ({
            name: p.name,
            why: typeof p.why === 'string' ? p.why.slice(0, 600) : '',
          }))
        : [],
      criteria: parsed.criteria || {},
    }, 200, headers);
  },
};
