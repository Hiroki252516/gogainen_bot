import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(new URL("../lib/test-term-pages.ts", import.meta.url), "utf8");
const javascript = ts.transpile(source, { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS });
const exports = {};
vm.runInNewContext(javascript, { exports });
const { groupTestQuestionsByTerm, combineTestGlossaries, initialTestTermPageIndex, normalizeTestRound, sameTestRound } = exports;
const normalize = (value) => JSON.parse(JSON.stringify(value));

const pendingRound = JSON.parse(JSON.stringify({ test_round: normalizeTestRound(null) })).test_round;
assert.equal(pendingRound, "", "page submissions serialize a missing test round as an empty string");
assert.equal(sameTestRound(pendingRound, null), true, "a pending submission must match its null-round page after reload");
assert.equal(sameTestRound(null, ""), true, "null and empty test rounds share the same normalized identity");
assert.equal(sameTestRound("retest_1", null), false, "a pending submission for another test round must not be restored");

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
const q1Questions = questions.filter((question) => question.question_id.endsWith("-1"));
const q1Pages = groupTestQuestionsByTerm(q1Questions);
assert.equal(q1Pages.length, 3);
assert.ok(q1Pages.every((page) => page.questions.length === 1));
assert.equal(initialTestTermPageIndex(q1Pages), 1, "Q1-only pages resume at the next unsaved term");
assert.equal(groupTestQuestionsByTerm([...q1Questions, questions[1]]), null, "mixed page widths are rejected");
assert.equal(groupTestQuestionsByTerm(q1Questions.map((question, index) => index === 1 ? { ...question, test_round: "retest_1" } : question)), null);
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

const runnerSource = fs.readFileSync(new URL("../components/QuestionRunner.tsx", import.meta.url), "utf8");
const validatorSource = runnerSource.slice(runnerSource.indexOf("function isPageSubmissionFor("), runnerSource.indexOf("function TermPageQuestionRunner("));
const validate = vm.runInNewContext(ts.transpile(validatorSource + "; isPageSubmissionFor", { target: ts.ScriptTarget.ES2022 }), { sameTestRound });
for (const page of [pages[0], q1Pages[0]]) {
  const saved = {
    participant_id: "p", phase: "pretest", term_slug: page.term_slug, test_round: "test",
    page_id: "frozen-page", question_shown_at: "2026-11-03T00:00:00Z", answered_at: "2026-11-03T00:00:01Z",
    elapsed_time_sec: 1, answers: page.questions.map((question) => ({ question_id: question.question_id, selected_option_ids: ["chosen"] })),
  };
  assert.equal(validate(saved, "p", "pretest", page), true, "both page widths restore pending submissions");
  assert.equal(validate({ ...saved, answers: [] }, "p", "pretest", page), false);
  assert.equal(validate({ ...saved, answers: [...saved.answers, saved.answers[0]] }, "p", "pretest", page), false);
  assert.equal(validate({ ...saved, answers: [{ question_id: "outside-page", selected_option_ids: ["chosen"] }] }, "p", "pretest", page), false);
}
console.log("term-page grouping, pending submission restoration, and glossary deduplication passed");
