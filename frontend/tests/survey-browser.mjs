// Run against disposable survey fixtures in an isolated Mock backend.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

assert.equal(process.env.SURVEY_VERIFY_ISOLATED, "1");
const base = new URL(process.env.SURVEY_UI_BASE_URL);
assert(base.hostname === "survey-v2-frontend-check" || (["localhost", "127.0.0.1"].includes(base.hostname) && base.port && base.port !== "3000"));
const { chromium } = await import(process.env.SURVEY_PLAYWRIGHT_MODULE);
const fixtures = [1440, 390].flatMap((width) => [true, false].map((viewed) => ({ width, viewed })));
const browser = await chromium.launch({ headless: true });
if (process.env.SURVEY_SCREENSHOT_DIR) await mkdir(process.env.SURVEY_SCREENSHOT_DIR, { recursive: true });

async function api(request, path, method = "GET", data) {
  const response = await request.fetch(new URL(path, base).href, { method, headers: { "Idempotency-Key": crypto.randomUUID() }, ...(data === undefined ? {} : { data }) });
  assert(response.ok(), path + ": " + response.status() + " " + await response.text());
  return response.json();
}

async function prepareFixture(request, fixture) {
  await api(request, "/api/admin/option-order", "PUT", { mode: "debug_fixed" });
  await api(request, "/api/admin/question-review-display", "PUT", { enabled: false });
  await api(request, "/api/admin/pretest-result-display", "PUT", { enabled: false });
  const record = await api(request, "/api/registrations", "POST", {
    assignment_code: "A", consent_checked: true,
    student_number: "SURVEY-SYNTHETIC-" + fixture.width + "-" + fixture.viewed + "-" + Date.now(),
  });
  const pid = record.participant_id;
  const baseline = await api(request, "/api/participants/" + pid + "/presurvey", "POST", {
    survey_version: "presurvey-baseline-v2",
    prior_term_knowledge: { pretraining: "unknown", fine_tuning: "unknown", rag: "unknown", prompt_engineering: "unknown", multi_agent: "unknown", memory_process: "unknown" },
    general_ratings: { ai_usage_frequency: 3, self_rated_ai_proficiency: 4 },
  });
  assert.equal(baseline.next_url, "/pretest");
  const questions = (await api(request, "/api/experiment/" + pid + "/pretest")).questions;
  const byTerm = new Map();
  for (const question of questions) byTerm.set(question.term_slug, [...(byTerm.get(question.term_slug) || []), question]);
  for (const [slug, pair] of byTerm) {
    const at = new Date().toISOString();
    await api(request, "/api/attempts/term-page", "POST", {
      participant_id: pid, phase: "pretest", term_slug: slug, test_round: pair[0].test_round,
      page_id: crypto.randomUUID(), question_shown_at: at, answered_at: at, elapsed_time_sec: 1,
      answers: pair.map((question) => ({
        question_id: question.question_id,
        selected_option_ids: [question.options.find((option) => fixture.viewed ? option.exclusive : option.label === "A").option_id],
      })),
    });
  }
  await api(request, "/api/participants/" + pid + "/diagnose-pretest", "POST", {});
  if (fixture.viewed) {
    const targets = await api(request, "/api/participants/" + pid + "/learning-targets");
    const session = await api(request, "/api/tutor-sessions", "POST", { participant_id: pid, term_slug: targets.targets[0].term_slug });
    const turn = await api(request, "/api/tutor-sessions/" + session.tutor_session_id + "/turns", "POST", {});
    await api(request, "/api/tutor-turns/" + turn.turn_id + "/material-view", "POST", {});
    await api(request, "/api/participants/" + pid + "/give-up-learning", "POST", {});
  }
  const ended = await api(request, "/api/participants/" + pid + "/give-up", "POST", {});
  assert.equal(ended.next_step, "survey");
  return record;
}

try {
  for (const fixture of fixtures) {
    const context = await browser.newContext({ viewport: { width: fixture.width, height: 1000 } });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const login = await context.request.post(new URL("/api/admin/auth/login", base).href, { data: { password: "abc" } });
    assert(login.ok());
    const status = await context.request.get(new URL("/api/admin/ai/status", base).href);
    assert.equal((await status.json()).ai_backend, "mock");

    Object.assign(fixture, await prepareFixture(context.request, fixture));
    await page.addInitScript((record) => {
      localStorage.setItem("participant_id", record.participant_id);
      localStorage.setItem("display_code", record.display_code);
    }, fixture);
    await page.goto(new URL("/survey", base).href);
    await page.getByRole("heading", { name: "実験後アンケート", exact: true }).waitFor().catch(async (error) => {
      console.error("page URL:", page.url(), "page errors:", errors, "body:", await page.locator("body").innerText());
      throw error;
    });
    const save = page.getByRole("button", { name: "回答を保存して終了", exact: true });
    if (process.env.SURVEY_SCREENSHOT_DIR) {
      await page.screenshot({ path: process.env.SURVEY_SCREENSHOT_DIR + "/" + fixture.width + "-" + fixture.viewed + ".png", fullPage: true });
    }
    await save.click();
    assert.match(await page.locator("form").getByRole("alert").innerText(), /未選択/);
    assert.equal(await page.getByText("普段のAI利用頻度", { exact: true }).count(), 0);
    assert.equal(await page.getByText("事前学習", { exact: true }).count(), 0);
    const ratings = page.locator(".survey-rating-options");
    assert.equal(await ratings.count(), fixture.viewed ? 8 : 2);
    for (let index = 0; index < await ratings.count() - 1; index++) {
      await ratings.nth(index).getByRole("button", { name: "7", exact: true }).click();
    }
    await save.click();
    assert.match(await page.locator("form").getByRole("alert").innerText(), /未選択/);
    await ratings.last().getByRole("button", { name: "7", exact: true }).click();
    const textarea = page.locator("textarea");
    assert.equal(await textarea.getAttribute("required"), null);
    assert.equal(await textarea.inputValue(), "");
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "horizontal overflow");
    const posted = page.waitForRequest((request) => request.method() === "POST" && request.url().endsWith("/survey"));
    const saved = page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith("/survey"));
    await save.click();
    const body = (await posted).postDataJSON();
    assert.equal(body.survey_version, "posttest-10point-v3");
    assert(!("prior_term_knowledge" in body));
    assert.equal(body.general_ratings.system_usability, 7);
    assert.equal(body.general_ratings.system_clarity, 7);
    assert(!("ai_usage_frequency" in body.general_ratings));
    assert(!("experiences" in body));
    assert(!("self_rated_ai_knowledge" in body.general_ratings));
    assert.equal(body.free_comment, "");
    assert.equal(body.material_ratings === null, !fixture.viewed);
    assert((await saved).ok());
    await page.waitForURL(new URL("/finish", base).href);
    const logs = await context.request.get(new URL("/api/admin/participants/" + fixture.participant_id + "/logs", base).href);
    assert(logs.ok());
    const survey = (await logs.json()).surveys;
    assert.equal(survey.length, 2);
    const presurvey = survey.find((row) => row.phase === "presurvey");
    const posttest = survey.find((row) => row.phase === "posttest");
    assert.equal(presurvey.survey_version, "presurvey-baseline-v2");
    assert.deepEqual(presurvey.responses.prior_term_knowledge, { pretraining: "unknown", fine_tuning: "unknown", rag: "unknown", prompt_engineering: "unknown", multi_agent: "unknown", memory_process: "unknown" });
    assert.equal(presurvey.responses.general_ratings.ai_usage_frequency, 3);
    assert.equal(posttest.survey_version, "posttest-10point-v3");
    assert(!("prior_term_knowledge" in posttest.responses));
    assert.equal(posttest.free_comment, "");
    assert.deepEqual(errors, []);
    console.log("survey saved without comment:", fixture.width, fixture.viewed ? "material viewed" : "not viewed");
    await context.close();
  }
} finally {
  await browser.close();
}
