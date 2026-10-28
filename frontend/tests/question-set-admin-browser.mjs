import assert from "node:assert/strict";
import fs from "node:fs/promises";

if (process.env.CYCLE_VERIFY_ISOLATED !== "1" || !process.env.CYCLE_UI_BASE_URL || !process.env.CYCLE_PLAYWRIGHT_MODULE || !process.env.CYCLE_SCREENSHOT_DIR) throw new Error("Explicit isolated UI and screenshot directory are required.");
const base = new URL(process.env.CYCLE_UI_BASE_URL);
assert(["localhost", "127.0.0.1"].includes(base.hostname) && base.port && base.port !== "3000");
const { chromium } = await import(process.env.CYCLE_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, channel: process.env.CYCLE_BROWSER_CHANNEL || undefined });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(new URL("/admin", base).href);
  await page.getByLabel("パスワード", { exact: true }).fill("abc");
  await page.getByRole("button", { name: "管理画面を開く", exact: true }).click();
  const settings = page.getByRole("group", { name: "新規参加者に適用する問題版", exact: true });
  const aggregate = page.getByRole("group", { name: "集計する問題版", exact: true });
  await settings.getByRole("button", { name: "通常版", exact: true }).waitFor();
  await page.waitForFunction(() => !document.querySelector('[aria-label="新規参加者に適用する問題版"] button')?.disabled);
  assert.equal(await aggregate.getByRole("button", { name: "通常版", exact: true }).getAttribute("aria-pressed"), "true");
  for (const [mode, label] of [["standard", "通常版"], ["easy", "易しい版"]]) {
    const button = settings.getByRole("button", { name: label, exact: true });
    if (await button.getAttribute("aria-pressed") !== "true") {
      const saved = page.waitForResponse((r) => r.url().endsWith("/api/admin/question-set") && r.request().method() === "PUT");
      await button.click();
      assert.equal((await saved).status(), 200);
    }
    assert.equal((await (await page.request.get(new URL("/api/admin/question-set", base).href)).json()).mode, mode);
  }
  assert.equal(await aggregate.getByRole("button", { name: "通常版", exact: true }).getAttribute("aria-pressed"), "true");
  const summary = page.waitForResponse((r) => r.url().includes("/api/admin/evaluation-summary?question_set_mode=easy"));
  await aggregate.getByRole("button", { name: "易しい版", exact: true }).click();
  assert.equal((await summary).status(), 200);
  await page.getByText("集計対象: 易しい版。新規参加者向け設定とは独立しています。生ログと被験者一覧は両版を表示します。", { exact: true }).waitFor();
  assert.equal((await (await page.request.get(new URL("/api/admin/question-set", base).href)).json()).mode, "easy");
  assert((await page.getByRole("link", { name: "6仮説・参加者別CSV", exact: true }).getAttribute("href")).includes("question_set_mode=easy"));
  await fs.mkdir(process.env.CYCLE_SCREENSHOT_DIR, { recursive: true });
  for (const [name, size] of [["desktop", { width: 1440, height: 1000 }], ["mobile", { width: 390, height: 844 }]]) {
    await page.setViewportSize(size);
    await page.screenshot({ path: `${process.env.CYCLE_SCREENSHOT_DIR}/admin-${name}.png`, fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "admin horizontal overflow");
  }
  assert.equal(errors.length, 0, errors.join("\n"));
  console.log("admin question mode and independent aggregation controls passed");
} finally {
  await browser.close();
}
