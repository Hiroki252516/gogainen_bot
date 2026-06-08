import fs from "node:fs";

const required = [
  "app/start/page.tsx",
  "app/pretest/page.tsx",
  "app/learning/[termSlug]/page.tsx",
  "app/admin/page.tsx",
  "components/QuestionRunner.tsx"
];

for (const file of required) {
  if (!fs.existsSync(new URL(`../${file}`, import.meta.url))) {
    throw new Error(`missing ${file}`);
  }
}

console.log("frontend smoke ok");


const learningPage = fs.readFileSync(new URL("../app/learning/[termSlug]/page.tsx", import.meta.url), "utf8");
if (learningPage.includes("{feedback ? <div className=\"notice\">{feedback.feedback}</div>")) {
  throw new Error("learning page must not show standalone feedback after submit");
}
if (!learningPage.includes("<strong>デバッグ</strong>")) {
  throw new Error("learning page must show debug panel in the normal participant view");
}
for (const expectedText of ["誤概念タイプ判定:", "learning_stage:", "teaching_strategy:"]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing debug text: ${expectedText}`);
  }
}
if (learningPage.includes("足場掛けレベル:")) {
  throw new Error("learning page must not show scaffolding level in stage-based UI");
}
if (learningPage.includes("ターン: {turn.turn_index}")) {
  throw new Error("learning page must not show fixed turn progress in stage-based UI");
}
for (const expectedText of ["対象概念:", "回答判定:", "教材フィードバック", "judgementLabel(feedback)"]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing final feedback/debug update behavior: ${expectedText}`);
  }
}
if (!learningPage.includes("learning_stage: data.next_learning_stage")) {
  throw new Error("learning page must update stage from next_learning_stage after response");
}
