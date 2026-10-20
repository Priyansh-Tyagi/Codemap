import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";

// These files are deployed as-is; nothing else checks them, and a stale CSP
// hash silently blocks the theme script (flash of wrong theme) in production only.
const root = resolve(__dirname, "..");
const read = (p) => readFileSync(resolve(root, p), "utf8");

const html = read("index.html");
const vercel = JSON.parse(read("vercel.json"));
const netlify = read("public/_headers");

const vercelHeaders = Object.fromEntries(vercel.headers[0].headers.map((h) => [h.key, h.value]));
const csp = vercelHeaders["Content-Security-Policy"];

describe("deployment security headers", () => {
  it("the CSP allows the inline theme script by its exact hash", () => {
    const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
    const hash = createHash("sha256").update(script).digest("base64");
    expect(csp).toContain(`'sha256-${hash}'`);
  });

  it("index.html has no other inline script the CSP would block", () => {
    const inline = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>/g)];
    expect(inline).toHaveLength(1);
  });

  it("never allows unsafe-inline or unsafe-eval for scripts", () => {
    const scriptSrc = csp.split(";").find((d) => d.trim().startsWith("script-src"));
    expect(scriptSrc).not.toMatch(/unsafe-inline|unsafe-eval/);
  });

  it("forbids framing, plugins and base-tag tricks", () => {
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(vercelHeaders["X-Frame-Options"]).toBe("DENY");
    expect(vercelHeaders["X-Content-Type-Options"]).toBe("nosniff");
  });

  it("Netlify's _headers carries exactly the same headers as vercel.json", () => {
    for (const [key, value] of Object.entries(vercelHeaders)) {
      expect(netlify).toContain(`  ${key}: ${value}`);
    }
  });

  it("the SPA rewrite is still in place alongside the headers", () => {
    expect(vercel.rewrites).toEqual([{ source: "/(.*)", destination: "/index.html" }]);
  });
});
