import assert from "node:assert/strict";
import fs from "node:fs/promises";
import ts from "typescript";

const source = await fs.readFile(new URL("../lib/api.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { api } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const events = [];
globalThis.window = { dispatchEvent: (event) => { events.push(event.type); return true; } };
globalThis.fetch = async () => new Response(JSON.stringify({ detail: "expired" }), { status: 401 });

for (const path of [
  "/api/admin/participants", "/api/admin/logs/overview?mode=all", "/api/seed",
  "/api/admin/learning-material-glossary-mode",
  "/api/seed/?x=1", "/api/participants/123/evaluation-summary/recalculate",
  "/api/participants/123/evaluation-summary/recalculate/?x=1",
]) {
  events.length = 0;
  await assert.rejects(api(path), (error) => error.status === 401);
  assert.deepEqual(events, ["admin-auth-required"], path);
}
for (const path of ["/api/admin/auth/login", "/api/admin/auth/logout", "/api/participants/123/current-step"]) {
  events.length = 0;
  await assert.rejects(api(path), (error) => error.status === 401);
  assert.deepEqual(events, [], path);
}
console.log("admin 401 paths passed");
