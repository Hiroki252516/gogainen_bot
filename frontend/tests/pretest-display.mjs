import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const page = fs.readFileSync(new URL("../app/learning-targets/page.tsx", import.meta.url), "utf8");
const body = page.split(".then((data) => {")[1].split("\n      })\n      .catch")[0];
const javascript = ts.transpile(`(data: any) => {${body}}`, { target: ts.ScriptTarget.ES2022 });
const events = [];
const sandbox = { id: "participant", saveLearningTargets: (id, slugs) => events.push(["learning_targets", Array.from(slugs)]), router: { replace: (url) => events.push(["route", url]) } };
const handler = vm.runInNewContext(javascript, sandbox);
const data = { review_required: false, targets: [{ term_slug: "llm_knowledge" }, { term_slug: "multi_agent" }, { term_slug: "memory_process" }], next_url: "/learning/llm_knowledge" };
handler(data);
assert.equal(events[0][0], "learning_targets");
assert.deepEqual(events[0][1], data.targets.map(t => t.term_slug));
assert.deepEqual(events[1], ["route", data.next_url]);
for (const next_url of [undefined, "", "/learning-targets", "https://example.com", "//example.com", "/unknown"]) {
  events.length = 0;
  assert.throws(() => handler({ ...data, next_url }), /次の画面/);
  assert.equal(events.some(e => e[0] === "route"), false);
}
const diagnosing = fs.readFileSync(new URL("../app/diagnosing/page.tsx", import.meta.url), "utf8");
assert(diagnosing.indexOf('saveLearningTargets(participantId') < diagnosing.indexOf("setTimeout(() => router.replace"));
assert(diagnosing.includes("!targets && data.review_required === false"));
const cache = new Map();
const helper = ts.transpile(fs.readFileSync(new URL("../lib/learning-targets.ts", import.meta.url), "utf8").replace("export function", "function"), { target: ts.ScriptTarget.ES2022 });
const save = vm.runInNewContext(`${helper}; saveLearningTargets`, { localStorage: { getItem: key => cache.get(key) ?? null, setItem: (key, value) => cache.set(key, value) } });
save("one", ["llm_knowledge", "multi_agent", "memory_process"]);
save("one", ["multi_agent", "memory_process"], true);
assert.equal(JSON.parse(cache.get("learning_targets")).length, 3);
save("two", ["multi_agent"], true);
assert.deepEqual(JSON.parse(cache.get("learning_targets")), ["multi_agent"]);
cache.set("learning_targets", "broken");
save("two", ["memory_process"], true);
assert.deepEqual(JSON.parse(cache.get("learning_targets")), ["memory_process"]);
console.log("pretest cache ordering and invalid navigation guards passed");
