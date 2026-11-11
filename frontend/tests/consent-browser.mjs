// Run only against an isolated backend, with synthetic identifiers.
import assert from "node:assert/strict";
import { newResearchCode } from "./research-code.mjs";
const previewOnly = process.env.CONSENT_PREVIEW_ONLY === "1";
if ((!previewOnly && process.env.PLAN_VERIFY_ISOLATED !== "1") || !process.env.PLAN_UI_BASE_URL || !process.env.PLAN_PLAYWRIGHT_MODULE) {
  throw new Error("Explicit isolated browser configuration is required.");
}
const base = new URL(process.env.PLAN_UI_BASE_URL);
assert(["localhost", "127.0.0.1"].includes(base.hostname));
const { chromium } = await import(process.env.PLAN_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ acceptDownloads: true });
const page = await context.newPage();
const synthetic = "001202611110001";
try {
  if (previewOnly) {
    // Read-only deployment check: never register, download, or delete on the study service.
    await page.goto(new URL("/consent", base).href);
    await page.getByRole("heading", { name: "研究参加同意書", exact: true }).waitFor();
    await page.getByRole("textbox", { name: "伝えられた番号を入力してください（必須）" }).waitFor();
    assert.equal(await page.getByRole("heading", { name: "5. 結果の公表", exact: true }).count(), 1);
    if (process.env.CONSENT_SCREENSHOT) await page.screenshot({ path: process.env.CONSENT_SCREENSHOT, fullPage: true });
    console.log("deployed consent page read-only preview passed");
  } else {
  await page.goto(new URL("/start", base).href);
  await page.getByLabel("参加コード", { exact: true }).fill("A");
  await page.getByRole("button", { name: "同意書を確認する", exact: true }).click();
  await page.getByRole("heading", { name: "研究参加同意書", exact: true }).waitFor();
  assert(await page.getByText("【実際の保存場所】", { exact: false }).count());
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "同意して事前アンケートへ", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "半角数字1〜64桁" }).waitFor();
  const researchCodeInput = page.getByRole("textbox", { name: "伝えられた番号を入力してください（必須）" });
  await researchCodeInput.fill("00A1-０2");
  assert.equal(await researchCodeInput.inputValue(), "0012", "leading zeroes are preserved while non-ASCII digits and other characters are removed");
  await researchCodeInput.fill(synthetic);
  const response = page.waitForResponse(r => r.url().endsWith("/api/registrations") && r.request().method() === "POST");
  await page.getByRole("button", { name: "同意して事前アンケートへ", exact: true }).click();
  const created = await response;
  assert.equal(created.status(), 200);
  const participant = await created.json();
  await page.waitForURL("**/presurvey");
  const persisted = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
  assert(!persisted.includes(synthetic));
  const logs = await context.request.get(new URL(`/api/admin/participants/${participant.participant_id}/logs`, base).href);
  assert(!(await logs.text()).includes(synthetic));
  await page.goto(new URL("/admin", base).href);
  await page.getByRole("button", { name: "研究用コード対応表を表示・更新", exact: true }).click();
  await page.getByRole("cell", { name: synthetic, exact: true }).waitFor();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "研究用コード対応表CSVをダウンロード", exact: true }).click();
  assert.equal((await download).suggestedFilename(), "research-code-mappings.csv");
  page.once("dialog", dialog => dialog.dismiss());
  await page.getByRole("button", { name: "対応表を個別削除", exact: true }).click();
  assert.equal(await page.getByRole("cell", { name: synthetic, exact: true }).count(), 1);
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "対応表を個別削除", exact: true }).click();
  await page.getByText("アプリ内に研究用コード対応表はありません。", { exact: true }).waitFor();
  assert.equal((await context.request.get(new URL(`/api/participants/${participant.participant_id}/current-step`, base).href)).status(), 200);
  // Verify full-table deletion separately, using another synthetic registration.
  const anotherCode = newResearchCode();
  const another = await context.request.post(new URL("/api/registrations", base).href, {
    data: { assignment_code: "B", consent_checked: true, research_code: anotherCode },
  });
  assert.equal(another.status(), 200);
  await page.getByRole("button", { name: "研究用コード対応表を表示・更新", exact: true }).click();
  await page.getByRole("cell", { name: anotherCode, exact: true }).waitFor();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "研究用コード対応表を全件削除", exact: true }).click();
  await page.getByText("アプリ内に研究用コード対応表はありません。", { exact: true }).waitFor();
  if (process.env.CONSENT_SCREENSHOT) {
    const preview = await context.newPage();
    await preview.goto(new URL("/start", base).href);
    await preview.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
    await preview.goto(new URL("/consent", base).href);
    await preview.getByRole("heading", { name: "研究参加同意書", exact: true }).waitFor();
    await preview.screenshot({ path: process.env.CONSENT_SCREENSHOT, fullPage: true });
  }
  console.log("consent browser checks passed: research-code input, registration, storage isolation, download, cancel, individual/all deletion");
  }
} finally { await browser.close(); }
