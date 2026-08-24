// Run the agent's gates against evals/cases.jsonl and print JSON results.
//
// It loads the built heatmap.html into jsdom and calls the functions that
// actually shipped. Not a copy of them — a copy drifts, and a suite that
// passes against a copy of last month's logic is worse than no suite at all.
//
// The page's boot paints an SVG jsdom cannot lay out, so it throws on the last
// line. That is fine and expected: every function declaration is hoisted and
// every const the gates close over is already initialised by then. The throw is
// swallowed rather than ignored silently — if it ever moves earlier, the probe
// below fails loudly instead of reporting a suite that tested nothing.
//
// Lives beside its own package.json because ESM resolves packages from the
// file's directory and ignores NODE_PATH.
//
//   node evals/run.mjs heatmap.html evals/cases.jsonl
import { JSDOM, VirtualConsole } from "jsdom";
import { readFileSync } from "node:fs";

const [, , pagePath, casesPath] = process.argv;
const dom = new JSDOM(readFileSync(pagePath, "utf8"), {
  runScripts: "dangerously", pretendToBeVisual: true,
  url: "http://localhost/", virtualConsole: new VirtualConsole(),
});
const w = dom.window;
await new Promise((r) => setTimeout(r, 800));

for (const fn of ["parseRequest", "readIntent", "figuresCheckOut",
                  "claimsCheckOut", "factsFor", "offTopic"]) {
  if (typeof w[fn] !== "function") {
    console.error(`${fn} is not on the page — the harness is testing nothing`);
    process.exit(2);
  }
}

const cases = readFileSync(casesPath, "utf8").trim().split("\n").map(JSON.parse);
const results = [];

const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

for (const c of cases) {
  let got, ok;
  try {
    if (c.kind === "intent") {
      got = w.readIntent(c.input, w.parseRequest(c.input));
      ok = got === c.expect;
    } else if (c.kind === "parse") {
      const p = w.parseRequest(c.input);
      // Only the keys the case names — a case about zones should not fail
      // because an unrelated field gained a value.
      got = Object.fromEntries(Object.keys(c.expect).map((k) => [k, p[k]]));
      ok = eq(got, c.expect);
    } else if (c.kind === "figures") {
      const facts = w.factsFor(c.suburb);
      const text = c.text ?? c.template.replace("%s",
        Number(facts[c.field]).toLocaleString("en-NZ"));
      got = w.figuresCheckOut(text, facts);
      ok = got === c.expect;
    } else if (c.kind === "claims") {
      got = w.claimsCheckOut(c.text, c.suburb);
      ok = got === c.expect;
    } else if (c.kind === "refuse") {
      got = w.offTopic(c.input, w.parseRequest(c.input));
      ok = got === c.expect;
    } else {
      throw new Error(`unknown kind ${c.kind}`);
    }
  } catch (e) {
    got = `threw: ${e.message}`;
    ok = false;
  }
  results.push({ id: c.id, kind: c.kind, ok, got, expect: c.expect, why: c.why });
}

console.log(JSON.stringify({ page: pagePath, n: results.length, results }, null, 1));
process.exit(0);
