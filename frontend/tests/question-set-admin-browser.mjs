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
  assert.equal(await page.getByRole("group", { name: "新規参加者に適用する問題版", exact: true }).count(), 0);
  assert.equal(await page.getByRole("group", { name: "集計する問題版", exact: true }).count(), 0);
  await page.getByText("今後の新規参加者には通常版を適用します。易しい版の参加者は閲覧専用で、群集計には含まれません。", { exact: true }).waitFor();
  await page.getByText("集計対象: 通常版。1回6設問・単一選択で集計します。生ログと被験者一覧は、閲覧専用の易しい版参加者を含めて表示します。", { exact: true }).waitFor();
  assert.equal((await (await page.request.get(new URL("/api/admin/question-set", base).href)).json()).mode, "standard");
  assert.equal((await page.request.put(new URL("/api/admin/question-set", base).href, { data: { mode: "easy" } })).status(), 422);
  if (process.env.CYCLE_RETIRED_EASY_PARTICIPANT_ID) {
    const participantId = process.env.CYCLE_RETIRED_EASY_PARTICIPANT_ID;
    const retiredParticipant = await page.evaluate(async (id) => {
      const roster = await (await fetch("/api/admin/participants")).json();
      return roster.participants.find((participant) => participant.participant_id === id);
    }, participantId);
    assert(retiredParticipant, "retired Easy participant was not returned by the admin API");
    const row = page.getByRole("row").filter({ hasText: retiredParticipant.display_code });
    await row.getByRole("button", { name: "被験者ログを見る", exact: true }).click();
    await page.getByText("問題版: 易しい版", { exact: true }).waitFor();
    await page.getByText("易しい版の実行を停止しています。保存済み記録は閲覧専用で、群集計から除外されます。", { exact: true }).waitFor();
    assert.equal(await page.getByRole("button", { name: "評価サマリーを再計算", exact: true }).isDisabled(), true);
  }
  assert((await page.getByRole("link", { name: "6仮説・参加者別CSV", exact: true }).getAttribute("href")).includes("question_set_mode=standard"));
  await fs.mkdir(process.env.CYCLE_SCREENSHOT_DIR, { recursive: true });
  for (const [name, size] of [["desktop", { width: 1440, height: 1000 }], ["mobile", { width: 390, height: 844 }]]) {
    await page.setViewportSize(size);
    await page.screenshot({ path: `${process.env.CYCLE_SCREENSHOT_DIR}/admin-${name}.png`, fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "admin horizontal overflow");
  }
  assert.equal(errors.length, 0, errors.join("\n"));
  console.log("admin fixed standard version and retired easy mode passed");
} finally {
  await browser.close();
}
