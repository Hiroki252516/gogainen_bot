import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(new URL("../lib/test-term-pages.ts", import.meta.url), "utf8");
const javascript = ts.transpile(source, { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS });
const exports = {};
vm.runInNewContext(javascript, { exports });
const { groupTestQuestionsByTerm, combineTestGlossaries, initialTestTermPageIndex } = exports;
const normalize = (value) => JSON.parse(JSON.stringify(value));

const questions = ["llm_knowledge", "multi_agent", "memory_process"].flatMap((term_slug, term_index) => [1, 2].map((number) => ({
  question_id: `${term_slug}-${number}`,
  term_slug,
  term_label: term_slug,
  test_round: "test",
  answer_status: term_index === 0 && number === 1 ? "submitted" : "unanswered",
  submitted_answer: term_index === 0 && number === 1 ? { selected_option_ids: ["chosen"] } : null,
  glossary: {
    version: "fixture-v1",
    entries: [
      { id: "shared", term: "共通", definition: "共通の補足" },
      { id: `${term_slug}-${number}`, term: `${term_slug}-${number}`, definition: "個別の補足" },
    ],
  },
})));
const original = structuredClone(questions);
const pages = groupTestQuestionsByTerm(questions);

assert.equal(pages.length, 3);
assert.deepEqual(normalize(pages.map((page) => page.questions.map((question) => question.question_id))), [
  ["llm_knowledge-1", "llm_knowledge-2"],
  ["multi_agent-1", "multi_agent-2"],
  ["memory_process-1", "memory_process-2"],
]);
assert.equal(initialTestTermPageIndex(pages), 0, "a partially completed page must be resumed");
assert.deepEqual(normalize(combineTestGlossaries(pages[0].questions).entries.map((entry) => entry.id)), ["shared", "llm_knowledge-1", "llm_knowledge-2"]);
assert.deepEqual(questions, original, "grouping and glossary merging must not mutate API data");

const completePages = groupTestQuestionsByTerm(questions.map((question) => ({ ...question, answer_status: "submitted" })));
assert.equal(initialTestTermPageIndex(completePages), 2, "all-saved pages resume at the final page to retry completion");
assert.equal(groupTestQuestionsByTerm(questions.slice(0, 5)), null, "incomplete term pages are rejected");
assert.equal(groupTestQuestionsByTerm(questions.map((question, index) => index === 1 ? { ...question, test_round: "retest_1" } : question)), null);

console.log("term-page grouping, resumption, and glossary deduplication passed");
