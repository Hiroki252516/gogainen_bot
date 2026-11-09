import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(new URL("../lib/option-answer-display.ts", import.meta.url), "utf8");
const javascript = ts.transpile(source.replace(/export function/g, "function"), { target: ts.ScriptTarget.ES2022 }).replace(/^export \{\};?$/m, "");
const { optionAnswerClass, optionCorrectnessForReview } = vm.runInNewContext(
  `${javascript}; ({ optionAnswerClass, optionCorrectnessForReview })`,
  {},
);

assert.equal(optionAnswerClass(false, true), "");
assert.equal(optionAnswerClass(false, false), "");
assert.equal(optionAnswerClass(false, undefined), "");
assert.equal(optionAnswerClass(true, true), "option-answer-correct");
assert.equal(optionAnswerClass(true, false), "option-answer-incorrect");
assert.equal(optionAnswerClass(true, undefined), "option-answer-incorrect");
assert.equal(optionCorrectnessForReview("multiple", true, false), true);
assert.equal(optionCorrectnessForReview("multiple", false, false), false);
assert.equal(optionCorrectnessForReview("multiple", undefined, false), false);
assert.equal(optionCorrectnessForReview("single", true, false), false);

console.log("answer review classifies selected multiple-choice options individually and preserves single-choice results");
