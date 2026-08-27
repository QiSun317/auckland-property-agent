import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

const origin = "https://qisun317.github.io";

describe("worker boundary", () => {
  it("answers preflight", async () => {
    const response = await SELF.fetch("https://worker.test/", {
      method: "OPTIONS",
      headers: { origin },
    });
    expect(response.status).toBe(204);
    expect(response.headers.get("access-control-allow-origin")).toBe(origin);
  });

  it("rejects an empty request before calling the model", async () => {
    const response = await SELF.fetch("https://worker.test/", {
      method: "POST",
      headers: { origin, "content-type": "application/json" },
      body: JSON.stringify({ text: "" }),
    });
    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toMatchObject({ error: "empty request" });
  });

  it("declines an obvious unrelated request without calling the model", async () => {
    const response = await SELF.fetch("https://worker.test/", {
      method: "POST",
      headers: { origin, "content-type": "application/json" },
      body: JSON.stringify({ text: "请写一首诗" }),
    });
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({ on_topic: false, picks: [] });
  });

  it("enforces the configured browser origin", async () => {
    const response = await SELF.fetch("https://worker.test/", {
      method: "POST",
      headers: { origin: "https://example.com", "content-type": "application/json" },
      body: JSON.stringify({ text: "奥克兰房价" }),
    });
    expect(response.status).toBe(403);
  });
});
