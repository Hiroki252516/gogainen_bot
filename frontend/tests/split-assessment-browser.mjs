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

try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    page.setDefaultTimeout(30000);
    await api(page.request, "/api/admin/auth/login", "POST", { password: process.env.ADMIN_PASSWORD });
    assert.equal((await api(page.request, "/api/admin/ai/status")).ai_backend, "mock");
    await api(page.request, "/api/admin/question-set", "PUT", { mode: "standard" });
    await api(page.request, "/api/admin/option-order", "PUT", { mode: "debug_fixed" });
    const participant = await api(page.request, "/api/registrations", "POST", { assignment_code: "B", consent_checked: true, student_number: "SPLIT-BROWSER-SYNTHETIC" });
    await page.addInitScript((p) => { localStorage.setItem("participant_id", p.participant_id); localStorage.setItem("display_code", p.display_code); }, participant);
    await page.goto(new URL("/pretest", base).href);
    for (let i = 0; i < 6; i++) {
      await page.getByRole("radio", { name: /^D\./ }).check();
      assert.equal(await page.getByRole("radio").count(), 4);
      if (i === 0) await page.screenshot({ path: `${directory}/pretest-${width}.png`, fullPage: true });
      await page.getByRole("button", { name: i === 5 ? "完了" : "次へ", exact: true }).click();
      if (i < 5) await page.getByText(`${i + 2} / 6`, { exact: true }).waitFor();
    }
    await page.waitForURL(/\/learning-targets$/);
    for (const slug of ["llm_knowledge", "multi_agent", "memory_process"]) {
      await page.goto(new URL(`/learning/${slug}`, base).href);
      const groups = page.locator(".problem-block .options");
      await groups.first().waitFor();
      assert.equal(await groups.count(), 2);
      for (let i = 0; i < 2; i++) await groups.nth(i).getByRole("radio", { name: /^D\./ }).check();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: `${directory}/${slug}-${width}.png`, fullPage: true });
      await page.getByRole("button", { name: "回答を確認", exact: true }).click();
      await page.getByText("不正解です。", { exact: true }).waitFor();
      await page.getByRole("button", { name: "次へ", exact: true }).click();
    }
    await page.waitForURL(/\/retest$/);
    assert.equal((await api(page.request, `/api/experiment/${participant.participant_id}/retest`)).questions.length, 6);
    await context.close();
    console.log(`ok ${width}px pretest, three grouped lessons, retest`);
  }
} finally {
  await browser.close();
}
