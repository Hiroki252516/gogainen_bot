// Run only against an isolated Mock backend, never the study instance.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { newResearchCode } from "./research-code.mjs";

if (process.env.GLOSSARY_MODE_VERIFY_ISOLATED !== "1" || !process.env.GLOSSARY_MODE_UI_BASE_URL || !process.env.GLOSSARY_MODE_PLAYWRIGHT_MODULE || !process.env.GLOSSARY_MODE_SCREENSHOT_DIR) {
  throw new Error("Set GLOSSARY_MODE_VERIFY_ISOLATED=1, GLOSSARY_MODE_UI_BASE_URL, GLOSSARY_MODE_PLAYWRIGHT_MODULE, and GLOSSARY_MODE_SCREENSHOT_DIR.");
}

const base = new URL(process.env.GLOSSARY_MODE_UI_BASE_URL);
assert(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname));
assert(base.port && base.port !== "3000", "Do not use the study frontend.");
const { chromium } = await import(process.env.GLOSSARY_MODE_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({
  headless: true,
  ...(process.env.GLOSSARY_MODE_BROWSER_EXECUTABLE ? { executablePath: process.env.GLOSSARY_MODE_BROWSER_EXECUTABLE } : {}),
});
await mkdir(process.env.GLOSSARY_MODE_SCREENSHOT_DIR, { recursive: true });

async function api(request, path, method = "GET", data, headers) {
  const response = await request.fetch(new URL(path, base).href, {
    method,
    ...(data ? { data } : {}),
    ...(headers ? { headers } : {}),
  });
  assert(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}

async function createParticipant(request, group, serial) {
  await api(request, "/api/admin/auth/login", "POST", { password: process.env.ADMIN_PASSWORD || "abc" });
  assert.equal((await api(request, "/api/admin/ai/status")).ai_backend, "mock");
  await api(request, "/api/admin/option-order", "PUT", { mode: "debug_fixed" });
  const created = await api(request, "/api/registrations", "POST", {
    assignment_code: group,
    consent_checked: true,
    research_code: newResearchCode(),
  });
  const participantId = created.participant_id;

  const presurvey = await api(request, `/api/participants/${participantId}/presurvey`);
  const termKeys = presurvey.term_items.map(({ key }) => key);
  await api(request, `/api/participants/${participantId}/presurvey`, "POST", {
    survey_version: presurvey.survey_version,
    prior_term_exposure: Object.fromEntries(termKeys.map((key) => [key, "not_experienced"])),
    prior_term_understanding: Object.fromEntries(termKeys.map((key) => [key, null])),
    general_ratings: {
      ai_usage_frequency_30d: "0_days",
      ai_proficiency: { goal_aligned_output: "not_applicable", revise_instructions: "not_applicable", verify_with_sources: "not_applicable" },
    },
  });

  const log = await api(request, `/api/admin/participants/${participantId}/logs`);
  assert.equal(log.participant.learning_material_glossary_mode, "integrated_material", "new registrations must use integrated material");
  assert.equal(log.participant.show_pretest_results, false);
  assert.equal(log.participant.show_retest_results, false);
  assert.equal(log.participant.show_question_reviews, true);
  assert.equal(log.participant.first_question_only, true);

  const questions = (await api(request, `/api/experiment/${participantId}/pretest`)).questions;
  assert.equal(questions.length, 3);
  for (const question of questions) {
    const now = new Date().toISOString();
    await api(request, "/api/attempts/term-page", "POST", {
      participant_id: participantId,
      phase: "pretest",
      term_slug: question.term_slug,
      test_round: question.test_round,
      page_id: crypto.randomUUID(),
      answers: [{
        question_id: question.question_id,
        selected_option_ids: [question.options.find((option) => option.exclusive).option_id],
      }],
      question_shown_at: now,
      answered_at: now,
      elapsed_time_sec: 1,
    }, { "Idempotency-Key": `glossary-mode-${serial}-${question.term_slug}` });
    const pending = (await api(request, `/api/experiment/${participantId}/pretest`)).pending_question_review;
    assert.equal(pending.term_slug, question.term_slug);
    assert.equal(pending.results.length, 1);
    await api(request, `/api/participants/${participantId}/question-review-acknowledgements`, "POST", {
      phase: "pretest", term_slug: question.term_slug,
    });
  }
  const diagnosis = await api(request, `/api/participants/${participantId}/diagnose-pretest`, "POST", {});
  assert.equal(diagnosis.next_step, "learning_targets");
  assert.equal(diagnosis.review_required, false);
  const targets = await api(request, `/api/participants/${participantId}/learning-targets`);
  assert(targets.targets.some((target) => target.term_slug === "llm_knowledge"));
  return { ...created, participant_id: participantId, target_slugs: targets.targets.map((target) => target.term_slug) };
}

async function assertGlossaryPanel(page, glossary) {
  const materialAside = page.getByRole("complementary", { name: "教材の用語の補足", exact: true });
  assert(glossary.entries.length > 0, "saved glossary snapshot should remain available");
  assert.equal(await materialAside.count(), 0, "integrated mode hides the material glossary panel");
  assert.equal(await page.getByRole("button", { name: "用語の補足", exact: true }).count(), 0);
}

try {
  let serial = 0;
  for (const width of [1440, 390]) {
    for (const group of ["A", "B"]) {
      serial += 1;
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      const page = await context.newPage();
      page.setDefaultTimeout(30_000);
      const participant = await createParticipant(page.request, group, serial);
      await page.addInitScript((record) => {
        localStorage.setItem("participant_id", record.participant_id);
        localStorage.setItem("display_code", record.display_code);
        localStorage.setItem("learning_targets", JSON.stringify(record.target_slugs));
        localStorage.setItem("learning_targets_participant_id", record.participant_id);
      }, participant);

      const materialResponse = page.waitForResponse((response) => /\/api\/tutor-sessions\/[^/]+\/turns$/.test(response.url()));
      await page.goto(new URL("/learning/llm_knowledge", base).href);
      const turn = await (await materialResponse).json();
      assert.equal(turn.show_material_glossary, false);
      assert(turn.glossary.entries.length > 0);
      await page.getByRole("heading", { name: "LLMに知識を与える方法", exact: true }).waitFor();
      await assertGlossaryPanel(page, turn.glossary);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "material page has horizontal overflow");
      await page.screenshot({ path: `${process.env.GLOSSARY_MODE_SCREENSHOT_DIR}/${width}-integrated_material-${group}-material.png`, fullPage: true });

      const practice = turn.practice_question;
      if (practice.questions?.length) {
        let offset = 0;
        for (const question of practice.questions) {
          await page.locator('input[type="radio"]').nth(offset).check();
          offset += question.options.length;
        }
      } else if (practice.selection_mode === "multiple") {
        const choices = practice.options.filter((option) => !option.exclusive).slice(0, practice.min_selections || 3);
        for (const choice of choices) await page.locator(`input[value="${choice.option_id}"]`).check();
      } else {
        await page.locator('input[type="radio"]').first().check();
      }

      const feedbackResponse = page.waitForResponse((response) => /\/api\/tutor-turns\/[^/]+\/respond$/.test(response.url()));
      await page.getByRole("button", { name: "回答を確認", exact: true }).click();
      const feedback = await (await feedbackResponse).json();
      await page.getByRole("heading", { name: "教材フィードバック", exact: true }).waitFor();
      assert(feedback.glossary.entries.length > 0);
      const feedbackGlossary = page.getByRole("complementary", { name: "回答後解説の用語の補足", exact: true });
      assert(await feedbackGlossary.isVisible(), "answer-feedback glossary must remain visible");
      assert.equal(await page.locator(".glossary-sidebar").count(), 0);
      assert.equal(await page.getByRole("button", { name: "用語の補足", exact: true }).count(), 0);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "feedback page has horizontal overflow");
      await page.screenshot({ path: `${process.env.GLOSSARY_MODE_SCREENSHOT_DIR}/${width}-integrated_material-${group}-feedback.png`, fullPage: true });
      console.log(`ok ${width}px integrated_material group=${group}: registration snapshot, hidden material glossary, visible feedback glossary`);
      await context.close();
    }
  }
} finally {
  await browser.close();
}
