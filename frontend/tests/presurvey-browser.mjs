// Run only against a disposable backend with synthetic participants.
import assert from "node:assert/strict";
import { newResearchCode } from "./research-code.mjs";

assert.equal(process.env.PRESURVEY_VERIFY_ISOLATED, "1");
const base = new URL(process.env.PRESURVEY_UI_BASE_URL);
assert(["localhost", "127.0.0.1"].includes(base.hostname) && base.port && base.port !== "3000");
const { chromium } = await import(process.env.PRESURVEY_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true });
const modes = [
  { mode: "application", version: "presurvey-baseline-v4", keys: ["pretraining", "fine_tuning", "rag", "prompt_engineering", "multi_agent", "memory_process"] },
  { mode: "basic_understanding", version: "presurvey-baseline-v4", keys: ["pretraining", "fine_tuning", "rag", "prompt_engineering", "multi_agent", "memory_process"] },
  { mode: "four_topic_fundamentals", version: "presurvey-four-topic-baseline-v4", keys: ["transformer", "pretraining", "instruction_tuning", "human_feedback_post_training", "multi_agent", "memory_process"] },
];
const experienceChoices = [
  ["experienced", "ある"],
  ["not_experienced", "ない"],
  ["cannot_recall", "覚えていない"],
];
const understandingChoices = [
  ["not_at_all", "全く理解していない"],
  ["slightly", "少し理解している"],
  ["moderately", "ある程度理解している"],
  ["well", "よく理解している"],
];
const understandingScale = [
  "全く理解していない", "少し理解している", "ある程度理解している", "よく理解している",
];
const proficiencyItems = [
  ["goal_aligned_output", "目的を伝えて、目的に合った回答を得る"],
  ["revise_instructions", "期待と違う回答のとき、指示や条件を修正する"],
  ["verify_with_sources", "AIの回答を他の資料・情報源で確認する"],
];

async function request(context, path, method = "GET", data) {
  return context.request.fetch(new URL(path, base).href, {
    method,
    ...(data === undefined ? {} : { data }),
  });
}

try {
  for (const mode of modes) {
    for (const width of [1440, 768, 390]) {
      const context = await browser.newContext({ viewport: { width, height: 950 } });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const login = await request(context, "/api/admin/auth/login", "POST", { password: "abc" });
      assert(login.ok(), await login.text());
      const configured = await request(context, "/api/admin/test-content-mode", "PUT", { mode: mode.mode });
      assert.equal(configured.status(), 200, await configured.text());
      const registration = await request(context, "/api/registrations", "POST", {
        assignment_code: "A", consent_checked: true, research_code: newResearchCode(),
      });
      assert.equal(registration.status(), 200, await registration.text());
      const { participant_id: pid, display_code: displayCode } = await registration.json();
      assert.equal((await request(context, `/api/experiment/${pid}/pretest`)).status(), 409);
      const contextResponse = await request(context, `/api/participants/${pid}/presurvey`);
      assert.equal(contextResponse.status(), 200);
      const surveyContext = await contextResponse.json();
      assert.equal(surveyContext.survey_version, mode.version);
      assert.deepEqual(surveyContext.term_items.map(({ key }) => key), mode.keys);

      await page.addInitScript(({ id, code }) => {
        localStorage.setItem("participant_id", id);
        localStorage.setItem("display_code", code);
      }, { id: pid, code: displayCode });
      await page.goto(new URL("/presurvey", base).href);
      const save = page.getByRole("button", { name: "回答を保存して事前テストへ", exact: true });
      await page.getByRole("heading", { name: "実験前アンケート", exact: true }).waitFor();
      await save.click();
      assert.match(await page.locator("form").getByRole("alert").innerText(), /未選択/);

      const exposure = {};
      const understanding = {};
      for (const [index, { key, label }] of surveyContext.term_items.entries()) {
        const group = page.getByRole("group", { name: `${label}という用語を、実験の説明を受ける前に見たり聞いたりしたことがありますか。`, exact: true });
        for (const [, choiceLabel] of experienceChoices) {
          assert.equal(await group.getByRole("button", { name: choiceLabel, exact: true }).count(), 1);
        }
        const selected = experienceChoices[index % experienceChoices.length];
        await group.getByRole("button", { name: selected[1], exact: true }).click();
        exposure[key] = selected[0];

        const comprehensionLabel = `${label}の基本的な意味や働きをどの程度理解していますか。`;
        const comprehensionGroup = page.getByRole("group", { name: comprehensionLabel, exact: true });
        if (selected[0] === "experienced") {
          assert.equal(await comprehensionGroup.count(), 1);
          for (const choiceLabel of understandingScale) {
            assert.equal(await comprehensionGroup.getByRole("button", { name: choiceLabel, exact: true }).count(), 1);
          }
          const chosenUnderstanding = understandingChoices[(index + 1) % understandingChoices.length];
          await comprehensionGroup.getByRole("button", { name: chosenUnderstanding[1], exact: true }).click();
          understanding[key] = chosenUnderstanding[0];
        } else {
          assert.equal(await comprehensionGroup.count(), 0);
          understanding[key] = null;
        }
      }

      const frequencyLabel = "直近30日間のうち、AIを利用した日数";
      const frequency = page.getByRole("group", { name: frequencyLabel, exact: true });
      for (const label of ["0日", "1〜3日", "4〜8日", "9〜20日", "21〜30日"]) {
        assert.equal(await frequency.getByRole("button", { name: label, exact: true }).count(), 1);
      }
      await frequency.getByRole("button", { name: "9〜20日", exact: true }).click();
      const proficiency = {};
      for (const [key, label] of proficiencyItems) {
        const group = page.getByRole("group", { name: label, exact: true });
        for (const choice of ["1", "2", "3", "4", "5", "評価できない"]) {
          assert.equal(await group.getByRole("button", { name: choice, exact: true }).count(), 1);
        }
        const chosen = key === "verify_with_sources" ? "評価できない" : key === "goal_aligned_output" ? "4" : "2";
        await group.getByRole("button", { name: chosen, exact: true }).click();
    proficiency[key] = chosen === "評価できない" ? "not_applicable" : Number(chosen);
      }
      const choiceLayouts = await page.locator(".presurvey-form .survey-choice-options").evaluateAll((groups) => groups.map((group) => {
        const buttons = [...group.querySelectorAll("button")].map((button) => button.getBoundingClientRect());
        const elements = [...group.querySelectorAll("button")];
        return {
          columns: getComputedStyle(group).gridTemplateColumns.trim().split(/\s+/).length,
          optionCount: buttons.length,
          rows: new Set(buttons.map((button) => Math.round(button.top))).size,
          overflowingButtons: elements.some((button) => button.scrollWidth > button.clientWidth + 1),
        };
      }));
      assert(choiceLayouts.length > 0);
      const narrow = width <= 760;
      assert(choiceLayouts.every(({ columns, optionCount, rows, overflowingButtons }) =>
        columns === (narrow ? 2 : optionCount)
        && rows === (narrow ? Math.ceil(optionCount / 2) : 1)
        && !overflowingButtons
      ), `choices must match the responsive horizontal layout at ${width}px`);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `horizontal overflow at ${width}px`);

      const responsePromise = page.waitForResponse((response) => response.url().endsWith(`/api/participants/${pid}/presurvey`) && response.request().method() === "POST");
      await save.click();
      const saved = await responsePromise;
      assert.equal(saved.status(), 200, await saved.text());
      const requestBody = saved.request().postDataJSON();
      assert.deepEqual(requestBody.prior_term_exposure, exposure);
      assert.deepEqual(requestBody.prior_term_understanding, understanding);
      assert.deepEqual(requestBody.general_ratings, {
        ai_usage_frequency_30d: "9_20_days",
        ai_proficiency: proficiency,
      });
      await page.waitForURL(new URL("/pretest", base).href);

      const logs = await request(context, `/api/admin/participants/${pid}/logs`);
      assert(logs.ok(), await logs.text());
      const surveys = (await logs.json()).surveys;
      assert.equal(surveys.length, 1);
      assert.equal(surveys[0].phase, "presurvey");
      assert.equal(surveys[0].survey_version, mode.version);
      assert.deepEqual(surveys[0].responses.prior_term_exposure, exposure);
      assert.deepEqual(surveys[0].responses.prior_term_understanding, understanding);
      const csv = await request(context, `/api/admin/participants/${pid}/logs.csv`);
      const xlsx = await request(context, `/api/admin/participants/${pid}/logs.xlsx`);
      assert(csv.ok() && xlsx.ok());
      assert((await csv.text()).includes(mode.version));
      assert.match(xlsx.headers()["content-type"], /spreadsheetml/);
      assert.deepEqual(errors, []);
      await context.close();
      console.log(`presurvey ${mode.mode} ${width}px passed`);
    }
  }
} finally {
  await browser.close();
}
