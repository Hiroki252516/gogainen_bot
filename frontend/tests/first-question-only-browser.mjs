// Disposable acceptance fixtures only; never point this at a study deployment.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { newResearchCode } from "./research-code.mjs";

assert.equal(process.env.Q1_VERIFY_ISOLATED, "1");
const base = new URL(process.env.Q1_UI_BASE_URL);
assert(["127.0.0.1", "localhost"].includes(base.hostname) && base.port === "13860");
const { chromium } = await import(process.env.Q1_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({
  headless: true,
  ...(process.env.Q1_BROWSER_EXECUTABLE ? { executablePath: process.env.Q1_BROWSER_EXECUTABLE } : {}),
});
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
  return admin.request.fetch(new URL(path, base).href, {
    method,
    headers: { "Idempotency-Key": crypto.randomUUID() },
    ...(data === undefined ? {} : { data }),
    timeout: 240000,
  });
}

async function ok(path, method = "GET", data) {
  const response = await api(path, method, data);
  assert(response.ok(), path + ": " + response.status() + " " + await response.text());
  return response.json();
}

async function register() {
  const record = await ok("/api/registrations", "POST", {
    assignment_code: "A", consent_checked: true, research_code: newResearchCode(),
  });
  participants.push(record.participant_id);
  const context = await ok(`/api/participants/${record.participant_id}/presurvey`);
  const termKeys = context.term_items.map(({ key }) => key);
  const baseline = await ok(`/api/participants/${record.participant_id}/presurvey`, "POST", {
    survey_version: context.survey_version,
    prior_term_exposure: Object.fromEntries(termKeys.map((key) => [key, "not_experienced"])),
    prior_term_understanding: Object.fromEntries(termKeys.map((key) => [key, null])),
    general_ratings: {
      ai_usage_frequency_30d: "0_days",
      ai_proficiency: { goal_aligned_output: "not_applicable", revise_instructions: "not_applicable", verify_with_sources: "not_applicable" },
    },
  });
  assert.equal(baseline.next_url, "/pretest");
  return record;
}

try {
  await ok("/api/admin/auth/login", "POST", { password: "abc" });
  const status = await ok("/api/admin/ai/status");
  assert.equal(status.ai_backend, process.env.Q1_EXPECT_BACKEND ?? "mock");
  await ok("/api/admin/option-order", "PUT", { mode: "debug_fixed" });

  for (const endpoint of ["pretest-result-display", "question-review-display", "first-question-only", "learning-material-glossary-mode"]) {
    assert.equal((await api(`/api/admin/${endpoint}`)).status(), 404, `${endpoint} GET must be removed`);
    assert.equal((await api(`/api/admin/${endpoint}`, "PUT", { enabled: true })).status(), 404, `${endpoint} PUT must be removed`);
  }

  await page.goto(new URL("/admin", base).href);
  await page.getByLabel("パスワード", { exact: true }).fill("abc");
  await page.getByRole("button", { name: "管理画面を開く", exact: true }).click();
  await page.getByRole("heading", { name: "管理画面", exact: true }).waitFor();
  const adminText = await page.locator("body").innerText();
  for (const label of ["テスト結果の表示", "設問ごとの答え合わせ", "設問1のみ出題", "教材の用語解説モード", "集計の出題条件"]) {
    assert(!adminText.includes(label), `admin must not show ${label}`);
  }

  const record = await register();
  const logs = await ok(`/api/admin/participants/${record.participant_id}/logs`);
  assert.equal(logs.participant.show_pretest_results, false);
  assert.equal(logs.participant.show_retest_results, false);
  assert.equal(logs.participant.show_question_reviews, true);
  assert.equal(logs.participant.first_question_only, true);
  assert.equal(logs.participant.learning_material_glossary_mode, "integrated_material");

  await page.evaluate((participant) => {
    localStorage.setItem("participant_id", participant.participant_id);
    localStorage.setItem("display_code", participant.display_code);
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
    await page.getByRole("button", { name: index === 2 ? "テストを完了" : "次の用語へ", exact: true }).waitFor();
    assert.equal(await page.getByRole("radio", { checked: true }).count(), 1);
    assert.match(await page.locator(".term-page-question").innerText(), /正解|不正解/);
    await page.getByRole("button", { name: index === 2 ? "テストを完了" : "次の用語へ", exact: true }).click();
  }

  await page.waitForURL(/\/learning\/llm_knowledge|\/learning-targets/, { timeout: 240000 });
  if (page.url().endsWith("/learning-targets")) {
    await page.getByRole("link", { name: "学習を開始", exact: true }).click();
  }
  await page.getByRole("heading", { name: "教材", exact: true }).waitFor({ timeout: 240000 });
  assert(await page.locator(".problem-block input[type=radio]").count() >= 1);

  await page.goto(new URL("/admin", base).href);
  const adminPasswordInput = page.getByLabel("パスワード", { exact: true });
  if (await adminPasswordInput.count()) {
    await adminPasswordInput.fill("abc");
    await page.getByRole("button", { name: "管理画面を開く", exact: true }).click();
  }
  await page.getByRole("heading", { name: "管理画面", exact: true }).waitFor();
  await page.getByRole("tab", { name: logs.participant.group_condition, exact: true }).click();
  const participantRow = page.getByRole("row").filter({ hasText: record.display_code });
  await participantRow.getByRole("button", { name: "被験者ログを見る", exact: true }).click();
  const participantNotice = page.locator(".notice").filter({ hasText: record.display_code }).last();
  await participantNotice.waitFor();
  const participantDetail = await participantNotice.innerText();
  for (const label of ["テスト結果の表示", "設問ごとの答え合わせ", "設問1のみ出題", "教材の用語解説モード"]) {
    assert(!participantDetail.includes(label), `participant log must not show ${label}`);
  }
  assert.deepEqual(errors, []);
  console.log("fixed admin settings, participant log display, 3-question pretest, per-question answer review, hidden overall result and learning transition passed (" + status.ai_backend + ")");
} finally {
  for (const id of participants) await api("/api/admin/participants/" + id, "DELETE").catch(() => {});
  await browser.close();
}
