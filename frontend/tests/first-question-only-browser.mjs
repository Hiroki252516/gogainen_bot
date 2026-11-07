// Disposable acceptance fixtures only; never point this at a study deployment.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

assert.equal(process.env.Q1_VERIFY_ISOLATED, "1");
const base = new URL(process.env.Q1_UI_BASE_URL);
assert(["127.0.0.1", "localhost"].includes(base.hostname) && base.port === "13860");
const { chromium } = await import(process.env.Q1_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true });
const admin = await browser.newContext();
const ui = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await ui.newPage();
page.setDefaultTimeout(20000);
const participants = [];
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const screenshotDir = process.env.Q1_SCREENSHOT_DIR;
if (screenshotDir) await mkdir(screenshotDir, { recursive: true });
async function api(path, method = "GET", data) {
  const response = await admin.request.fetch(new URL(path, base).href, {
    method, headers: { "Idempotency-Key": crypto.randomUUID() },
    ...(data === undefined ? {} : { data }), timeout: 240000,
  });
  assert(response.ok(), path + ": " + response.status() + " " + await response.text());
  return response.json();
}
async function register() {
  const record = await api("/api/registrations", "POST", {
    assignment_code: "A", consent_checked: true, student_number: "Q1-BROWSER-SYNTHETIC-" + Date.now(),
  });
  participants.push(record.participant_id);
  return record;
}
try {
  await api("/api/admin/auth/login", "POST", { password: "abc" });
  const status = await api("/api/admin/ai/status");
  assert.equal(status.ai_backend, process.env.Q1_EXPECT_BACKEND ?? "mock");
  const disabledSetting = await admin.request.fetch(new URL("/api/admin/first-question-only", base).href, {
    method: "PUT", data: { enabled: false }, timeout: 20000,
  });
  assert.equal(disabledSetting.status(), 409, "V6 must reject turning off its Q1-only condition");
  await api("/api/admin/option-order", "PUT", { mode: "debug_fixed" });
  await api("/api/admin/question-review-display", "PUT", { enabled: true });
  await api("/api/admin/pretest-result-display", "PUT", { enabled: false });
  await page.goto(new URL("/admin", base).href);
  await page.getByLabel("パスワード", { exact: true }).fill("abc");
  await page.getByRole("button", { name: "管理画面を開く", exact: true }).click();
  const toggle = page.getByRole("switch", { name: "設問1のみ出題", exact: true });
  await toggle.waitFor();
  assert.equal(await toggle.isChecked(), true);
  assert.equal(await toggle.isDisabled(), true, "V6 Q1-only setting is fixed in the admin screen");
  const record = await register();
  if (screenshotDir) await toggle.locator("../..").screenshot({ path: screenshotDir + "/admin-q1-switch.png" });
  const questions = (await api("/api/experiment/" + record.participant_id + "/pretest")).questions;
  assert.equal(questions.length, 3, "V6 serves question 1 only for each term");
  await page.evaluate((record) => {
    localStorage.setItem("participant_id", record.participant_id);
    localStorage.setItem("display_code", record.display_code);
  }, record);
  await page.goto(new URL("/pretest", base).href);
  for (let index = 0; index < 3; index++) {
    await page.getByLabel(`${index + 1} / 3`, { exact: true }).waitFor();
    await page.getByRole("region", { name: "設問1", exact: true }).waitFor();
    assert.equal(await page.locator(".term-page-question").count(), 1);
    assert.equal(await page.getByRole("region", { name: "設問2", exact: true }).count(), 0);
    if (index === 0 && screenshotDir) {
      await page.screenshot({ path: screenshotDir + "/q1-desktop.png", fullPage: true });
      await page.setViewportSize({ width: 390, height: 1000 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
      await page.screenshot({ path: screenshotDir + "/q1-mobile.png", fullPage: true });
      await page.setViewportSize({ width: 1440, height: 1000 });
    }
    await page.getByRole("radio").nth(index === 0 ? 5 : 0).check();
    await page.getByRole("button", { name: index === 2 ? "完了" : "次へ", exact: true }).click();
    const continued = page.getByRole("button", { name: index === 2 ? "テストを完了" : "次の用語へ", exact: true });
    await continued.waitFor();
    assert.equal(await page.locator(".term-page-question").count(), 1);
    assert.equal(await page.getByRole("radio", { checked: true }).count(), 1);
    await continued.click();
  }
  await page.waitForURL(/\/learning\/llm_knowledge|\/learning-targets/, { timeout: 240000 });
  if (page.url().endsWith("/learning-targets")) {
    await page.getByRole("link", { name: "学習を開始", exact: true }).click();
  }
  await page.getByRole("heading", { name: "教材", exact: true }).waitFor({ timeout: 240000 });
  assert.equal(await page.locator(".problem-block input[type=radio]").count(), 6);
  const logs = await api("/api/admin/participants/" + record.participant_id + "/logs");
  assert.equal(logs.participant.first_question_only, true);
  assert(logs.tutor_sessions.length > 0);
  if (status.ai_backend !== "mock") {
    assert(logs.ai_call_logs.some((call) => call.status === "success"), "the real AI call must succeed");
  }
  if (screenshotDir) await page.screenshot({ path: screenshotDir + "/q1-learning.png", fullPage: true });
  assert.deepEqual(errors, []);
  console.log("V6 fixed Q1-only admin state, desktop/mobile test, answer review and learning passed (" + status.ai_backend + ")");
} finally {
  for (const id of participants) await api("/api/admin/participants/" + id, "DELETE").catch(() => {});
  await browser.close();
}
