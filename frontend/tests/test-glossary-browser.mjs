// Run only against an isolated Mock backend, never the study instance.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

if (process.env.GLOSSARY_VERIFY_ISOLATED !== "1" || !process.env.GLOSSARY_UI_BASE_URL || !process.env.GLOSSARY_PLAYWRIGHT_MODULE || !process.env.GLOSSARY_SCREENSHOT_DIR) throw new Error("Set the GLOSSARY_VERIFY_ISOLATED, GLOSSARY_UI_BASE_URL, GLOSSARY_PLAYWRIGHT_MODULE, and GLOSSARY_SCREENSHOT_DIR variables.");
const base = new URL(process.env.GLOSSARY_UI_BASE_URL);
assert(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname));
assert(base.port && base.port !== "3000", "Do not use the study frontend.");
const { chromium } = await import(process.env.GLOSSARY_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, ...(process.env.GLOSSARY_BROWSER_CHANNEL ? { channel: process.env.GLOSSARY_BROWSER_CHANNEL } : {}) });
await mkdir(process.env.GLOSSARY_SCREENSHOT_DIR, { recursive: true });
const excluded = new Set(["ai", "pretraining", "fine_tuning", "prompt_engineering", "rag", "database", "multi_agent", "task", "memory_process"]);
const correctPretests = new Map();
let views = 0;

async function api(request, path, method = "GET", data) {
  const response = await request.fetch(new URL(path, base).href, { method, ...(data ? { data } : {}) });
  assert(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}

async function create(request, mode, layout, group) {
  await api(request, "/api/admin/auth/login", "POST", { password: process.env.ADMIN_PASSWORD || "abc" });
  assert.equal((await api(request, "/api/admin/ai/status")).ai_backend, "mock");
  await api(request, "/api/admin/question-set", "PUT", { mode });
  await api(request, "/api/admin/option-order", "PUT", { mode: layout });
  return api(request, "/api/registrations", "POST", { assignment_code: group, consent_checked: true, student_number: "TEST-GLOSSARY-BROWSER-SYNTHETIC" });
}

async function verifyQuestion(page, question) {
  await page.locator(".question-heading strong").filter({ hasText: question.term_label }).waitFor();
  assert.deepEqual(await page.locator('.options input[type="checkbox"]').evaluateAll((inputs) => inputs.map((input) => input.value)), question.options.map((option) => option.option_id));
  const notes = page.getByRole("complementary", { name: "テストの用語の補足", exact: true });
  assert.equal(question.glossary.version, "learning-glossary-v2");
  for (const entry of question.glossary.entries) assert(!excluded.has(entry.id));
  if (question.glossary.entries.length) {
    await notes.waitFor();
    assert.deepEqual(await notes.locator("dt").allTextContents(), question.glossary.entries.map((entry) => entry.term));
    assert.deepEqual(await notes.locator("dd").allTextContents(), question.glossary.entries.map((entry) => entry.definition));
    assert(await page.evaluate(() => document.querySelector(".learning-glossary").getBoundingClientRect().top >= document.querySelector(".options").getBoundingClientRect().bottom), "glossary overlaps options");
  } else assert.equal(await notes.count(), 0);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "horizontal overflow");
  for (const option of question.options) assert.deepEqual(Object.keys(option).sort(), ["body", "exclusive", "label", "option_id"]);
  views++;
}

async function runTest(page, pid, phase, perfect, capture) {
  const endpoint = `/api/experiment/${pid}/${phase.replaceAll("_", "-")}`;
  const questions = (await api(page.request, endpoint)).questions;
  await page.goto(new URL(`/${phase.replaceAll("_", "-")}`, base).href);
  for (let index = 0; index < questions.length; index++) {
    const question = questions[index];
    await verifyQuestion(page, question);
    if (index === 0) {
      await page.reload();
      await verifyQuestion(page, question);
    }
    const selected = perfect ? correctPretests.get(question.question_id) : question.options.filter((option) => option.exclusive).map((option) => option.option_id);
    assert.equal(selected?.length, perfect ? 3 : 1);
    for (const optionId of selected) await page.locator(`input[value="${optionId}"]`).check();
    assert.deepEqual((await api(page.request, endpoint)).questions[index].glossary, question.glossary);
    if (capture && index === 0) await page.screenshot({ path: `${process.env.GLOSSARY_SCREENSHOT_DIR}/test-${page.viewportSize().width}-${phase}.png`, fullPage: true });
    const saved = page.waitForResponse((response) => response.url().endsWith("/api/attempts") && response.request().method() === "POST");
    await page.getByRole("button", { name: index === 2 ? "完了" : "次へ", exact: true }).click();
    assert((await saved).ok());
    if (index < 2) {
      const replay = (await api(page.request, endpoint)).questions[index];
      assert.equal(replay.answer_status, "submitted");
      assert.deepEqual(replay.glossary, question.glossary);
    }
  }
  await page.waitForURL(/\/learning-targets$/);
  await page.getByRole("heading", { name: /確認結果$/ }).waitFor();
  assert.equal(await page.locator(".learning-glossary").count(), 0);
}

try {
  const baseline = await browser.newContext();
  await api(baseline.request, "/api/admin/auth/login", "POST", { password: process.env.ADMIN_PASSWORD || "abc" });
  assert.equal((await api(baseline.request, "/api/admin/ai/status")).ai_backend, "mock");
  for (const mode of ["standard", "easy"]) {
    const record = await create(baseline.request, mode, "debug_fixed", "B");
    for (const question of (await api(baseline.request, `/api/experiment/${record.participant_id}/pretest`)).questions) correctPretests.set(question.question_id, question.options.filter((option) => "ABC".includes(option.label)).map((option) => option.option_id));
  }
  await baseline.close();
  for (const width of [1440, 390]) for (const mode of ["standard", "easy"]) for (const layout of ["debug_fixed", "randomized"]) for (const group of ["A", "B"]) for (const perfect of [false, true]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    page.setDefaultTimeout(30_000);
    const record = await create(page.request, mode, layout, group);
    await page.addInitScript((created) => {
      localStorage.setItem("participant_id", created.participant_id);
      localStorage.setItem("display_code", created.display_code);
    }, record);
    const capture = mode === "standard" && layout === "debug_fixed" && group === "A";
    const pid = record.participant_id;
    await runTest(page, pid, "pretest", perfect, capture);
    if (!perfect) await api(page.request, `/api/participants/${pid}/give-up-learning`, "POST", {});
    await runTest(page, pid, perfect ? "final_test" : "retest", false, capture);
    await api(page.request, `/api/participants/${pid}/give-up-learning`, "POST", {});
    await runTest(page, pid, "retest", false, capture);
    assert.equal((await api(page.request, `/api/participants/${pid}/current-step`)).step, "survey");
    const logs = await api(page.request, `/api/admin/participants/${pid}/logs`);
    assert.equal(logs.attempts.length, 9);
    assert(logs.attempts.every((attempt) => attempt.test_glossary.version === "learning-glossary-v2"));
    console.log(`ok ${width}px ${mode} ${layout} ${group} ${perfect ? "initial-perfect" : "normal"}`);
    await context.close();
  }
  const empty = await browser.newContext({ viewport: { width: 390, height: 1000 } });
  const page = await empty.newPage();
  const record = await create(page.request, "standard", "debug_fixed", "B");
  await page.addInitScript((created) => localStorage.setItem("participant_id", created.participant_id), record);
  await page.route("**/api/experiment/*/pretest", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.questions.forEach((question) => { question.glossary.entries = []; });
    await route.fulfill({ response, json: data });
  });
  await page.goto(new URL("/pretest", base).href);
  await page.locator(".options").waitFor();
  assert.equal(await page.locator(".learning-glossary").count(), 0);
  await empty.close();
  console.log(`ok ${views} question views and empty glossary fixture`);
} finally {
  await browser.close();
}
