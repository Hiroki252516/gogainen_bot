import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(new URL("../lib/option-answer-display.ts", import.meta.url), "utf8");
const javascript = ts.transpile(source.replace("export function", "function"), { target: ts.ScriptTarget.ES2022 }).replace(/^export \{\};?$/m, "");
const optionAnswerClass = vm.runInNewContext(`${javascript}; optionAnswerClass`, {});

assert.equal(optionAnswerClass(false, true), "");
assert.equal(optionAnswerClass(false, false), "");
assert.equal(optionAnswerClass(false, undefined), "");
assert.equal(optionAnswerClass(true, true), "option-answer-correct");
assert.equal(optionAnswerClass(true, false), "option-answer-incorrect");
assert.equal(optionAnswerClass(true, undefined), "option-answer-incorrect");

console.log("learning answer colors are hidden before feedback and classify every option afterward");
