import assert from "node:assert/strict";
import fs from "node:fs/promises";

if (process.env.CYCLE_VERIFY_ISOLATED !== "1" || !process.env.CYCLE_UI_BASE_URL || !process.env.CYCLE_PLAYWRIGHT_MODULE || !process.env.CYCLE_SCREENSHOT_DIR) {
  throw new Error("Use CYCLE_VERIFY_ISOLATED=1 with an isolated Mock database, UI URL, Playwright module, and screenshot directory.");
}
const base = new URL(process.env.CYCLE_UI_BASE_URL);
assert(["localhost", "127.0.0.1", "[::1]"].includes(base.hostname));
assert(base.port && base.port !== "3000", "Never run this against the study UI.");
await fs.mkdir(process.env.CYCLE_SCREENSHOT_DIR, { recursive: true });
const { chromium } = await import(process.env.CYCLE_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, channel: process.env.CYCLE_BROWSER_CHANNEL || undefined });
const terms = ["LLMに知識を与える方法", "マルチエージェント", "記憶プロセス"];

async function answerTest(page, labels) {
  for (let index = 0; index < terms.length; index++) {
    await page.locator(".question-heading").filter({ hasText: terms[index] }).waitFor();
    for (const label of labels) await page.getByRole("checkbox", { name: new RegExp(`^${label}\\.`) }).check();
    await page.getByRole("button", { name: index === 2 ? "完了" : "次へ", exact: true }).click();
  }
}

async function learn(page) {
  await page.getByRole("link", { name: "学習を開始", exact: true }).click();
  for (const term of terms) {
    await page.getByText(`学習内容：${term}`, { exact: false }).waitFor();
    await page.getByRole("heading", { name: "教材", exact: true }).waitFor();
    for (const label of "ABC") await page.getByRole("checkbox", { name: new RegExp(`^${label}\\.`) }).check();
    await page.getByRole("button", { name: "回答を確認", exact: true }).click();
    await page.getByText("正解です。", { exact: true }).waitFor();
    await page.getByRole("button", { name: "次へ", exact: true }).click();
  }
}

try {
  const api = await browser.newContext();
  const status = await (await api.request.get(new URL("/api/admin/ai/status", base).href)).json();
  assert.equal(status.ai_backend, "mock");
  assert.equal((await api.request.put(new URL("/api/admin/option-order", base).href, { data: { mode: "debug_fixed" } })).status(), 200);
  await api.close();
  for (const assignment of ["A", "B"]) {
    for (const initialPerfect of [false, true]) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      const page = await context.newPage();
      page.setDefaultTimeout(45_000);
      const problems = new Map();
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("response", async (response) => {
        if (response.ok() && /\/api\/experiment\/[^/]+\/(pretest|retest|final-test)$/.test(new URL(response.url()).pathname)) {
          const payload = await response.json();
          for (const q of payload.questions) problems.set(`${q.test_round}:${q.term_slug}`, q);
        }
      });
      await page.goto(new URL("/start", base).href);
      await page.getByLabel("参加コード", { exact: true }).fill(assignment);
      await page.getByRole("button", { name: "同意書を確認する", exact: true }).click();
      await page.getByRole("textbox", { name: "学籍番号（必須）" }).fill("ISSUE156-SYNTHETIC");
      await page.getByRole("checkbox", { name: "説明を読み、その内容を理解した上で、本実験に参加することに同意します。", exact: true }).check();
      const registration = page.waitForResponse((r) => r.url().endsWith("/api/registrations") && r.request().method() === "POST");
      await page.getByRole("button", { name: "同意してテストを開始", exact: true }).click();
      const { participant_id: pid } = await (await registration).json();
      await answerTest(page, initialPerfect ? "ABC" : "DEF");
      if (initialPerfect) {
        await page.getByRole("link", { name: "次のテストへ", exact: true }).click();
      } else {
        await learn(page);
      }
      await answerTest(page, "DEF");
      await page.getByRole("heading", { name: "再テスト1の確認結果", exact: true }).waitFor();
      await learn(page);
      await answerTest(page, "GHI");
      await page.getByRole("heading", { name: "再テスト2の確認結果", exact: true }).waitFor();
      await page.getByText("事前テスト後のテストを2回実施しましたが、満点には届きませんでした。", { exact: false }).waitFor();
      assert.equal(await page.getByRole("link", { name: "学習を開始", exact: true }).count(), 0);
      assert.equal(problems.size, 9);
      assert.equal(new Set([...problems.values()].map((q) => q.body)).size, 9);
      for (const q of problems.values()) {
        assert(q.body.includes("開発担当者の対応として、適切なものを3つ選びなさい。"));
        assert(q.options.every((option) => !Object.hasOwn(option, "is_correct") && !Object.hasOwn(option, "misconception_type")));
      }
      const review = await (await page.request.get(new URL(`/api/participants/${pid}/learning-targets`, base).href)).json();
      assert.equal(review.post_pretest_tests_completed, 2);
      assert.equal(review.post_pretest_test_limit, 2);
      assert.equal(review.retest_cycles_completed, initialPerfect ? 1 : 2);
      assert.equal(review.retest_cycle_limit_reached, true);
      assert(review.test_results.results.every((result) => result.is_correct === false));
      assert.equal((await page.request.get(new URL(`/api/experiment/${pid}/retest`, base).href)).status(), 409);
      for (const [name, viewport] of [["desktop", { width: 1440, height: 1000 }], ["mobile", { width: 390, height: 844 }]]) {
        await page.setViewportSize(viewport);
        await page.screenshot({ path: `${process.env.CYCLE_SCREENSHOT_DIR}/${assignment}-${initialPerfect ? "initial-perfect" : "learning"}-${name}.png`, fullPage: true });
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "horizontal overflow");
      }
      await page.getByRole("link", { name: "アンケートへ進む", exact: true }).click();
      await page.getByRole("heading", { name: "実験後アンケート", exact: true }).waitFor();
      const selects = page.locator("form select");
      await selects.first().waitFor();
      assert.equal(await selects.count(), 14);
      for (let index = 0; index < 14; index++) await selects.nth(index).selectOption(index < 4 ? "no" : "8");
      await page.getByRole("textbox", { name: "自由記述（必須）", exact: false }).fill("隔離DBでの上限確認用の合成回答です。");
      await page.getByRole("button", { name: "回答を保存して終了", exact: true }).click();
      await page.getByRole("heading", { name: "実験は終了です", exact: true }).waitFor();
      const logs = await (await page.request.get(new URL(`/api/admin/participants/${pid}/logs`, base).href)).json();
      assert.equal(logs.participant.experiment_spec_version, 6);
      assert.equal(logs.latest_evaluation_summary.hypothesis_metrics.h6.value, 0);
      assert.equal(logs.attempts.length, 9);
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.goto(new URL("/admin", base).href);
      await page.getByRole("tab", { name: assignment === "A" ? "proposed" : "control", exact: true }).click();
      const row = page.getByRole("row").filter({ hasText: logs.participant.display_code }).filter({ has: page.getByRole("button", { name: "被験者ログを見る", exact: true }) });
      await row.waitFor();
      assert((await row.innerText()).includes("2 / 2"));
      await row.getByRole("button", { name: "被験者ログを見る", exact: true }).click();
      await page.getByText("事前テスト後のテスト: 2 / 2回（学習前の追加テストを含む）", { exact: true }).waitFor();
      assert.equal(await page.getByText(`学習後の再テスト: ${initialPerfect ? 1 : 2}回`, { exact: true }).count(), 1);
      assert.equal(errors.length, 0, errors.join("\n"));
      console.log(JSON.stringify({ assignment, initialPerfect, participant_id: pid, tests: problems.size / 3, post_tests: 2, raw_retests: review.retest_cycles_completed, flow: "passed" }));
      await context.close();
    }
  }
} finally {
  await browser.close();
}
