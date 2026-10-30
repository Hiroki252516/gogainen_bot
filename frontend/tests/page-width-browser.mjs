// Run only against an isolated Mock backend, never the study instance.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

if (process.env.WIDTH_VERIFY_ISOLATED !== "1" || !process.env.WIDTH_UI_BASE_URL || !process.env.WIDTH_PLAYWRIGHT_MODULE || !process.env.WIDTH_SCREENSHOT_DIR || !process.env.ADMIN_PASSWORD) {
  throw new Error("Set isolated UI, browser, screenshot directory and test admin password.");
}
const base = new URL(process.env.WIDTH_UI_BASE_URL);
assert(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname));
assert(base.port && base.port !== "3000", "Do not use the study frontend.");
const { chromium } = await import(process.env.WIDTH_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, ...(process.env.WIDTH_BROWSER_CHANNEL ? { channel: process.env.WIDTH_BROWSER_CHANNEL } : {}) });
await mkdir(process.env.WIDTH_SCREENSHOT_DIR, { recursive: true });

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

async function verify(page, view, width) {
  const dimensions = await page.evaluate(() => {
    const shell = document.querySelector(".shell").getBoundingClientRect();
    const bar = document.querySelector(".admin-lock-bar")?.getBoundingClientRect();
    const blocks = [...document.querySelectorAll(".learning-layout > .learning-block")].map((block) => block.getBoundingClientRect());
    return {
      viewport: innerWidth, shell: { width: shell.width, left: shell.left },
      bar: bar && { width: bar.width, left: bar.left },
      overflow: document.documentElement.scrollWidth > innerWidth,
      optionOverflow: [...document.querySelectorAll(".option > span")].some((span) => span.scrollWidth > span.clientWidth + 1),
      blocks: blocks.map((rect) => ({ left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom })),
    };
  });
  assert.equal(dimensions.viewport, width);
  assert(Math.abs(dimensions.shell.width - Math.min(1440, width - 32)) < 1, `${view} ${width}: shell width`);
  assert(Math.abs(dimensions.shell.left - (width - dimensions.shell.width) / 2) < 1, `${view} ${width}: shell alignment`);
  assert(!dimensions.overflow && !dimensions.optionOverflow, `${view} ${width}: horizontal overflow`);
  if (view === "admin") {
    assert(dimensions.bar && Math.abs(dimensions.bar.width - dimensions.shell.width) < 1 && Math.abs(dimensions.bar.left - dimensions.shell.left) < 1, `admin ${width}: lock bar alignment`);
  }
  if (view === "learning") {
    assert.equal(dimensions.blocks.length, 2);
    const [first, second] = dimensions.blocks;
    if (width <= 760) assert(second.top >= first.bottom, `learning ${width}: stacked blocks overlap`);
    else assert(second.left >= first.right, `learning ${width}: columns overlap`);
  }
  const expectsGiveUp = ["learning", "retest", "retest2", "final-test", "retest-results"].includes(view);
  const exit = page.locator(".app-header-give-up");
  assert.equal(await exit.count(), expectsGiveUp ? 1 : 0, `${view} ${width}: give-up visibility`);
  if (expectsGiveUp) {
    const button = exit.getByRole("button");
    assert(await button.isVisible(), `${view} ${width}: give-up visible`);
    assert.equal(await exit.evaluate((el) => getComputedStyle(el).position), "static");
    const initialOverlap = await page.evaluate(() => {
      const actions = document.querySelector(".app-header-actions");
      const giveUp = document.querySelector(".app-header-give-up");
      const adminRect = document.querySelector('a[href="/admin"]').getBoundingClientRect();
      const exitRect = giveUp.getBoundingClientRect();
      return {
        overlap: exitRect.left < adminRect.right && adminRect.left < exitRect.right && exitRect.top < adminRect.bottom && adminRect.top < exitRect.bottom,
        order: actions.children[0] === giveUp && actions.children[1]?.tagName === "A",
        adjacent: exitRect.right <= adminRect.left,
      };
    });
    assert(initialOverlap.order && initialOverlap.adjacent && !initialOverlap.overlap, `${view} ${width}: give-up must be immediately left of the admin link`);
    const initial = await exit.boundingBox();
    await page.evaluate(() => window.scrollTo(0, Math.min(350, document.documentElement.scrollHeight - innerHeight)));
    const scrolled = await exit.boundingBox();
    const scrollY = await page.evaluate(() => window.scrollY);
    assert(initial && scrolled && Math.abs(scrolled.y - (initial.y - scrollY)) <= 2, `${view} ${width}: give-up should move with the document`);
    if (scrollY > initial.y + 8) assert(scrolled.y + scrolled.height < 0, `${view} ${width}: give-up should scroll out of view`);
    const collision = await page.evaluate(() => {
      const rect = (selector) => document.querySelector(selector)?.getBoundingClientRect();
      const exitRect = rect(".app-header-give-up");
      const parentRect = document.querySelector(".app-header-actions").getBoundingClientRect();
      const sidebarRect = rect(".glossary-sidebar");
      const primaryRect = rect(".corner-primary button");
      const intersects = (a, b) => a && b && a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
      return {
        outsideContent: exitRect.left < parentRect.left || exitRect.right > parentRect.right,
        sidebar: intersects(exitRect, sidebarRect),
        primary: intersects(exitRect, primaryRect),
      };
    });
    assert(!collision.outsideContent && !collision.sidebar && !collision.primary, `${view} ${width}: overlapping controls ${JSON.stringify(collision)}`);
    await page.evaluate(() => window.scrollTo(0, 0));
    await button.focus();
    assert(await button.evaluate((el) => document.activeElement === el), `${view} ${width}: keyboard focus`);
  }
  await page.screenshot({ path: `${process.env.WIDTH_SCREENSHOT_DIR}/${view}-${width}.png`, fullPage: true });
  console.log(`ok ${view} ${width}px`);
}

try {
  for (const width of [1920, 1440, 1100, 1099, 768, 760, 390, 320]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    page.setDefaultTimeout(30000);
    await api(page.request, "/api/admin/auth/login", "POST", { password: process.env.ADMIN_PASSWORD });
    assert.equal((await api(page.request, "/api/admin/ai/status")).ai_backend, "mock");
    await api(page.request, "/api/admin/question-set", "PUT", { mode: "standard" });
    await api(page.request, "/api/admin/option-order", "PUT", { mode: "debug_fixed" });
    const participant = await api(page.request, "/api/registrations", "POST", { assignment_code: "B", consent_checked: true, student_number: `WIDTH-TEST-SYNTHETIC-${width}` });
    const pid = participant.participant_id;
    await page.addInitScript((p) => {
      localStorage.setItem("participant_id", p.participant_id);
      localStorage.setItem("display_code", p.display_code);
    }, participant);
    await page.goto(new URL("/pretest", base).href);
    await page.locator(".options").first().waitFor();
    await verify(page, "pretest", width);
    const pretestQuestions = (await api(page.request, `/api/experiment/${pid}/pretest`)).questions;
    for (const question of pretestQuestions) {
      await api(page.request, "/api/attempts", "POST", { participant_id: pid, question_id: question.question_id, selected_option_ids: question.options.filter((option) => option.exclusive).map((option) => option.option_id) });
    }
    await acknowledgeQuestionReviews(page.request, pid, "pretest", pretestQuestions);
    await api(page.request, `/api/participants/${pid}/diagnose-pretest`, "POST", {});
    await page.goto(new URL("/learning-targets", base).href);
    await page.getByRole("heading", { name: /確認結果$/ }).waitFor();
    await verify(page, "results", width);
    await page.goto(new URL("/learning/llm_knowledge", base).href);
    await page.locator(".learning-layout").waitFor();
    await verify(page, "learning", width);
    await api(page.request, `/api/participants/${pid}/give-up-learning`, "POST", {});
    await page.goto(new URL("/retest", base).href);
    await page.locator(".options").first().waitFor();
    await verify(page, "retest", width);
    const retestQuestions = (await api(page.request, `/api/experiment/${pid}/retest`)).questions;
    for (const question of retestQuestions) {
      await api(page.request, "/api/attempts", "POST", {
        participant_id: pid,
        question_id: question.question_id,
        selected_option_ids: question.options.filter((option) => option.exclusive).map((option) => option.option_id),
      });
    }
    await acknowledgeQuestionReviews(page.request, pid, "retest", retestQuestions);
    await api(page.request, `/api/participants/${pid}/score-retest`, "POST", {});
    await page.goto(new URL("/learning-targets", base).href);
    await page.getByRole("heading", { name: "再テスト1の確認結果", exact: true }).waitFor();
    await verify(page, "retest-results", width);

    if (width === 390) {
      const giveUp = page.locator(".app-header-give-up button");
      page.once("dialog", (dialog) => dialog.dismiss());
      await giveUp.click();
      assert(await giveUp.isEnabled(), "cancelled give-up should remain enabled");

      let requestStarted;
      const started = new Promise((resolve) => { requestStarted = resolve; });
      await page.route("**/api/participants/*/give-up", async (route) => {
        requestStarted();
        await new Promise((resolve) => setTimeout(resolve, 250));
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "終了処理に失敗しました。時間をおいてから再度お試しください。".repeat(4) }) });
      });
      page.once("dialog", (dialog) => dialog.accept());
      await giveUp.click();
      await started;
      assert(await giveUp.isDisabled(), "give-up should be disabled while saving");
      await page.getByRole("alert").waitFor();
      await page.waitForFunction(() => {
        const button = document.querySelector(".app-header-give-up button");
        return button && !button.disabled;
      });
      assert(await giveUp.isEnabled(), "failed give-up should allow retry");
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "long give-up error caused horizontal overflow");
      await page.unroute("**/api/participants/*/give-up");
      await page.route("**/api/participants/*/give-up", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ next_url: "/finish" }) }));
      page.once("dialog", (dialog) => dialog.accept());
      await giveUp.click();
      await page.waitForURL(/\/finish$/);
    }
    await page.goto(new URL("/learning-targets", base).href);
    await page.getByRole("heading", { name: "再テスト1の確認結果", exact: true }).waitFor();
    await api(page.request, `/api/participants/${pid}/give-up-learning`, "POST", {});
    await page.goto(new URL("/retest", base).href);
    await page.locator(".options").first().waitFor();
    await verify(page, "retest2", width);
    await page.goto(new URL("/admin", base).href);
    await page.getByLabel("パスワード", { exact: true }).fill(process.env.ADMIN_PASSWORD);
    await page.getByRole("button", { name: "管理画面を開く", exact: true }).click();
    await page.locator(".admin-lock-bar").waitFor();
    await page.locator(".shell").waitFor();
    await verify(page, "admin", width);
    await context.close();
  }
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    page.setDefaultTimeout(30000);
    await api(page.request, "/api/admin/auth/login", "POST", { password: process.env.ADMIN_PASSWORD });
    await api(page.request, "/api/admin/question-set", "PUT", { mode: "standard" });
    await api(page.request, "/api/admin/option-order", "PUT", { mode: "debug_fixed" });
    const record = await api(page.request, "/api/registrations", "POST", { assignment_code: "B", consent_checked: true, student_number: `WIDTH-FINAL-SYNTHETIC-${width}` });
    const questions = (await api(page.request, `/api/experiment/${record.participant_id}/pretest`)).questions;
    for (const question of questions) {
      const correctOption = question.options.find((option) => option.label === "A");
      assert(correctOption, "debug-fixed pretest should expose its first correct choice at A");
      await api(page.request, "/api/attempts", "POST", { participant_id: record.participant_id, question_id: question.question_id, selected_option_ids: [correctOption.option_id] });
    }
    await acknowledgeQuestionReviews(page.request, record.participant_id, "pretest", questions);
    const diagnosed = await api(page.request, `/api/participants/${record.participant_id}/diagnose-pretest`, "POST", {});
    assert.equal(diagnosed.next_step, "final_test");
    await page.addInitScript((p) => { localStorage.setItem("participant_id", p.participant_id); localStorage.setItem("display_code", p.display_code); }, record);
    await page.goto(new URL(diagnosed.next_url, base).href);
    if (diagnosed.next_url === "/learning-targets") {
      await page.getByRole("link", { name: "次のテストへ", exact: true }).click();
    }
    await page.locator(".options").first().waitFor();
    await verify(page, "final-test", width);
    await context.close();
  }
} finally {
  await browser.close();
}
