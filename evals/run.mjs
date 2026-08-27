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
                  "claimsCheckOut", "factsFor", "offTopic", "carryOver", "modelHtml"]) {
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
    } else if (c.kind === "modelhtml") {
      got = w.modelHtml(c.input);
      ok = got === c.expect;
    } else if (c.kind === "refuse") {
      got = w.offTopic(c.input, w.parseRequest(c.input));
      ok = got === c.expect;
    } else if (c.kind === "follow") {
      // Replay the turns the way handle() does: parse this one, merge it into
      // what the last one settled on, then decide whether to refuse. `offered`
      // supplies the suburbs each turn came back with, so a case about "dearer"
      // does not also depend on the scorer picking the same three today.
      let last = null, refused = false, merged = null;
      c.turns.forEach((t, i) => {
        if (refused) return;
        const raw = w.parseRequest(t);
        merged = w.carryOver(t, raw, last).c;
        refused = w.offTopic(t, raw, merged, last);
        if (refused) return;
        last = { c: JSON.parse(JSON.stringify(merged)),
                 names: (c.offered || [])[i] || [], text: t };
      });
      const want = c.expect.criteria || {};
      // `true` in a case means "set to something", for values that depend on
      // the dataset — the floor for "dearer" is whatever those suburbs cost.
      const seen = Object.fromEntries(Object.keys(want).map((k) =>
        [k, want[k] === true ? !!merged[k] : merged[k]]));
      got = { refused, ...seen };
      ok = refused === c.expect.refused && eq(seen, want);
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
