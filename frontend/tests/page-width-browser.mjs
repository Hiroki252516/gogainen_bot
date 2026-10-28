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
  await page.screenshot({ path: `${process.env.WIDTH_SCREENSHOT_DIR}/${view}-${width}.png`, fullPage: true });
  console.log(`ok ${view} ${width}px`);
}

try {
  for (const width of [1920, 1440, 768, 760, 390, 320]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    page.setDefaultTimeout(30000);
    await api(page.request, "/api/admin/auth/login", "POST", { password: process.env.ADMIN_PASSWORD });
    assert.equal((await api(page.request, "/api/admin/ai/status")).ai_backend, "mock");
    await api(page.request, "/api/admin/question-set", "PUT", { mode: "standard" });
    await api(page.request, "/api/admin/option-order", "PUT", { mode: "debug_fixed" });
    const participant = await api(page.request, "/api/registrations", "POST", { assignment_code: "B", consent_checked: true, student_number: "WIDTH-TEST-SYNTHETIC" });
    const pid = participant.participant_id;
    await page.addInitScript((p) => {
      localStorage.setItem("participant_id", p.participant_id);
      localStorage.setItem("display_code", p.display_code);
    }, participant);
    await page.goto(new URL("/pretest", base).href);
    await page.locator(".options").waitFor();
    await verify(page, "pretest", width);
    for (const question of (await api(page.request, `/api/experiment/${pid}/pretest`)).questions) {
      await api(page.request, "/api/attempts", "POST", { participant_id: pid, question_id: question.question_id, selected_option_ids: question.options.filter((option) => option.exclusive).map((option) => option.option_id) });
    }
    await api(page.request, `/api/participants/${pid}/diagnose-pretest`, "POST", {});
    await page.goto(new URL("/learning-targets", base).href);
    await page.getByRole("heading", { name: /確認結果$/ }).waitFor();
    await verify(page, "results", width);
    await page.goto(new URL("/learning/llm_knowledge", base).href);
    await page.locator(".learning-layout").waitFor();
    await verify(page, "learning", width);
    await api(page.request, `/api/participants/${pid}/give-up-learning`, "POST", {});
    await page.goto(new URL("/retest", base).href);
    await page.locator(".options").waitFor();
    await verify(page, "retest", width);
    await page.goto(new URL("/admin", base).href);
    await page.getByLabel("パスワード", { exact: true }).fill(process.env.ADMIN_PASSWORD);
    await page.getByRole("button", { name: "管理画面を開く", exact: true }).click();
    await page.locator(".admin-lock-bar").waitFor();
    await page.locator(".shell").waitFor();
    await verify(page, "admin", width);
    await context.close();
  }
} finally {
  await browser.close();
}
