import assert from "node:assert/strict";
import fs from "node:fs/promises";

if (process.env.CYCLE_REAL_AI_VERIFY !== "1" || process.env.CYCLE_VERIFY_ISOLATED !== "1" || !process.env.CYCLE_UI_BASE_URL || !process.env.CYCLE_PLAYWRIGHT_MODULE || !process.env.CYCLE_SCREENSHOT_DIR) throw new Error("Use explicit real-AI verification with an isolated database.");
const base = new URL(process.env.CYCLE_UI_BASE_URL);
assert(["localhost", "127.0.0.1"].includes(base.hostname) && base.port && base.port !== "3000");
const { chromium } = await import(process.env.CYCLE_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, channel: process.env.CYCLE_BROWSER_CHANNEL || undefined });
try {
  await fs.mkdir(process.env.CYCLE_SCREENSHOT_DIR, { recursive: true });
  for (const group of ["A", "B"]) {
    for (const labels of ["J", "DEF", "GHI"]) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      const api = context.request;
      const url = (path) => new URL(path, base).href;
      assert.equal((await (await api.get(url("/api/admin/ai/status"))).json()).ai_backend, "codex_app_server");
      assert.equal((await api.put(url("/api/admin/question-set"), { data: { mode: "easy" } })).status(), 200);
      assert.equal((await api.put(url("/api/admin/option-order"), { data: { mode: "debug_fixed" } })).status(), 200);
      async function post(path, data = {}) {
        const response = await api.post(url(path), { data, timeout: 300_000 });
        assert.equal(response.status(), 200, await response.text());
        return response.json();
      }
      const { participant_id: pid } = await post("/api/participants", { assignment_code: group, consent_checked: true, student_number: "EASY-REAL-BROWSER-SYNTHETIC" });
      const questions = (await (await api.get(url(`/api/experiment/${pid}/pretest`))).json()).questions;
      for (const q of questions) {
        const wanted = q.term_slug === "llm_knowledge" ? labels : "ABC";
        await post("/api/attempts", { participant_id: pid, question_id: q.question_id, selected_option_ids: q.options.filter((o) => wanted.includes(o.label)).map((o) => o.option_id) });
      }
      await post(`/api/participants/${pid}/diagnose-pretest`);
      await context.addInitScript((id) => localStorage.setItem("participant_id", id), pid);
      const page = await context.newPage();
      page.setDefaultTimeout(300_000);
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      const initial = page.waitForResponse((r) => /\/api\/tutor-sessions\/[^/]+\/turns$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
      await page.goto(url("/learning/llm_knowledge"));
      const initialResponse = await initial;
      assert.equal(initialResponse.status(), 200, await initialResponse.text());
      const turn = await initialResponse.json();
      await page.getByRole("heading", { name: "教材", exact: true }).waitFor();
      assert(turn.tutor_message.length >= 600 && turn.tutor_message.length <= 800);
      assert(turn.practice_question.body.includes("新しい説明書"));
      for (const [name, viewport] of [["desktop", { width: 1440, height: 1000 }], ["mobile", { width: 390, height: 844 }]]) {
        await page.setViewportSize(viewport);
        await page.screenshot({ path: `${process.env.CYCLE_SCREENSHOT_DIR}/real-${group}-${labels}-${name}.png`, fullPage: true });
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      }
      for (const l of "GHI") await page.getByRole("checkbox", { name: new RegExp(`^${l}\\.`) }).check();
      await page.getByRole("button", { name: "回答を確認", exact: true }).click();
      await page.getByText("不正解です。", { exact: true }).waitFor();
      await page.getByRole("button", { name: "次の確認へ", exact: true }).click();
      await page.getByRole("button", { name: "回答を確認", exact: true }).waitFor();
      for (const l of "ABC") await page.getByRole("checkbox", { name: new RegExp(`^${l}\\.`) }).check();
      await page.getByRole("button", { name: "回答を確認", exact: true }).click();
      await page.getByText("正解です。", { exact: true }).waitFor();
      const logs = (await (await api.get(url(`/api/admin/participants/${pid}/logs`))).json());
      const calls = logs.ai_call_logs;
      assert(calls.some((c) => c.purpose === "generate_correct_answer_summary"));
      assert(calls.some((c) => c.purpose === "explain_selected_distractor"));
      for (const call of calls) {
        assert.equal(call.provider, "codex_app_server");
        const sent = call.request_payload.effective_request.actual_ai_input;
        assert.equal(sent.explanation_level, "beginner");
        assert.equal(call.request_payload.question_set_mode, "easy");
        if (group === "B") assert(!Object.keys(sent).some((k) => ["misconception_taxonomy", "learner_state", "pretest_targets", "active_misconception_type", "learning_stage"].includes(k)));
      }
      assert.equal(errors.length, 0, errors.join("\n"));
      console.log(JSON.stringify({ group, labels, participant_id: pid, characters: turn.tutor_message.length, real_ai_browser: "passed" }));
      await context.close();
    }
  }
} finally {
  await browser.close();
}
