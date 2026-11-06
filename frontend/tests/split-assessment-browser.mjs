// Requires a separate Mock backend and temporary database.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

assert.equal(process.env.SPLIT_VERIFY_ISOLATED, "1");
const base = new URL(process.env.SPLIT_UI_URL);
assert(["localhost", "127.0.0.1"].includes(base.hostname) && base.port && base.port !== "3000");
const { chromium } = await import(process.env.SPLIT_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const directory = process.env.SPLIT_SCREENSHOTS;
assert(directory && process.env.ADMIN_PASSWORD);
await mkdir(directory, { recursive: true });

async function api(request, path, method = "GET", data) {
  const response = await request.fetch(new URL(path, base).href, { method, ...(data ? { data } : {}) });
  assert(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}

async function answerTermPages(page, participant, phase, m1ChoiceIds, width, assignmentCode, optionOrder) {
  const questions = (await api(page.request, `/api/experiment/${participant.participant_id}/${phase.replaceAll("_", "-")}`));
  assert.equal(questions.test_page_mode, "per_term");
  assert.equal(questions.questions.length, 6);
  await page.goto(new URL(`/${phase.replaceAll("_", "-")}`, base).href);
  for (let pageIndex = 0; pageIndex < 3; pageIndex++) {
    const pair = questions.questions.slice(pageIndex * 2, pageIndex * 2 + 2);
    const groups = page.locator(".term-page-question");
    await page.getByText(`${pageIndex + 1} / 3`, { exact: true }).waitFor();
    await groups.first().waitFor();
    assert.equal(await groups.count(), 2);
    assert.equal(await page.getByRole("radio").count(), 12);
    assert.equal(await page.locator(".notice .question-heading").count(), 1);
    const primaryAction = page.locator(".term-page-runner .corner-primary");
    assert.equal(await primaryAction.count(), 1);
    const primaryStyle = await primaryAction.evaluate((element) => ({
      position: getComputedStyle(element).position,
      background: getComputedStyle(element).backgroundColor,
      buttonFontSize: getComputedStyle(element.querySelector("button")).fontSize,
      buttonMinHeight: getComputedStyle(element.querySelector("button")).minHeight,
    }));
    assert.deepEqual(primaryStyle, {
      position: "fixed",
      background: "rgb(255, 255, 255)",
      buttonFontSize: "18px",
      buttonMinHeight: "56px",
    });
    const actionBeforeScroll = await primaryAction.boundingBox();
    assert(actionBeforeScroll);
    assert(actionBeforeScroll.x >= 0 && actionBeforeScroll.x + actionBeforeScroll.width <= width);
    assert(actionBeforeScroll.y >= 0 && actionBeforeScroll.y + actionBeforeScroll.height <= 1000);
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.waitForTimeout(50);
    const actionAfterScroll = await primaryAction.boundingBox();
    assert(actionAfterScroll);
    assert(Math.abs(actionAfterScroll.x - actionBeforeScroll.x) < 1, "fixed action should retain its horizontal position while scrolling");
    assert(Math.abs(actionAfterScroll.y - actionBeforeScroll.y) < 1, "fixed action should retain its vertical position while scrolling");
    await page.evaluate(() => window.scrollTo(0, 0));
    const scenario = pair[0].body.split("\n\n設問1：")[0];
    assert.equal(pair[1].body.split("\n\n設問2：")[0], scenario);
    assert.equal((await page.locator(".notice").first().innerText()).includes(scenario), true);
    const glossaryEntries = [];
    const seenGlossary = new Set();
    for (const question of pair) for (const entry of question.glossary?.entries || []) {
      const key = JSON.stringify([entry.id, entry.term, entry.definition]);
      if (!seenGlossary.has(key)) { seenGlossary.add(key); glossaryEntries.push(entry); }
    }
    if (glossaryEntries.length) {
      if (width < 1100) await page.getByRole("button", { name: "用語の補足", exact: true }).click();
      const glossary = page.locator(width < 1100 ? ".glossary-dialog" : ".glossary-sidebar");
      await glossary.waitFor();
      assert.deepEqual(await glossary.locator("dt").allTextContents(), glossaryEntries.map((entry) => entry.term));
      if (width < 1100) await page.getByRole("button", { name: "閉じる", exact: true }).click();
    }

    for (let questionIndex = 0; questionIndex < pair.length; questionIndex++) {
      const question = pair[questionIndex];
      const optionId = phase === "pretest"
        ? m1ChoiceIds.get(question.question_id)
        : question.options.find((option) => option.exclusive)?.option_id;
      assert(optionId, `missing target option for ${question.question_id}`);
      const group = groups.nth(questionIndex);
      await group.locator(`input[value="${optionId}"]`).check();
      if (questionIndex === 0) assert.equal(await groups.nth(1).locator('input[type="radio"]:checked').count(), 0);
    }
    if (width < 1100) {
      const endNote = page.locator(".term-page-runner .glossary-main > span.muted").last();
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await page.waitForTimeout(50);
      const noteBox = await endNote.boundingBox();
      const glossaryButtonBox = await page.getByRole("button", { name: "用語の補足", exact: true }).boundingBox();
      assert(noteBox && glossaryButtonBox, "mobile footer and glossary control should be visible");
      const overlaps = noteBox.x < glossaryButtonBox.x + glossaryButtonBox.width
        && noteBox.x + noteBox.width > glossaryButtonBox.x
        && noteBox.y < glossaryButtonBox.y + glossaryButtonBox.height
        && noteBox.y + noteBox.height > glossaryButtonBox.y;
      assert.equal(overlaps, false, "glossary toggle must not cover the end note");
    }
    if (phase === "pretest" && pageIndex === 0) {
      await page.screenshot({ path: `${directory}/pretest-${assignmentCode}-${optionOrder}-${width}.png`, fullPage: true });
    }
    await page.getByRole("button", { name: pageIndex === 2 ? "完了" : "次へ", exact: true }).click();
    const reviewAction = page.getByRole("button", {
      name: pageIndex === 2 ? "テストを完了" : "次の用語へ",
      exact: true,
    });
    const nextProgress = pageIndex < 2
      ? page.getByText(`${pageIndex + 2} / 3`, { exact: true })
      : null;
    const transition = await Promise.race([
      reviewAction.waitFor({ state: "visible" }).then(() => "review").catch(() => null),
      (nextProgress
        ? nextProgress.waitFor({ state: "visible" })
        : page.waitForURL(/\/learning-targets$/)
      ).then(() => "advanced").catch(() => null),
    ]);
    if (transition === "review") {
      assert.equal(await groups.count(), 2);
      for (const group of await groups.all()) {
        assert.equal(await group.getByRole("radio").count(), 6, "answer review should retain all six choices");
        assert.equal(await group.locator(".option-verdict").count(), 1);
      }
      await reviewAction.click();
    }
    if (nextProgress) await nextProgress.waitFor();
    if (pageIndex === 0) {
      await page.reload();
      await page.getByText("2 / 3", { exact: true }).waitFor();
      assert.equal(await page.locator(".term-page-question").count(), 2, "reload resumes on the first incomplete term page");
    }
  }
  await page.waitForURL(/\/learning-targets$/);
}

try {
  const baseline = await browser.newContext();
  await api(baseline.request, "/api/admin/auth/login", "POST", { password: process.env.ADMIN_PASSWORD });
  await api(baseline.request, "/api/admin/option-order", "PUT", { mode: "debug_fixed" });
  const reference = await api(baseline.request, "/api/registrations", "POST", {
    assignment_code: "A", consent_checked: true, student_number: `SPLIT-MODE-REFERENCE-${Date.now()}`,
  });
  const referenceQuestions = (await api(baseline.request, `/api/experiment/${reference.participant_id}/pretest`)).questions;
  const m1ChoiceIds = new Map(referenceQuestions.map((question) => [question.question_id, question.options.find((option) => option.label === "B")?.option_id]));
  await api(baseline.request, `/api/admin/participants/${reference.participant_id}`, "DELETE");
  await baseline.close();

  for (const width of [1440, 390]) {
    for (const assignment_code of ["A", "B"]) {
      for (const optionOrder of ["debug_fixed", "randomized"]) {
        const context = await browser.newContext({ viewport: { width, height: 1000 } });
        const page = await context.newPage();
        page.setDefaultTimeout(30000);
        await api(page.request, "/api/admin/auth/login", "POST", { password: process.env.ADMIN_PASSWORD });
        assert.equal((await api(page.request, "/api/admin/ai/status")).ai_backend, "mock");
        await api(page.request, "/api/admin/option-order", "PUT", { mode: optionOrder });
        const participant = await api(page.request, "/api/registrations", "POST", {
          assignment_code,
          consent_checked: true,
          student_number: `SPLIT-BROWSER-${assignment_code}-${optionOrder}-${width}`,
        });
        await page.addInitScript((p) => { localStorage.setItem("participant_id", p.participant_id); localStorage.setItem("display_code", p.display_code); }, participant);
        await answerTermPages(page, participant, "pretest", m1ChoiceIds, width, assignment_code, optionOrder);
        for (const slug of ["llm_knowledge", "multi_agent", "memory_process"]) {
          await page.goto(new URL(`/learning/${slug}`, base).href);
          const groups = page.locator(".problem-block .options");
          await groups.first().waitFor();
          assert.equal(await groups.count(), 2);
          const displayedBodies = await page.locator(".problem-block > p.preserve-lines, .problem-block .stack > p.preserve-lines").allTextContents();
          assert.equal(displayedBodies.length, 3, `${slug} should show one shared scenario and two question bodies`);
          assert.match(displayedBodies[0], /.+/s);
          assert.match(displayedBodies[1], /^設問1：/);
          assert.match(displayedBodies[2], /^設問2：/);
          for (const group of await groups.all()) assert.equal(await group.getByRole("radio").count(), 6);
          assert.equal(await page.locator(".problem-block .option-answer-correct, .problem-block .option-answer-incorrect").count(), 0, "answer correctness must stay hidden before submission");

          await groups.nth(0).getByRole("radio", { name: /^F\./ }).check();
          assert.equal(await groups.nth(1).locator('input[type="radio"]:checked').count(), 0, "question selections must be independent");
          await groups.nth(1).getByRole("radio", { name: /^F\./ }).check();
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          await page.screenshot({ path: `${directory}/${slug}-${assignment_code}-${optionOrder}-${width}.png`, fullPage: true });
          const feedbackResponse = page.waitForResponse((response) => /\/api\/tutor-turns\/[^/]+\/respond$/.test(response.url()));
          await page.getByRole("button", { name: "回答を確認", exact: true }).click();
          await feedbackResponse;
          await page.getByText("不正解です。", { exact: true }).waitFor();
          for (const group of await groups.all()) {
            const options = await group.locator("label.option").evaluateAll((labels) => labels.map((label) => ({
              correct: label.classList.contains("option-answer-correct"),
              incorrect: label.classList.contains("option-answer-incorrect"),
              checked: label.querySelector("input")?.checked,
              verdict: label.querySelector(".option-verdict")?.textContent,
            })));
            assert.equal(options.filter((option) => option.correct).length, 1);
            assert.equal(options.filter((option) => option.incorrect).length, 5);
            assert.equal(options.filter((option) => option.incorrect && !option.checked).length, 4, "unselected incorrect choices must also be red");
            for (const option of options) {
              assert.equal(option.verdict, option.correct ? "正解" : "不正解");
              assert.equal(option.incorrect, !option.correct);
            }
          }
          await page.getByRole("button", { name: "次へ", exact: true }).click();
        }
        await page.waitForURL(/\/retest$/);
        await answerTermPages(page, participant, "retest", m1ChoiceIds, width, assignment_code, optionOrder);
        assert.equal((await api(page.request, `/api/participants/${participant.participant_id}/learning-targets`)).test_results.results.length, 6);
        await context.close();
        console.log(`ok ${width}px, group ${assignment_code}, ${optionOrder}, grouped pretest and retest`);
      }
    }
  }
} finally {
  await browser.close();
}
