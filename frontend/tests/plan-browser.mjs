// Opt-in end-to-end check against an explicitly isolated backend and test account.
import assert from "node:assert/strict";

if (process.env.PLAN_VERIFY_ISOLATED !== "1" || !process.env.PLAN_UI_BASE_URL || !process.env.PLAN_PLAYWRIGHT_MODULE) {
  throw new Error("Set PLAN_VERIFY_ISOLATED=1, PLAN_UI_BASE_URL, and PLAN_PLAYWRIGHT_MODULE. Never use the study database.");
}
const base = new URL(process.env.PLAN_UI_BASE_URL);
assert(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname));
const { chromium } = await import(process.env.PLAN_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true });
const terms = ["LLMに知識を与える方法", "マルチエージェント", "記憶プロセス"];

async function answerTest(page, unknownFirst) {
  for (let index = 0; index < 3; index++) {
    await page.locator(".question-heading").filter({ hasText: terms[index] }).waitFor();
    for (const label of unknownFirst && index === 0 ? "J" : "ABC") {
      await page.getByRole("checkbox", { name: new RegExp(`^${label}\\.`) }).check();
    }
    await page.getByRole("button", { name: index === 2 ? "完了" : "次へ", exact: true }).click();
  }
}

try {
  for (const viewed of [false, true]) {
    const context = await browser.newContext();
    const page = await context.newPage();
    page.setDefaultTimeout(120_000);
    await page.goto(new URL("/start", base).href);
    await page.getByLabel("参加コード", { exact: true }).fill("A");
    await page.getByRole("button", { name: "同意書を確認する", exact: true }).click();
    await page.getByRole("checkbox", { name: "上記を確認し、研究参加と研究用ログの保存に同意します。", exact: true }).check();
    const created = page.waitForResponse((response) => response.url().endsWith("/api/participants") && response.request().method() === "POST");
    await page.getByRole("button", { name: "同意してテストを開始", exact: true }).click();
    const participant = await (await created).json();
    await answerTest(page, viewed);
    if (viewed) {
      await page.getByRole("link", { name: "学習を開始", exact: true }).click();
      await page.getByRole("heading", { name: "教材", exact: true }).waitFor();
      for (const label of "ABC") await page.getByRole("checkbox", { name: new RegExp(`^${label}\\.`) }).check();
      await page.getByRole("button", { name: "回答を確認", exact: true }).click();
      await page.getByText("正解です。", { exact: true }).waitFor();
      await page.getByRole("button", { name: "次へ", exact: true }).click();
    } else {
      await page.getByRole("link", { name: "次のテストへ", exact: true }).click();
    }
    await answerTest(page, false);
    await page.getByRole("link", { name: "アンケートへ進む", exact: true }).click();
    await page.getByRole("heading", { name: "実験後アンケート", exact: true }).waitFor();
    const selects = page.locator("form select");
    await selects.first().waitFor();
    const count = await selects.count();
    assert.equal(count, viewed ? 14 : 8);
    for (let index = 0; index < count; index++) {
      const select = selects.nth(index);
      assert.notEqual(await select.getAttribute("required"), null);
      await select.selectOption(index < 4 ? "no" : "8");
    }
    const comment = page.getByRole("textbox", { name: "自由記述（必須）", exact: false });
    assert.notEqual(await comment.getAttribute("required"), null);
    await comment.fill("画面検証用の合成回答です。特になし。");
    const saved = page.waitForResponse((response) => response.url().endsWith(`/api/participants/${participant.participant_id}/survey`) && response.request().method() === "POST");
    await page.getByRole("button", { name: "回答を保存して終了", exact: true }).click();
    assert.equal((await saved).status(), 200);
    await page.getByRole("heading", { name: "実験は終了です", exact: true }).waitFor();
    const logs = await (await page.request.get(new URL(`/api/admin/participants/${participant.participant_id}/logs`, base).href)).json();
    assert.equal(logs.surveys[0].responses.has_viewed_material, viewed);
    assert.equal(logs.surveys[0].responses.material_ratings === null, !viewed);
    if (viewed) assert.equal(logs.latest_evaluation_summary.hypothesis_metrics.h5.value, 8);
    await page.goto(new URL("/admin", base).href);
    await page.getByRole("heading", { name: "6仮説の記述集計", exact: true }).waitFor();
    assert.equal(await page.getByRole("link", { name: "6仮説・群別CSV", exact: true }).count(), 1);
    console.log(JSON.stringify({ scenario: viewed ? "material_viewed" : "not_viewed_initial_perfect", survey_fields: count, flow_and_admin: "passed", participant_id: participant.participant_id }));
    await context.close();
  }
} finally {
  await browser.close();
}
