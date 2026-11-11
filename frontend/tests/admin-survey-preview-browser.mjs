import assert from "node:assert/strict";

assert.equal(process.env.SURVEY_PREVIEW_VERIFY_ISOLATED, "1");
const base = new URL(process.env.SURVEY_PREVIEW_UI_BASE_URL);
assert(["localhost", "127.0.0.1"].includes(base.hostname) && base.port && base.port !== "3000");
const { chromium } = await import(process.env.SURVEY_PREVIEW_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true });
const terms = ["Transformer", "事前学習", "ファインチューニング", "人の評価・好みを用いる事後学習", "マルチエージェント", "記憶プロセス"];
const proficiencyItems = [
  "目的を伝えて、目的に合った回答を得る",
  "期待と違う回答のとき、指示や条件を修正する",
  "AIの回答を他の資料・情報源で確認する",
];

try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 950 } });
    const page = await context.newPage();
    const participantRequests = [];
    const errors = [];
    page.on("request", (request) => {
      if (/\/api\/(participants|experiment)\//.test(request.url())) participantRequests.push(request.url());
    });
    page.on("pageerror", (error) => errors.push(error.message));

    await page.goto(new URL("/admin/survey-preview/presurvey", base).href);
    await page.getByRole("dialog", { name: "管理画面のパスワード", exact: true }).waitFor();
    assert.equal(await page.locator(".presurvey-form").count(), 0, "locked admin routes must not show preview content");
    await page.getByLabel("パスワード", { exact: true }).fill("abc");
    await page.getByRole("button", { name: "管理画面を開く", exact: true }).click();
    await page.getByRole("button", { name: "管理画面をロック", exact: true }).waitFor();
    await page.getByRole("heading", { name: "実験前アンケート", exact: true }).waitFor();

    const presurveySubmit = page.getByRole("button", { name: "入力を確認する（保存なし）", exact: true });
    await presurveySubmit.click();
    await page.getByRole("alert").getByText("未選択の項目があります。必須の各項目を選択してください。", { exact: true }).waitFor();

    for (const [index, term] of terms.entries()) {
      const group = page.getByRole("group", { name: `${term}という用語を、実験の説明を受ける前に見たり聞いたりしたことがありますか。`, exact: true });
      assert.equal(await group.count(), 1);
      if (index === 0) {
        await group.getByRole("button", { name: "ある", exact: true }).click();
        const understanding = page.getByRole("group", { name: `${term}の基本的な意味や働きをどの程度理解していますか。`, exact: true });
        assert.equal(await understanding.count(), 1);
      } else {
        await group.getByRole("button", { name: index % 2 ? "ない" : "覚えていない", exact: true }).click();
      }
    }
    await page.getByRole("group", { name: "直近30日間のうち、AIを利用した日数", exact: true }).getByRole("button", { name: "0日", exact: true }).click();
    for (const label of proficiencyItems) {
      await page.getByRole("group", { name: label, exact: true }).getByRole("button", { name: "評価できない", exact: true }).click();
    }
    await presurveySubmit.click();
    await page.getByRole("alert").getByText("未選択の項目があります。必須の各項目を選択してください。", { exact: true }).waitFor();
    await page.getByRole("group", { name: `${terms[0]}の基本的な意味や働きをどの程度理解していますか。`, exact: true }).getByRole("button", { name: "全く理解していない", exact: true }).click();
    await presurveySubmit.click();
    await page.getByRole("heading", { name: "事前アンケートの入力確認", exact: true }).waitFor();
    await page.getByText("デバッグプレビューのため、回答は保存されていません。", { exact: false }).waitFor();
    await page.getByRole("button", { name: "もう一度入力する", exact: true }).click();

    await page.getByRole("link", { name: "事後アンケート", exact: true }).click();
    await page.getByRole("heading", { name: "実験後アンケート", exact: true }).waitFor();
    const ratingGroups = page.locator(".survey-rating-options");
    assert.equal(await ratingGroups.count(), 8, "viewed-material preview includes 2 system and 6 material ratings");
    const posttestSubmit = page.getByRole("button", { name: "入力を確認する（保存なし）", exact: true });
    await posttestSubmit.click();
    await page.getByRole("alert").getByText("未選択の項目があります。各項目を選択してください。", { exact: true }).waitFor();
    for (let index = 0; index < await ratingGroups.count(); index += 1) {
      await ratingGroups.nth(index).getByRole("button").nth(2).click();
    }
    await page.locator("textarea").fill("プレビュー確認");
    await posttestSubmit.click();
    await page.getByRole("heading", { name: "事後アンケートの入力確認", exact: true }).waitFor();
    assert.deepEqual(participantRequests, [], "preview must not call participant or experiment APIs");
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `horizontal overflow at ${width}px`);
    assert.deepEqual(errors, []);
    await context.close();
    console.log(`admin survey preview ${width}px passed`);
  }
} finally {
  await browser.close();
}
