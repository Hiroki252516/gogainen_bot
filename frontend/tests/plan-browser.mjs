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
    await page.getByRole("textbox", { name: "伝えられた番号を入力してください（必須）" }).fill("001234567890");
    await page.getByRole("checkbox", { name: "説明を読み、その内容を理解した上で、本実験に参加することに同意します。", exact: true }).check();
    const created = page.waitForResponse((response) => response.url().endsWith("/api/registrations") && response.request().method() === "POST");
    await page.getByRole("button", { name: "同意して事前アンケートへ", exact: true }).click();
    const participant = await (await created).json();
    await page.getByRole("heading", { name: "実験前アンケート", exact: true }).waitFor();
    for (const label of ["事前学習", "ファインチューニング", "RAG", "プロンプトエンジニアリング", "マルチエージェント", "記憶プロセス"])
      await page.getByRole("group", { name: new RegExp(`^${label}`) }).getByRole("button", { name: "知らない", exact: true }).click();
    const baselineRatings = page.locator("form .survey-rating-options");
    await baselineRatings.nth(0).getByRole("button", { name: "5", exact: true }).click();
    await baselineRatings.nth(1).getByRole("button", { name: "5", exact: true }).click();
    await page.getByRole("button", { name: "回答を保存して事前テストへ", exact: true }).click();
    await page.waitForURL(/\/pretest$/);
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
    const optionGroups = page.locator("form .survey-rating-options");
    await optionGroups.first().waitFor();
    const count = await optionGroups.count();
    assert.equal(count, viewed ? 8 : 2);
    for (let index = 0; index < count; index++) {
      const group = optionGroups.nth(index);
      assert.notEqual(await group.getAttribute("aria-label"), null);
      await group.locator('[data-rating-value="4"]').click();
    }
    const comment = page.getByRole("textbox", { name: "自由記述（任意）", exact: false });
    await comment.fill("画面検証用の合成回答です。特になし。");
    const saved = page.waitForResponse((response) => response.url().endsWith(`/api/participants/${participant.participant_id}/survey`) && response.request().method() === "POST");
    await page.getByRole("button", { name: "回答を保存して終了", exact: true }).click();
    assert.equal((await saved).status(), 200);
    await page.getByRole("heading", { name: "実験は終了です", exact: true }).waitFor();
    const logs = await (await page.request.get(new URL(`/api/admin/participants/${participant.participant_id}/logs`, base).href)).json();
    assert.equal(logs.surveys[0].phase, "presurvey");
    assert.equal(logs.surveys[1].phase, "posttest");
    assert.equal(logs.surveys[1].responses.has_viewed_material, viewed);
    assert.equal(logs.surveys[1].responses.material_ratings === null, !viewed);
    if (viewed) assert.equal(logs.latest_evaluation_summary.hypothesis_metrics.h4.items.clarity, 4);
    await page.goto(new URL("/admin", base).href);
    await page.getByRole("heading", { name: "4仮説の記述集計", exact: false }).waitFor();
    assert.equal(await page.getByRole("link", { name: "4仮説・群別CSV", exact: true }).count(), 1);
    const summary = await (await page.request.get(new URL("/api/admin/evaluation-summary", base).href)).json();
    assert.equal(summary.hypotheses.metrics_version, "four-hypotheses-v1");
    for (const group of summary.hypotheses.groups) {
      assert.equal(group.h3.denominator, group.h3.eligible_count);
      assert.equal(group.h3.numerator <= group.h3.denominator, true);
      assert.equal("h5" in group, false);
      assert.equal("h6" in group, false);
    }
    const csv = await page.request.get(new URL("/api/admin/export/hypothesis_group_summary.csv", base).href);
    assert.equal(csv.status(), 200);
    assert((await csv.text()).includes("h4.difficulty_appropriateness"));
    console.log(JSON.stringify({ scenario: viewed ? "material_viewed" : "not_viewed_initial_perfect", survey_fields: count, flow_and_admin: "passed", participant_id: participant.participant_id }));
    await context.close();
  }
} finally {
  await browser.close();
}
