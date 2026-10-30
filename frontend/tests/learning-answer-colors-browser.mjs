// Uses route-mocked API responses only; no backend or participant data is touched.
import assert from "node:assert/strict";

assert.equal(process.env.ANSWER_COLOR_VERIFY_ISOLATED, "1");
const base = new URL(process.env.ANSWER_COLOR_UI_URL);
assert(["localhost", "127.0.0.1"].includes(base.hostname) && base.port && base.port !== "3000");
const { chromium } = await import(process.env.ANSWER_COLOR_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ channel: "chrome", headless: true });

const options = [
  ...["A", "B", "C"].map((label, index) => ({ option_id: `correct-${index}`, label, body: `正答${index + 1}` })),
  ...["D", "E", "F", "G", "H", "I"].map((label, index) => ({ option_id: `incorrect-${index}`, label, body: `誤答${index + 1}` })),
  { option_id: "unknown", label: "J", body: "わからない。", exclusive: true },
];
const answerKey = Object.fromEntries(options.map((option) => [option.option_id, option.option_id.startsWith("correct-")]));
const turn = {
  turn_id: "synthetic-turn",
  term_slug: "multi_agent",
  term_label: "マルチエージェント",
  tutor_message: "## マルチエージェント\n\n確認用の教材です。",
  learner_prompt: "",
  practice_question: {
    body: "合成fixtureの確認問題です。",
    options,
    selection_mode: "multiple",
    min_selections: 3,
    max_selections: 3,
    learning_variant_index: 1,
  },
  turn_index: 1,
  max_turns: 3,
  learning_stage: "baseline",
};
const feedback = {
  feedback: "回答を確認しました。",
  answer_key: answerKey,
  next_action: "continue_learning",
  is_sufficient: false,
  session_completed: false,
  learning_stage: "baseline",
  next_learning_stage: "baseline",
  learning_misconception_type: "M1",
  turn_index: 1,
  max_turns: 3,
  attempts_used: 1,
  remaining_attempts: 0,
};

try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();
    await page.addInitScript(() => {
      localStorage.setItem("participant_id", "synthetic-participant");
      localStorage.setItem("display_code", "SYNTHETIC");
      localStorage.setItem("learning_targets", JSON.stringify(["multi_agent"]));
    });
    const unexpected = [];
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let payload;
      if (path.endsWith("/current-step")) {
        payload = { step: "learning_targets", next_url: "/learning/multi_agent", can_resume: true, progress: { stage_id: "learning", label: "学習中", percent: 25 } };
      } else if (path.endsWith("/learning-targets")) {
        payload = { targets: [{ term_slug: "multi_agent" }] };
      } else if (path === "/api/tutor-sessions" && route.request().method() === "POST") {
        payload = { tutor_session_id: "synthetic-session" };
      } else if (path === "/api/tutor-sessions/synthetic-session/turns" && route.request().method() === "POST") {
        payload = turn;
      } else if (path === "/api/tutor-turns/synthetic-turn/material-view" && route.request().method() === "POST") {
        payload = { recorded: true };
      } else if (path === "/api/tutor-turns/synthetic-turn/respond" && route.request().method() === "POST") {
        payload = feedback;
      } else {
        unexpected.push(`${route.request().method()} ${path}`);
        payload = { detail: "Unexpected API route in isolated UI test." };
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
    });

    await page.goto(new URL("/learning/multi_agent", base).href);
    await page.getByText("合成fixtureの確認問題です。", { exact: true }).waitFor();
    assert.equal(await page.locator(".problem-block .option-answer-correct, .problem-block .option-answer-incorrect").count(), 0);
    for (const label of ["D", "E", "F"]) await page.getByRole("checkbox", { name: new RegExp(`^${label}\\.`) }).check();
    await page.getByRole("button", { name: "回答を確認", exact: true }).click();
    await page.getByText("不正解です。", { exact: true }).waitFor();

    const rendered = await page.locator(".problem-block .options label.option").evaluateAll((labels) => labels.map((label) => {
      const input = label.querySelector('input[type="checkbox"]');
      return {
        optionId: input?.value,
        checked: input?.checked,
        correct: label.classList.contains("option-answer-correct"),
        incorrect: label.classList.contains("option-answer-incorrect"),
        verdict: label.querySelector(".option-verdict")?.textContent,
        background: getComputedStyle(label).backgroundColor,
        opacity: getComputedStyle(label).opacity,
      };
    }));
    assert.equal(rendered.length, options.length);
    for (const item of rendered) {
      const correct = answerKey[item.optionId] === true;
      assert.equal(item.correct, correct);
      assert.equal(item.incorrect, !correct);
      assert.equal(item.verdict, correct ? "正解" : "不正解");
      assert.equal(item.background, correct ? "rgb(240, 253, 246)" : "rgb(255, 245, 245)");
      assert.equal(item.opacity, "1");
    }
    assert(rendered.some((item) => item.incorrect && item.checked));
    assert(rendered.some((item) => item.incorrect && !item.checked), "unselected wrong choices must also remain visibly red when disabled");
    assert.deepEqual(unexpected, []);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    console.log(`ok multiple-choice learning feedback ${width}px`);
    await context.close();
  }
} finally {
  await browser.close();
}
