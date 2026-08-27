import { runDatasetAgent, type ConversationTurn } from "./agent";
import { cleanDataset } from "./dataset";

const MAX_BODY_BYTES = 750_000;
const MAX_TEXT_CHARS = 1_200;
const MAX_CONTEXT_CHARS = 2_400;
const MAX_HISTORY_TURNS = 8;

const PROPERTY_WORDS = [
  "房", "屋", "住", "买", "購", "租", "预算", "預算", "地段", "区", "區", "郊区", "通勤",
  "投资", "回报", "公寓", "地块", "房价", "估价", "奥克兰", "奧克蘭", "数据", "比较", "推荐",
  "suburb", "house", "home", "apartment", "property", "buy", "rent", "budget", "yield", "invest",
  "auckland", "area", "commute", "section", "land", "bedroom", "value", "price", "dataset", "compare",
];
const EXPLICIT_OFF_TOPIC = [
  /写(一?[首篇段]|个|下).*(诗|故事|代码|程序|作文|歌词)|翻译|食谱|菜谱|笑话|简历/,
  /\b(write|translate|code|program|debug|script|poem|story|joke|recipe|essay|resume)\b/i,
  /python|javascript|typescript|sql|正则|regex|天气|新闻|股票|怎么做菜/i,
];

function cors(origin: string | null, allowed: string): HeadersInit {
  const allowList = allowed.split(",").map((item) => item.trim()).filter(Boolean);
  const ok = allowed === "*" || Boolean(origin && allowList.includes(origin));
  return {
    "access-control-allow-origin": ok ? (origin ?? "*") : "null",
    "access-control-allow-headers": "content-type",
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-max-age": "86400",
    vary: "Origin",
  };
}

function json(body: unknown, status: number, headers: HeadersInit): Response {
  return Response.json(body, { status, headers });
}

async function readBoundedJson(request: Request): Promise<Record<string, unknown>> {
  const contentLength = Number(request.headers.get("content-length") ?? 0);
  if (contentLength > MAX_BODY_BYTES) throw new Error("request too large");
  const reader = request.body?.getReader();
  if (!reader) throw new Error("empty body");
  const decoder = new TextDecoder();
  let size = 0;
  let raw = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY_BYTES) {
      await reader.cancel();
      throw new Error("request too large");
    }
    raw += decoder.decode(value, { stream: true });
  }
  raw += decoder.decode();
  const parsed: unknown = JSON.parse(raw);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("bad json");
  return parsed as Record<string, unknown>;
}

function cleanText(value: unknown, max: number): string {
  return typeof value === "string" ? value.trim().slice(0, max) : "";
}

function cleanHistory(value: unknown): ConversationTurn[] {
  if (!Array.isArray(value)) return [];
  return value.slice(-MAX_HISTORY_TURNS).flatMap((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const turn = item as Record<string, unknown>;
    if (turn.role !== "user" && turn.role !== "assistant") return [];
    const content = cleanText(turn.content, 800);
    return content ? [{ role: turn.role, content }] : [];
  });
}

function isObviouslyOffTopic(text: string): boolean {
  const lower = text.toLocaleLowerCase("zh-CN");
  const hasPropertySignal = PROPERTY_WORDS.some((word) => lower.includes(word)) || /\$|\d/.test(lower);
  return !hasPropertySignal && EXPLICIT_OFF_TOPIC.some((pattern) => pattern.test(text));
}

function safeError(error: unknown): string {
  const message = error instanceof Error ? error.message : "unknown error";
  return message
    .replace(/AIza[0-9A-Za-z_-]{10,}/g, "[redacted]")
    .replace(/key=[^&\s]+/gi, "key=[redacted]")
    .slice(0, 300);
}

export default {
  async fetch(request, env): Promise<Response> {
    const origin = request.headers.get("origin");
    const headers = cors(origin, env.ALLOWED_ORIGIN || "*");
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers });
    if (request.method !== "POST") return json({ error: "POST only" }, 405, headers);
    if ((headers as Record<string, string>)["access-control-allow-origin"] === "null") {
      return json({ error: "origin not allowed" }, 403, headers);
    }

    let body: Record<string, unknown>;
    try {
      body = await readBoundedJson(request);
    } catch (error) {
      return json({ error: safeError(error) }, 400, headers);
    }
    const text = cleanText(body.text, MAX_TEXT_CHARS);
    const context = cleanText(body.context, MAX_CONTEXT_CHARS);
    if (!text) return json({ error: "empty request" }, 400, headers);
    if (isObviouslyOffTopic(text)) {
      return json({ on_topic: false, answer: "这个问题超出了本项目的奥克兰住宅数据范围。", picks: [] }, 200, headers);
    }

    const ip = request.headers.get("cf-connecting-ip") ?? "anonymous";
    const { success } = await env.RATE_LIMIT.limit({ key: ip });
    if (!success) return json({ error: "rate limited, try again shortly" }, 429, headers);
    if (!env.GEMINI_API_KEY) return json({ error: "proxy not configured" }, 500, headers);

    const dataset = cleanDataset(body);
    if (!dataset.rows.length) return json({ error: "no project data supplied" }, 400, headers);

    const started = Date.now();
    try {
      const result = await runDatasetAgent(env, dataset, {
        text,
        context,
        history: cleanHistory(body.history),
      });
      console.log(JSON.stringify({ event: "agent.complete", rows: dataset.rows.length,
        picks: result.picks.length, evidence: result.evidence.length, ms: Date.now() - started }));
      return json(result, 200, headers);
    } catch (error) {
      console.error(JSON.stringify({ event: "agent.error", error: safeError(error), ms: Date.now() - started }));
      return json({ error: "grounded model response unavailable" }, 502, headers);
    }
  },
} satisfies ExportedHandler<Env>;
