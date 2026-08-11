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
 * Everything this proxy will do is also enforced here rather than in the page.
 * Client-side limits are a courtesy to honest users; the person who would abuse
 * an open model endpoint is the one editing the client.
 */

// Model ids get retired for new keys — 2.5-flash-lite already was. The
// upstream error says so plainly, and MODEL is a var in wrangler.toml so
// swapping it is a config change, not a code change.
const MODEL = 'gemini-3.5-flash-lite';
const MAX_CHARS = 400;

// Same rule as the page: this shortlists Auckland suburbs against a budget and
// declines everything else, so the endpoint cannot be farmed as a free chatbot.
const TOPIC_WORDS = [
  '房', '屋', '住', '买', '購', '租', '预算', '預算', '首付', '贷款', '按揭', '地段',
  '区', '區', '郊区', '学区', '通勤', '上班', '投资', '回报', '楼', '公寓', '别墅',
  '院子', '地块', '房价', '估价', '中介', 'suburb', 'house', 'home', 'flat',
  'apartment', 'property', 'buy', 'buying', 'rent', 'rental', 'budget', 'mortgage',
  'deposit', 'yield', 'invest', 'live', 'living', 'move', 'area', 'neighbourhood',
  'neighborhood', 'commute', 'school', 'section', 'land', 'bedroom', 'auckland',
];
const OFFTOPIC = [
  /写(一[首篇段]|个|下)|翻译|代码|程序|作文|故事|笑话|食谱|菜谱|歌词|论文|简历/,
  /\b(write|translate|code|program|debug|script|poem|story|joke|recipe|essay|resume)\b/i,
  /python|javascript|sql|html|api|regex/i,
  /天气|新闻|股票|翻译成|怎么做菜/,
];

const SYS = `You help someone choose an Auckland suburb, and nothing else.
Do exactly two things: extract structured criteria, and write one natural
opening sentence in the user's language.
Never name a suburb and never state a price or any statistic — those are
computed by the page from local data.
If the request is about anything other than buying or choosing where to live in
Auckland, set on_topic to false, leave the rest empty, and do not answer it.
Output JSON only:
{"on_topic":true|false,"criteria":{"budget":number|null,"beds":number|null,"zones":[],"maxKm":number|null,"wants":[]},"intro":"one sentence"}
zones must come from: 北岸, 西区, 中区, 东区, 南区, 北部乡村, 海岛.
wants must come from: invest, quiet, land, apartment, commute, coastal, growth, liquid.
budget is an integer in NZD ("110万" = 1100000).`;

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
    status,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

function offTopic(text) {
  const t = text.toLowerCase();
  const hasSignal = TOPIC_WORDS.some(w => t.includes(w)) || /\d/.test(t);
  if (OFFTOPIC.some(re => re.test(text))) return true;
  return !hasSignal;
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

    // Per-IP limit. Declared in wrangler.toml; if the binding is missing the
    // proxy still works, it is just Gemini's own quota doing the limiting.
    if (env.RATE_LIMIT) {
      const ip = request.headers.get('cf-connecting-ip') || 'anon';
      const { success } = await env.RATE_LIMIT.limit({ key: ip });
      if (!success) return json({ error: 'rate limited, try again shortly' }, 429, headers);
    }

    if (!env.GEMINI_API_KEY) return json({ error: 'proxy not configured' }, 500, headers);

    // {"models":true} lists what this key can actually reach. Model ids move
    // between releases and a 404 from generateContent does not say which part
    // of the path was wrong.
    if (body.models === true) {
      const r = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models?key=${env.GEMINI_API_KEY}&pageSize=200`);
      const j = await r.json().catch(() => ({}));
      return json({ status: r.status,
                    models: (j.models || [])
                      .filter(m => (m.supportedGenerationMethods || []).includes('generateContent'))
                      .map(m => m.name.replace('models/', '')) }, 200, headers);
    }

    const upstream = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${
        env.MODEL || MODEL}:generateContent?key=${env.GEMINI_API_KEY}`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          systemInstruction: { parts: [{ text: SYS }] },
          contents: [{ role: 'user', parts: [{ text }] }],
          generationConfig: { temperature: 0.4, maxOutputTokens: 600 },
        }),
      });

    if (!upstream.ok) {
      const detail = await upstream.text();
      // Surface enough to diagnose, but scrub anything key-shaped first: the
      // upstream body is not trusted to be free of it.
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
    // Return only the fields the page uses.
    return json({
      on_topic: parsed.on_topic !== false,
      criteria: parsed.criteria || {},
      intro: typeof parsed.intro === 'string' ? parsed.intro.slice(0, 300) : '',
    }, 200, headers);
  },
};
