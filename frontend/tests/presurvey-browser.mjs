// Run only against a disposable backend with synthetic participants.
import assert from "node:assert/strict";

assert.equal(process.env.PRESURVEY_VERIFY_ISOLATED, "1");
const base = new URL(process.env.PRESURVEY_UI_BASE_URL);
assert(["localhost", "127.0.0.1"].includes(base.hostname) && base.port && base.port !== "3000");
const { chromium } = await import(process.env.PRESURVEY_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true });
const knowledgeChoices = [
  ["unknown", "知らない"],
  ["heard_of", "聞いたことがある"],
  ["knows_meaning", "意味を知っている"],
  ["can_explain", "説明できる"],
];
const termLabels = ["事前学習", "ファインチューニング", "RAG", "プロンプトエンジニアリング", "マルチエージェント",
  "記憶プロセス（AIが以前の会話で伝えた利用者の希望を記憶し、次回以降の回答に利用する仕組み）"];

async function request(context, path, method = "GET", data) {
  const response = await context.request.fetch(new URL(path, base).href, {
    method,
    ...(data === undefined ? {} : { data }),
  });
  return response;
}

try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 950 } });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const registration = await request(context, "/api/registrations", "POST", {
      data: { assignment_code: "A", consent_checked: true, student_number: `PRESURVEY-SYNTHETIC-${width}-${Date.now()}` },
    });
    assert.equal(registration.status(), 200, await registration.text());
    const { participant_id: pid, display_code: displayCode } = await registration.json();
    assert.equal((await request(context, `/api/experiment/${pid}/pretest`)).status(), 409);
    assert.equal((await request(context, `/api/participants/${pid}/presurvey`)).status(), 200);
    await page.addInitScript(({ id, code }) => {
      localStorage.setItem("participant_id", id);
      localStorage.setItem("display_code", code);
    }, { id: pid, code: displayCode });
    await page.goto(new URL("/presurvey", base).href);
    const save = page.getByRole("button", { name: "回答を保存して事前テストへ", exact: true });
    await page.getByRole("heading", { name: "実験前アンケート", exact: true }).waitFor();
    await save.click();
    assert.match(await page.locator("form").getByRole("alert").innerText(), /未選択/);
    const selectedKnowledge = {};
    for (const [index, label] of termLabels.entries()) {
      const selected = knowledgeChoices[index % knowledgeChoices.length];
      const group = page.getByRole("group", { name: label, exact: true });
      for (const [, choiceLabel] of knowledgeChoices) {
        assert.equal(await group.getByRole("button", { name: choiceLabel, exact: true }).count(), 1);
      }
      await group.getByRole("button", { name: selected[1], exact: true }).click();
      selectedKnowledge[ ["pretraining", "fine_tuning", "rag", "prompt_engineering", "multi_agent", "memory_process"][index] ] = selected[0];
    }
    const ratingGroups = page.locator(".survey-rating-options");
    assert.equal(await ratingGroups.count(), 2);
    await ratingGroups.nth(0).getByRole("button", { name: "3", exact: true }).click();
    await ratingGroups.nth(1).getByRole("button", { name: "4", exact: true }).click();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "horizontal overflow");
    const responsePromise = page.waitForResponse((response) => response.url().endsWith(`/api/participants/${pid}/presurvey`) && response.request().method() === "POST");
    await save.click();
    const saved = await responsePromise;
    assert.equal(saved.status(), 200, await saved.text());
    await page.waitForURL(new URL("/pretest", base).href);
    assert.equal((await request(context, `/api/participants/${pid}/current-step`)).status(), 200);
    const adminLogin = await context.request.post(new URL("/api/admin/auth/login", base).href, { data: { password: "abc" } });
    assert(adminLogin.ok());
    const logs = await request(context, `/api/admin/participants/${pid}/logs`);
    assert(logs.ok());
    const survey = (await logs.json()).surveys;
    assert.equal(survey.length, 1);
    assert.equal(survey[0].phase, "presurvey");
    assert.equal(survey[0].survey_version, "presurvey-baseline-v2");
    assert.deepEqual(survey[0].responses.prior_term_knowledge, selectedKnowledge);
    assert.equal(survey[0].responses.general_ratings.ai_usage_frequency, 3);
    assert.equal(survey[0].responses.general_ratings.self_rated_ai_proficiency, 4);
    assert.deepEqual(errors, []);
    await context.close();
  }
  console.log("presurvey browser checks passed at desktop and mobile widths");
} finally {
  await browser.close();
}
