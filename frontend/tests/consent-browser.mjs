// Run only against an isolated backend, with synthetic identifiers.
import assert from "node:assert/strict";

const previewOnly = process.env.CONSENT_PREVIEW_ONLY === "1";
if ((!previewOnly && process.env.PLAN_VERIFY_ISOLATED !== "1") || !process.env.PLAN_UI_BASE_URL || !process.env.PLAN_PLAYWRIGHT_MODULE) {
  throw new Error("Explicit isolated browser configuration is required.");
}
const base = new URL(process.env.PLAN_UI_BASE_URL);
assert(["localhost", "127.0.0.1"].includes(base.hostname));
const { chromium } = await import(process.env.PLAN_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();
const synthetic = "001202611120001";

try {
  await page.goto(new URL(previewOnly ? "/consent" : "/start", base).href);
  if (!previewOnly) {
    await page.getByLabel("参加コード", { exact: true }).fill("A");
    await page.getByRole("button", { name: "同意書を確認する", exact: true }).click();
  }
  await page.getByRole("heading", { name: "研究参加同意書", exact: true }).waitFor();
  await page.getByRole("heading", { name: "5. 結果の公表", exact: true }).waitFor();
  assert.equal(await page.getByText("未確定項目を含む動作確認用です。", { exact: false }).count(), 0);
  assert.equal(await page.getByText("4つの専門用語", { exact: false }).count(), 1);
  assert.equal(await page.getByText("Codex app-server", { exact: false }).count(), 1);
  const researchCodeInput = page.getByRole("textbox", { name: "研究用コードを入力してください（必須）" });
  await researchCodeInput.waitFor();
  assert.equal(await page.getByRole("textbox", { name: /学籍番号/ }).count(), 0);

  if (previewOnly) {
    if (process.env.CONSENT_SCREENSHOT) await page.screenshot({ path: process.env.CONSENT_SCREENSHOT, fullPage: true });
    console.log("deployed consent page read-only preview passed");
  } else {
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "同意して事前アンケートへ", exact: true }).click();
    await page.getByRole("alert").filter({ hasText: "半角数字1〜64桁" }).waitFor();
    await researchCodeInput.fill("00A1-０2");
    assert.equal(await researchCodeInput.inputValue(), "0012", "leading zeroes are preserved and invalid characters are removed");
    await researchCodeInput.fill(synthetic);

    const response = page.waitForResponse(r => r.url().endsWith("/api/registrations") && r.request().method() === "POST");
    await page.getByRole("button", { name: "同意して事前アンケートへ", exact: true }).click();
    const created = await response;
    assert.equal(created.status(), 200);
    const participant = await created.json();
    await page.waitForURL("**/presurvey");
    const presurvey = await context.request.get(new URL(`/api/participants/${participant.participant_id}/presurvey`, base).href);
    assert.equal(presurvey.status(), 200);
    const contextData = await presurvey.json();
    assert.equal(contextData.survey_version, "presurvey-four-topic-baseline-v4");
    assert.deepEqual(contextData.term_items.map(({ key }) => key), [
      "transformer", "pretraining", "instruction_tuning", "human_feedback_post_training", "multi_agent", "memory_process",
    ]);

    const persisted = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
    assert(!persisted.includes(synthetic));
    const login = await context.request.post(new URL("/api/admin/auth/login", base).href, { data: { password: "abc" } });
    assert(login.ok());
    const logs = await context.request.get(new URL(`/api/admin/participants/${participant.participant_id}/logs`, base).href);
    assert(!(await logs.text()).includes(synthetic));
    for (const path of [
      "/api/admin/identity-mappings", "/api/admin/identity-mappings.csv",
      "/api/admin/research-code-mappings", "/api/admin/research-code-mappings.csv",
    ]) {
      assert.equal((await context.request.get(new URL(path, base).href)).status(), 404);
    }

    await page.goto(new URL("/admin", base).href);
    assert.equal(await page.getByRole("button", { name: /対応表/ }).count(), 0);
    await page.getByText("4用語版（固定）", { exact: true }).waitFor();
    const deleted = await context.request.delete(new URL(`/api/admin/participants/${participant.participant_id}`, base).href);
    assert.equal(deleted.status(), 200, await deleted.text());
    if (process.env.CONSENT_SCREENSHOT) await page.screenshot({ path: process.env.CONSENT_SCREENSHOT, fullPage: true });
    console.log("consent browser checks passed: current copy, transient code, fixed mode, removed mapping UI/API");
  }
} finally {
  await browser.close();
}
