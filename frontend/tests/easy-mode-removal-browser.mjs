import assert from "node:assert/strict";
import { newResearchCode } from "./research-code.mjs";

if (process.env.CYCLE_VERIFY_ISOLATED !== "1" || !process.env.CYCLE_UI_BASE_URL || !process.env.CYCLE_PLAYWRIGHT_MODULE) {
  throw new Error("Use an isolated Mock backend and an explicit non-study UI URL.");
}
const base = new URL(process.env.CYCLE_UI_BASE_URL);
assert(["localhost", "127.0.0.1", "[::1]"].includes(base.hostname));
assert(base.port && base.port !== "3000");
const { chromium } = await import(process.env.CYCLE_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, channel: process.env.CYCLE_BROWSER_CHANNEL || undefined });

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.goto(new URL("/admin", base).href);
  await page.getByLabel("パスワード", { exact: true }).fill(process.env.ADMIN_PASSWORD || "abc");
  await page.getByRole("button", { name: "管理画面を開く", exact: true }).click();
  const body = await page.locator("body").innerText();
  assert(!body.includes("易しい版"));
  assert(!body.includes("問題版"));
  assert(!body.includes("集計する問題版"));

  assert.equal((await page.request.get(new URL("/api/admin/question-set", base).href)).status(), 404);
  assert.equal((await page.request.put(new URL("/api/admin/question-set", base).href, { data: { mode: "easy" } })).status(), 404);
  for (const path of [
    "/api/admin/evaluation-summary?question_set_mode=easy",
    "/api/admin/logs/overview?question_set_mode=easy",
    "/api/admin/export/hypothesis_metrics.csv?question_set_mode=easy",
    "/api/admin/export/hypothesis_group_summary.xlsx?question_set_mode=easy",
  ]) assert.equal((await page.request.get(new URL(path, base).href)).status(), 422, path);

  const registration = await page.request.post(new URL("/api/registrations", base).href, {
    data: { assignment_code: "B", consent_checked: true, research_code: newResearchCode() },
  });
  assert.equal(registration.status(), 200);
  const participant = await registration.json();
  const questionResponse = await page.request.get(new URL(`/api/experiment/${participant.participant_id}/pretest`, base).href);
  assert.equal(questionResponse.status(), 200);
  assert.equal((await questionResponse.json()).questions.length, 6);
  console.log("easy-mode routes removed; standard registration and six-question pretest remain");
} finally {
  await browser.close();
}
