// Synthetic responses belong only in a separate Mock database.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

const { LEARNING_VERIFY_ISOLATED, LEARNING_UI_BASE_URL, LEARNING_PLAYWRIGHT_MODULE, LEARNING_SCREENSHOT_DIR } = process.env;
assert.equal(LEARNING_VERIFY_ISOLATED, "1");
assert(LEARNING_UI_BASE_URL && LEARNING_PLAYWRIGHT_MODULE && LEARNING_SCREENSHOT_DIR);
const base = new URL(LEARNING_UI_BASE_URL);
assert(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname));
assert(base.port && base.port !== "3000", "Never use the study frontend.");
const { chromium } = await import(LEARNING_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, channel: "chrome" });
await mkdir(LEARNING_SCREENSHOT_DIR, { recursive: true });
const bodies = [
  "利用者の質問に応じて履修規程の該当箇所を検索し、質問と一緒にAIへ渡して回答を作らせる。",
  "「必要な手続き・提出期限・注意点」の順に説明するよう、AIへ渡すプロンプトに指示を加える。",
  "担当者が確認した質問と回答の例を学習用データにして、AIを追加訓練する。",
  "履修規程を一度AIへ渡せば、その内容がモデルの重みに保存され、以後は検索しなくてもよい。",
  "回答例を毎回の質問に加えれば、学習用データによる訓練をしなくてもモデルの重みを調整できる。",
  "回答の順番を指示する文章をプロンプトに加えることで、モデルの重みを更新する。",
  "回答例をRAGの検索対象に登録すれば、回答方法の追加訓練が完了する。",
  "履修規程の該当箇所を探すには、文書検索ではなくファインチューニングを使う。",
  "履修規程の本文をプロンプトに含めれば、プロンプト自体を文書の保存・検索先として使える。",
];
const questionBody = "大学の履修案内AIに、更新された履修規程を使わせたい。回答は「必要な手続き・提出期限・注意点」の順にそろえ、担当者が確認した質問と回答の例も改善に利用したい。\n\n担当者の対応として、適切なものを3つ選びなさい。";

async function api(request, path, method = "GET", data) {
  const response = await request.fetch(new URL(path, base).href, { method, ...(data ? { data } : {}) });
  assert(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}

try {
  for (const width of [1440, 390]) for (const group of ["A", "B"]) for (const layout of ["debug_fixed", "randomized"]) for (const role of ["unknown", "M1", "M3"]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    assert.equal((await api(page.request, "/api/admin/ai/status")).ai_backend, "mock");
    await api(page.request, "/api/admin/question-set", "PUT", { mode: "standard" });
    await api(page.request, "/api/admin/option-order", "PUT", { mode: layout });
    const created = await api(page.request, "/api/registrations", "POST", { assignment_code: group, consent_checked: true, student_number: "LEARNING-BROWSER-SYNTHETIC" });
    const questions = (await api(page.request, `/api/experiment/${created.participant_id}/pretest`)).questions;
    const pretestLabels = role === "unknown" ? "J" : role === "M1" ? "DEF" : "GHI";
    // Get the source option bodies from a separate debug-fixed participant, not from public correctness metadata.
    await api(page.request, "/api/admin/option-order", "PUT", { mode: "debug_fixed" });
    const reference = await api(page.request, "/api/registrations", "POST", { assignment_code: group, consent_checked: true, student_number: "LEARNING-BROWSER-REFERENCE" });
    const canonical = (await api(page.request, `/api/experiment/${reference.participant_id}/pretest`)).questions;
    for (const [index, question] of questions.entries()) {
      const labels = question.term_slug === "llm_knowledge" ? pretestLabels : "ABC";
      const selectedBodies = canonical[index].options.filter((option) => labels.includes(option.label)).map((option) => option.body);
      await api(page.request, "/api/attempts", "POST", { participant_id: created.participant_id, question_id: question.question_id, selected_option_ids: question.options.filter((option) => selectedBodies.includes(option.body)).map((option) => option.option_id) });
    }
    await api(page.request, `/api/participants/${created.participant_id}/diagnose-pretest`, "POST", {});
    await page.addInitScript((record) => {
      localStorage.setItem("participant_id", record.participant_id);
      localStorage.setItem("display_code", record.display_code);
      localStorage.setItem("learning_targets", JSON.stringify(["llm_knowledge"]));
    }, created);
    const materialResponse = page.waitForResponse((response) => /\/api\/tutor-sessions\/[^/]+\/turns$/.test(response.url()));
    await page.goto(new URL("/learning/llm_knowledge", base).href);
    const material = await (await materialResponse).json();
    const question = material.practice_question;
    assert.equal(question.body, questionBody);
    assert.deepEqual(question.options.map((option) => option.body).sort(), [...bodies, "わからない。"].sort());
    for (const option of question.options) assert.deepEqual(Object.keys(option).sort(), ["body", "exclusive", "label", "option_id"]);
    await page.getByText(questionBody, { exact: true }).waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const unknown = page.getByRole("checkbox", { name: /^J\./ });
    await unknown.check();
    assert.equal(await page.getByRole("checkbox", { checked: true }).count(), 1);
    await unknown.uncheck();
    const responseRole = role === "M3" ? "correct" : role === "M1" ? "unknown" : "mixed";
    const selectedBodies = responseRole === "correct" ? bodies.slice(0, 3) : responseRole === "unknown" ? ["わからない。"] : [bodies[0], bodies[3], bodies[6]];
    for (const option of question.options.filter((option) => selectedBodies.includes(option.body))) {
      await page.getByRole("checkbox", { name: `${option.label}. ${option.body}`, exact: true }).check();
    }
    const feedbackResponse = page.waitForResponse((response) => /\/api\/tutor-turns\/[^/]+\/respond$/.test(response.url()));
    await page.getByRole("button", { name: "回答を確認", exact: true }).click();
    await feedbackResponse;
    await page.getByText(responseRole === "correct" ? "正解です。" : "不正解です。", { exact: true }).waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: `${LEARNING_SCREENSHOT_DIR}/${width}-${group}-${layout}-${role}.png`, fullPage: true });
    if (responseRole !== "correct") {
      await page.getByRole("button", { name: "次の確認へ", exact: true }).click();
      await page.getByRole("button", { name: "回答を確認", exact: true }).waitFor();
      assert.equal(await page.getByText(questionBody, { exact: true }).count(), 1);
      assert.equal(await page.getByRole("checkbox").count(), 10);
    }
    console.log(`ok ${width}px ${group} ${layout} ${role} -> ${responseRole}`);
    await context.close();
  }
} finally {
  await browser.close();
}
