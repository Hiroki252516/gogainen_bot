import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(new URL("../lib/learning-question-display.ts", import.meta.url), "utf8");
const javascript = ts.transpile(source.replace("export function", "function"), { target: ts.ScriptTarget.ES2022 }).replace(/^export \{\};?$/m, "");
const prepare = vm.runInNewContext(`${javascript}; prepareGroupedQuestionDisplay`, {});
const normalize = (value) => JSON.parse(JSON.stringify(value));

const scenario = "場面の1段落目。\n\n場面の2段落目。";
const question1 = `${scenario}\n\n設問1：タイトル1\n\n問い1。`;
const question2 = `${scenario}\n\n設問2：タイトル2\n\n問い2。`;
const options = [{ option_id: "correct", body: "選択肢" }];
const questions = [
  { question_id: "q1", body: question1, options },
  { question_id: "q2", body: question2, options },
];
const original = structuredClone(questions);

assert.deepEqual(normalize(prepare(questions)), {
  sharedScenario: scenario,
  questionBodies: ["設問1：タイトル1\n\n問い1。", "設問2：タイトル2\n\n問い2。"],
});
assert.deepEqual(questions, original, "display preparation must not mutate saved question data");
assert.equal(prepare([questions[0]]).sharedScenario, null);
assert.deepEqual(normalize(prepare([questions[1]]).questionBodies), [question2], "a lone second question keeps its original number and body");

const differentScenario = { ...questions[1], body: `別の場面。\n\n設問2：タイトル2\n\n問い2。` };
assert.deepEqual(normalize(prepare([questions[0], differentScenario])), {
  sharedScenario: null,
  questionBodies: [question1, differentScenario.body],
});

for (const invalidBodies of [
  [question1, "設問2：タイトル2\n\n問い2。"],
  [question1, `${scenario}\n\n問題2：タイトル2\n\n問い2。`],
  [question1, `${scenario}\n\n設問1：タイトル2\n\n問い2。`],
]) {
  const result = normalize(prepare(invalidBodies.map((body, index) => ({ body, question_id: `q${index}` }))));
  assert.equal(result.sharedScenario, null);
  assert.deepEqual(result.questionBodies, invalidBodies, "unrecognized boundaries must preserve all original text");
}

assert.deepEqual(normalize(prepare([])), { sharedScenario: null, questionBodies: [] });
assert.equal(prepare(null), null, "a missing practice question must not throw during grouped display preparation");
assert.equal(prepare(undefined), null, "an omitted practice question must not throw during grouped display preparation");
console.log("grouped confirmation display preserves source data and only deduplicates matching scenarios");
