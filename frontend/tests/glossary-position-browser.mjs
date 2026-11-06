// Run only against an isolated Mock backend, never the study instance.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

if (process.env.GLOSSARY_VERIFY_ISOLATED !== "1" || !process.env.GLOSSARY_UI_BASE_URL || !process.env.GLOSSARY_PLAYWRIGHT_MODULE || !process.env.GLOSSARY_SCREENSHOT_DIR || !process.env.ADMIN_PASSWORD) throw new Error("Set isolated UI, browser, screenshot directory and test admin password.");
const base = new URL(process.env.GLOSSARY_UI_BASE_URL);
assert(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname) && base.port && base.port !== "3000");
const { chromium } = await import(process.env.GLOSSARY_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, ...(process.env.GLOSSARY_BROWSER_CHANNEL ? { channel: process.env.GLOSSARY_BROWSER_CHANNEL } : {}) });
await mkdir(process.env.GLOSSARY_SCREENSHOT_DIR, { recursive: true });

async function api(request, path, method = "GET", data) {
  const response = await request.fetch(new URL(path, base).href, { method, ...(data ? { data } : {}) });
  assert(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}

async function acknowledgeQuestionReviews(request, participantId, phase, questions) {
  for (const termSlug of new Set(questions.map((question) => question.term_slug))) {
    await api(request, `/api/participants/${participantId}/question-review-acknowledgements`, "POST", { phase, term_slug: termSlug });
  }
}

async function check(page, label, width) {
  const button = page.getByRole("button", { name: "用語の補足", exact: true });
  const exit = page.locator(".app-header-give-up button");
  const exitWrapper = page.locator(".app-header-give-up");
  const exitExpected = label !== "pretest";
  assert.equal(await exitWrapper.count(), exitExpected ? 1 : 0, `${label}: give-up visibility`);
  if (exitExpected) {
    assert(await exit.isVisible(), `${label}: give-up button visible`);
    assert.equal(await exitWrapper.evaluate((el) => getComputedStyle(el).position), "static");
    const initial = await exitWrapper.boundingBox();
    const arrangement = await page.evaluate(() => {
      const actions = document.querySelector(".app-header-actions");
      const giveUp = document.querySelector(".app-header-give-up");
      const admin = document.querySelector('a[href="/admin"]');
      const giveUpRect = giveUp.getBoundingClientRect();
      const adminRect = admin.getBoundingClientRect();
      return {
        order: actions.children[0] === giveUp && actions.children[1] === admin,
        adjacent: giveUpRect.right <= adminRect.left,
        overlap: giveUpRect.left < adminRect.right && adminRect.left < giveUpRect.right && giveUpRect.top < adminRect.bottom && adminRect.top < giveUpRect.bottom,
      };
    });
    assert(arrangement.order && arrangement.adjacent && !arrangement.overlap, `${label}: give-up must sit immediately left of admin link`);
    await page.evaluate(() => window.scrollTo(0, Math.min(350, document.documentElement.scrollHeight - innerHeight)));
    const scrolled = await exitWrapper.boundingBox();
    const scrollY = await page.evaluate(() => window.scrollY);
    assert(initial && scrolled && Math.abs(scrolled.y - (initial.y - scrollY)) <= 2, `${label}: give-up should move with the document`);
    if (scrollY > initial.y + 8) assert(scrolled.y + scrolled.height < 0, `${label}: give-up should scroll out of view`);
    await page.evaluate(() => window.scrollTo(0, 0));
    await exit.focus();
    assert(await exit.evaluate((el) => document.activeElement === el), `${label}: give-up remains keyboard focusable`);
  }
  const desktop = width >= 1100;
  assert.equal(await button.isVisible(), !desktop);
  if (desktop) {
    const aside = page.locator(".glossary-sidebar");
    assert(await aside.isVisible());
    const initial = await aside.boundingBox();
    const main = await page.locator(".glossary-main").boundingBox();
    assert(initial.x >= main.x + main.width, "sidebar overlaps main content");
    await page.evaluate(() => window.scrollTo(0, Math.min(350, document.documentElement.scrollHeight - innerHeight)));
    const scrolled = await aside.boundingBox();
    assert(scrolled.y >= 87 && scrolled.y <= initial.y, "sidebar does not follow scroll");
    const overlap = await page.evaluate(() => {
      const a = document.querySelector(".glossary-sidebar").getBoundingClientRect();
      return [...document.querySelectorAll(".corner-primary button, .app-header-give-up button")].some((node) => {
        const b = node.getBoundingClientRect();
        return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
      });
    });
    assert(!overlap, "sidebar overlaps an action");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `${process.env.GLOSSARY_SCREENSHOT_DIR}/${label}-${width}.png` });
  } else {
    await button.focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: label === "pretest" || label === "retest" ? "テストの用語の補足" : "教材の用語の補足" });
    assert(await dialog.isVisible());
    assert(await page.getByRole("button", { name: "閉じる", exact: true }).evaluate((el) => document.activeElement === el));
    await page.screenshot({ path: `${process.env.GLOSSARY_SCREENSHOT_DIR}/${label}-${width}.png` });
    await page.keyboard.press("Escape");
    assert(!(await dialog.isVisible()));
    assert(await button.evaluate((el) => document.activeElement === el), "focus not restored");
    const overlap = await page.evaluate(() => {
      const a = document.querySelector(".glossary-open").getBoundingClientRect();
      return [...document.querySelectorAll(".corner-primary button, .app-header-give-up button")].some((node) => {
        const b = node.getBoundingClientRect();
        return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
      });
    });
    assert(!overlap, "glossary button overlaps an action");
  }
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "horizontal overflow");
}

try {
  for (const width of [1920, 1100, 1099, 768, 390, 320]) {
    const context = await browser.newContext({ viewport: { width, height: 720 } });
    const page = await context.newPage();
    page.setDefaultTimeout(30000);
    await api(page.request, "/api/admin/auth/login", "POST", { password: process.env.ADMIN_PASSWORD });
    assert.equal((await api(page.request, "/api/admin/ai/status")).ai_backend, "mock");
    await api(page.request, "/api/admin/option-order", "PUT", { mode: "debug_fixed" });
    const record = await api(page.request, "/api/registrations", "POST", { assignment_code: "B", consent_checked: true, student_number: `GLOSSARY-POSITION-SYNTHETIC-${width}` });
    await page.addInitScript((p) => { localStorage.setItem("participant_id", p.participant_id); localStorage.setItem("display_code", p.display_code); }, record);
    const questions = (await api(page.request, `/api/experiment/${record.participant_id}/pretest`)).questions;
    await page.goto(new URL("/pretest", base).href);
    await page.locator(".options").first().waitFor();
    await check(page, "pretest", width);
    for (const question of questions) await api(page.request, "/api/attempts", "POST", { participant_id: record.participant_id, question_id: question.question_id, selected_option_ids: question.options.filter((option) => option.exclusive).map((option) => option.option_id) });
    await acknowledgeQuestionReviews(page.request, record.participant_id, "pretest", questions);
    await api(page.request, `/api/participants/${record.participant_id}/diagnose-pretest`, "POST", {});
    await page.goto(new URL("/learning/llm_knowledge", base).href);
    await page.locator(".learning-layout").waitFor();
    await check(page, "learning", width);
    const confirmationGroups = page.locator(".problem-block .options");
    assert.equal(await confirmationGroups.count(), 2);
    for (const group of await confirmationGroups.all()) await group.getByRole("radio", { name: /^D\./ }).check();
    await page.getByRole("button", { name: "回答を確認", exact: true }).click();
    await page.getByText("不正解です。", { exact: true }).waitFor();
    const feedback = page.locator(".feedback-card .learning-glossary");
    if (await feedback.count()) assert(await feedback.isVisible());
    await api(page.request, `/api/participants/${record.participant_id}/give-up-learning`, "POST", {});
    await page.goto(new URL("/retest", base).href);
    await page.locator(".options").first().waitFor();
    await check(page, "retest", width);
    console.log(`ok ${width}px pretest learning feedback retest`);
    await context.close();
  }
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 720 } });
    const page = await context.newPage();
    await api(page.request, "/api/admin/auth/login", "POST", { password: process.env.ADMIN_PASSWORD });
    const record = await api(page.request, "/api/registrations", "POST", { assignment_code: "B", consent_checked: true, student_number: `GLOSSARY-LONG-SYNTHETIC-${width}` });
    await page.addInitScript((p) => localStorage.setItem("participant_id", p.participant_id), record);
    await page.route("**/api/experiment/*/pretest", async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      data.questions[0].glossary.entries = Array.from({ length: 30 }, (_, index) => ({ id: `test-${index}`, term: `用語${index}`, definition: "長い用語の説明を表示するための確認用の文章です。".repeat(4) }));
      await route.fulfill({ response, json: data });
    });
    await page.goto(new URL("/pretest", base).href);
    await page.locator(".options").first().waitFor();
    if (width < 1100) await page.getByRole("button", { name: "用語の補足", exact: true }).click();
    const container = page.locator(width >= 1100 ? ".glossary-sidebar" : ".glossary-dialog");
    const scrollable = await container.evaluate((el) => {
      el.scrollTop = el.scrollHeight;
      return el.scrollHeight > el.clientHeight && el.scrollTop > 0;
    });
    assert(scrollable, `${width}px long glossary must scroll internally`);
    assert(await container.getByText("用語29", { exact: true }).isVisible());
    await context.close();
    console.log(`ok ${width}px long glossary`);
  }
} finally {
  await browser.close();
}
