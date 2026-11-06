// Run only against an isolated Mock backend, never the study instance.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

if (process.env.GLOSSARY_VERIFY_ISOLATED !== "1" || !process.env.GLOSSARY_UI_BASE_URL || !process.env.GLOSSARY_PLAYWRIGHT_MODULE || !process.env.GLOSSARY_SCREENSHOT_DIR) {
  throw new Error("Set GLOSSARY_VERIFY_ISOLATED=1, GLOSSARY_UI_BASE_URL, GLOSSARY_PLAYWRIGHT_MODULE, and GLOSSARY_SCREENSHOT_DIR.");
}
const base = new URL(process.env.GLOSSARY_UI_BASE_URL);
assert(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname));
assert(base.port && base.port !== "3000", "Do not use the study frontend.");
const { chromium } = await import(process.env.GLOSSARY_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, ...(process.env.GLOSSARY_BROWSER_CHANNEL ? { channel: process.env.GLOSSARY_BROWSER_CHANNEL } : {}) });
await mkdir(process.env.GLOSSARY_SCREENSHOT_DIR, { recursive: true });

async function api(request, path, method = "GET", data) {
  const response = await request.fetch(new URL(path, base).href, { method, ...(data ? { data } : {}) });
  assert(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}

async function participant(request, group) {
  await api(request, "/api/admin/auth/login", "POST", { password: process.env.ADMIN_PASSWORD || "abc" });
  assert.equal((await api(request, "/api/admin/ai/status")).ai_backend, "mock");
  await api(request, "/api/admin/option-order", "PUT", { mode: "debug_fixed" });
  const created = await api(request, "/api/registrations", "POST", { assignment_code: group, consent_checked: true, student_number: "GLOSSARY-BROWSER-SYNTHETIC" });
  const pid = created.participant_id;
  const questions = (await api(request, `/api/experiment/${pid}/pretest`)).questions;
  for (const question of questions) {
    const labels = question.term_slug === "llm_knowledge" ? "DEF" : "ABC";
    await api(request, "/api/attempts", "POST", { participant_id: pid, question_id: question.question_id, selected_option_ids: question.options.filter((option) => labels.includes(option.label)).map((option) => option.option_id) });
  }
  await api(request, `/api/participants/${pid}/diagnose-pretest`, "POST", {});
  return created;
}

async function verifyNotes(page, label, expected) {
  const mobile = page.viewportSize().width < 1100 && label === "教材の用語の補足";
  if (mobile && expected.entries.length) await page.getByRole("button", { name: "用語の補足", exact: true }).click();
  const notes = page.getByRole("complementary", { name: label, exact: true });
  if (!expected.entries.length) {
    assert.equal(await notes.count(), 0);
    return;
  }
  assert(await notes.isVisible());
  assert.deepEqual(await notes.locator("dt").allTextContents(), expected.entries.map((entry) => entry.term));
  assert.deepEqual(await notes.locator("dd").allTextContents(), expected.entries.map((entry) => entry.definition));
  assert.equal(await page.locator(".problem-block .learning-glossary").count(), 0);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "horizontal overflow");
  if (mobile) await page.getByRole("button", { name: "閉じる", exact: true }).click();
}

try {
  for (const width of [1440, 390]) for (const group of ["A", "B"]) for (const correct of [false, true]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    page.setDefaultTimeout(30_000);
    const created = await participant(page.request, group);
    await page.addInitScript((record) => {
      localStorage.setItem("participant_id", record.participant_id);
      localStorage.setItem("display_code", record.display_code);
      localStorage.setItem("learning_targets", JSON.stringify(["llm_knowledge"]));
    }, created);
    const materialResponse = page.waitForResponse((response) => /\/api\/tutor-sessions\/[^/]+\/turns$/.test(response.url()));
    await page.goto(new URL("/learning/llm_knowledge", base).href);
    const material = await (await materialResponse).json();
    await verifyNotes(page, "教材の用語の補足", material.glossary);
    for (const label of correct ? "ABC" : "DEF") {
      await page.getByRole("checkbox", { name: new RegExp(`^${label}\\.`) }).check();
    }
    const feedbackResponse = page.waitForResponse((response) => /\/api\/tutor-turns\/[^/]+\/respond$/.test(response.url()));
    await page.getByRole("button", { name: "回答を確認", exact: true }).click();
    const feedback = await (await feedbackResponse).json();
    await page.getByText(correct ? "正解です。" : "不正解です。", { exact: true }).waitFor();
    await verifyNotes(page, "回答後解説の用語の補足", feedback.glossary);
    await page.screenshot({ path: `${process.env.GLOSSARY_SCREENSHOT_DIR}/${width}-${group}-${correct ? "correct" : "wrong"}.png`, fullPage: true });
    assert(await page.getByRole("button", { name: feedback.session_completed ? "次へ" : "次の確認へ", exact: true }).isEnabled());
    console.log(`ok ${width}px ${group} ${correct ? "correct" : "wrong"}`);
    await context.close();
  }

  // A response fixture exercises the no-matching-terms rendering without changing saved materials.
  const context = await browser.newContext({ viewport: { width: 390, height: 1000 } });
  const page = await context.newPage();
  const created = await participant(page.request, "B");
  await page.addInitScript((record) => localStorage.setItem("participant_id", record.participant_id), created);
  await page.route("**/api/tutor-sessions/*/turns", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({ response, json: { ...data, tutor_message: "## 読み物\n\n### 内容\n\n必要な情報を確かめて読み進めます。", glossary: { version: "learning-glossary-v4", entries: [] } } });
  });
  await page.goto(new URL("/learning/llm_knowledge", base).href);
  await page.getByRole("heading", { name: "読み物", exact: true }).waitFor();
  assert.equal(await page.locator(".learning-glossary").count(), 0);
  await page.screenshot({ path: `${process.env.GLOSSARY_SCREENSHOT_DIR}/390-empty.png`, fullPage: true });
  await context.close();
  console.log("ok empty glossary fixture");
} finally {
  await browser.close();
}
