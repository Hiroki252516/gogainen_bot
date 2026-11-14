import assert from "node:assert/strict";

assert.equal(process.env.SURVEY_PREVIEW_VERIFY_ISOLATED, "1");
const base = new URL(process.env.SURVEY_PREVIEW_UI_BASE_URL);
assert(["localhost", "127.0.0.1"].includes(base.hostname) && base.port && base.port !== "3000");
const { chromium } = await import(process.env.SURVEY_PREVIEW_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true });
const terms = ["Transformer", "事前学習", "インストラクションチューニング", "人の評価・好みを用いる事後学習", "マルチエージェント", "記憶プロセス"];
const proficiencyItems = [
  "AIに目的を伝え、目的に合った回答を得ることができますか。",
  "AIの回答が期待と異なるとき、指示や条件を修正できますか。",
  "AIの回答が正しいか、公式サイトや別の資料で確かめられますか。",
];

try {
  for (const width of [1440, 768, 390]) {
    const context = await browser.newContext({
      viewport: { width, height: 950 },
      reducedMotion: width === 390 ? "reduce" : "no-preference",
    });
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
    const presurveyChoiceLayouts = await page.locator(".presurvey-form .survey-choice-options").evaluateAll((groups) => groups.map((group) => ({
      columns: getComputedStyle(group).gridTemplateColumns.trim().split(/\s+/).length,
      optionCount: group.querySelectorAll("button").length,
    })));
    assert(presurveyChoiceLayouts.length > 0);
    assert(presurveyChoiceLayouts.every(({ columns, optionCount }) => columns === (width <= 760 ? 2 : optionCount)));

    const presurveySubmit = page.getByRole("button", { name: "入力を確認する（保存なし）", exact: true });
    await presurveySubmit.click();
    await page.getByRole("alert").getByText("未選択の項目があります。必須の各項目を選択してください。", { exact: true }).waitFor();

    for (const [index, term] of terms.entries()) {
      const group = page.getByRole("group", { name: `${term}という用語を、実験の説明を受ける前に見たり聞いたりしたことがありますか。`, exact: true });
      assert.equal(await group.count(), 1);
      if (index === 0) {
        const experienced = group.getByRole("button", { name: "ある", exact: true });
        await experienced.click();
        const understanding = page.getByRole("group", { name: `${term}の基本的な意味や働きをどの程度理解していますか。`, exact: true });
        assert.equal(await understanding.count(), 1);
        const termItem = page.locator(".presurvey-term-item").filter({ has: group });
        const followup = termItem.locator(".presurvey-followup");
        assert.equal(await followup.count(), 1);
        await followup.getByRole("heading", { name: "追加質問：理解度", exact: true }).waitFor();
        assert.equal(await experienced.evaluate((button) => button === document.activeElement), true, "revealing the follow-up must not move focus");
        const announcement = page.locator(".presurvey-announcement");
        assert.equal(await announcement.getAttribute("role"), "status");
        assert.equal(await announcement.getAttribute("aria-live"), "polite");
        assert.match(await announcement.innerText(), new RegExp(`${term}.*表示`));
        const followupStyle = await followup.evaluate((element) => {
          const style = getComputedStyle(element);
          return { accent: style.borderLeftWidth, background: style.backgroundColor, animation: style.animationName };
        });
        assert.equal(followupStyle.accent, "4px");
        assert.notEqual(followupStyle.background, "rgba(0, 0, 0, 0)");
        assert.equal(followupStyle.animation, width === 390 ? "none" : "presurvey-followup-enter");
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, "follow-up must not cause horizontal overflow");
        const chosenUnderstanding = understanding.getByRole("button", { name: "ある程度理解している", exact: true });
        await chosenUnderstanding.click();
        assert.equal(await chosenUnderstanding.getAttribute("aria-pressed"), "true");
        await group.getByRole("button", { name: "ない", exact: true }).click();
        assert.equal(await followup.count(), 0);
        assert.match(await page.locator(".presurvey-announcement").innerText(), new RegExp(`${term}.*非表示`));
        await group.getByRole("button", { name: "ある", exact: true }).click();
        assert.equal(await followup.count(), 1);
        assert.equal(await followup.getByRole("button", { name: "ある程度理解している", exact: true }).getAttribute("aria-pressed"), "false", "hidden follow-up answers must be cleared");
        await understanding.getByRole("button", { name: "ある程度理解している", exact: true }).click();
      } else {
        const answer = index % 2 ? "ない" : "覚えていない";
        await group.getByRole("button", { name: answer, exact: true }).click();
        assert.equal(await page.getByRole("group", { name: `${term}の基本的な意味や働きをどの程度理解していますか。`, exact: true }).count(), 0);
      }
    }
    await page.getByRole("group", { name: "直近30日間のうち、AIを利用した日は何日ありましたか。", exact: true }).getByRole("button", { name: "0日", exact: true }).click();
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
