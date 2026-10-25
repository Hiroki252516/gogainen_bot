// Use an isolated Mock backend only; never submit synthetic responses to the study instance.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

const { PRETEST_VERIFY_ISOLATED, PRETEST_UI_BASE_URL, PRETEST_PLAYWRIGHT_MODULE, PRETEST_SCREENSHOT_DIR } = process.env;
assert.equal(PRETEST_VERIFY_ISOLATED, "1");
assert(PRETEST_UI_BASE_URL && PRETEST_PLAYWRIGHT_MODULE && PRETEST_SCREENSHOT_DIR);
const base = new URL(PRETEST_UI_BASE_URL);
assert(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname));
assert(base.port && base.port !== "3000", "Do not use the study frontend.");
const { chromium } = await import(PRETEST_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, channel: "chrome" });
await mkdir(PRETEST_SCREENSHOT_DIR, { recursive: true });

async function api(request, path, method = "GET", data) {
  const response = await request.fetch(new URL(path, base).href, { method, ...(data ? { data } : {}) });
  assert(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}

async function create(request, mode, layout) {
  await api(request, "/api/admin/question-set", "PUT", { mode });
  await api(request, "/api/admin/option-order", "PUT", { mode: layout });
  return api(request, "/api/registrations", "POST", {
    assignment_code: "A", consent_checked: true, student_number: "PRETEST-BROWSER-SYNTHETIC",
  });
}

try {
  for (const width of [1440, 390]) for (const mode of ["standard", "easy"]) for (const layout of ["debug_fixed", "randomized"]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    assert.equal((await api(page.request, "/api/admin/ai/status")).ai_backend, "mock");
    const reference = await create(page.request, mode, "debug_fixed");
    const canonical = (await api(page.request, `/api/experiment/${reference.participant_id}/pretest`)).questions;
    if (mode === "standard") {
      assert.deepEqual(canonical[0].options.slice(0, 2).map((option) => option.body), [
        "利用者の質問に応じて最新の取扱説明書を検索し、該当箇所を質問と一緒にAIへ渡して回答を作らせる仕組みを実装する。",
        "利用者からの質問に回答するとき、「結論・操作手順・注意点」の順に説明するよう、AIに指示するプロンプトを設定する。",
      ]);
    }
    const record = await create(page.request, mode, layout);
    const questions = (await api(page.request, `/api/experiment/${record.participant_id}/pretest`)).questions;
    await page.addInitScript((created) => {
      localStorage.setItem("participant_id", created.participant_id);
      localStorage.setItem("display_code", created.display_code);
    }, record);
    await page.goto(new URL("/pretest", base).href);
    for (const [index, question] of questions.entries()) {
      await page.getByText(question.body, { exact: true }).waitFor();
      assert.equal(await page.getByRole("checkbox").count(), 10);
      assert.equal(await page.locator(".learning-glossary").count(), 0);
      for (const option of question.options) {
        assert.deepEqual(Object.keys(option).sort(), ["body", "exclusive", "label", "option_id"]);
        assert(await page.getByRole("checkbox", { name: `${option.label}. ${option.body}`, exact: true }).isVisible());
      }
      const geometry = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > innerWidth,
        badText: Array.from(document.querySelectorAll(".option > span")).some((span) => span.scrollWidth > span.clientWidth + 1),
        overlap: Array.from(document.querySelectorAll(".option")).some((label) => label.querySelector("input").getBoundingClientRect().right > label.querySelector("span").getBoundingClientRect().left + 1),
      }));
      assert.deepEqual(geometry, { overflow: false, badText: false, overlap: false });
      const unknown = page.getByRole("checkbox", { name: /^J\./ });
      await unknown.check();
      assert.equal(await page.getByRole("checkbox", { checked: true }).count(), 1);
      assert.equal(await page.getByRole("checkbox", { disabled: true }).count(), 9);
      await unknown.uncheck();
      const correctBodies = canonical[index].options.filter((option) => ["A", "B", "C"].includes(option.label)).map((option) => option.body);
      for (const option of question.options.filter((option) => correctBodies.includes(option.body))) {
        await page.getByRole("checkbox", { name: `${option.label}. ${option.body}`, exact: true }).check();
      }
      assert.equal(await page.getByRole("checkbox", { checked: true }).count(), 3);
      await page.screenshot({ path: `${PRETEST_SCREENSHOT_DIR}/${width}-${mode}-${layout}-q${index + 1}.png`, fullPage: true });
      await page.getByRole("button", { name: index === 2 ? "完了" : "次へ", exact: true }).click();
    }
    await page.waitForURL((url) => url.pathname === "/learning-targets");
    const review = (await api(page.request, `/api/participants/${record.participant_id}/learning-targets`)).test_results;
    assert.equal(review.results.length, 3);
    assert(review.results.every((row) => row.is_correct === true));
    for (const [index, result] of review.results.entries()) {
      assert.equal(result.question_body, questions[index].body);
      for (const selected of result.selected_options) {
        assert(questions[index].options.some((option) => option.body === selected.body && option.label === selected.label));
      }
    }
    console.log(`ok ${width}px ${mode} ${layout}: all 3 questions, selection and saved review`);
    await context.close();
  }
} finally {
  await browser.close();
}
