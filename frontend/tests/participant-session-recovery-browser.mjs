// All API responses are mocked; this test does not create or change participant records.
import assert from "node:assert/strict";

const base = new URL(process.env.PLAN_UI_BASE_URL);
assert(["localhost", "127.0.0.1"].includes(base.hostname));
const { chromium } = await import(process.env.PLAN_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const participant = "synthetic-participant";

async function checkRecovery(path, initialStatus) {
  const context = await browser.newContext({ serviceWorkers: "block" });
  try {
    let status = initialStatus;
    const requests = [];
    await context.route("**/api/**", async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      requests.push([request.method(), pathname]);
      await route.fulfill({ status, json: { detail: "Synthetic session check response" } });
    });

    const page = await context.newPage();
    await page.goto(new URL("/start", base).href);
    const startForm = page.getByRole("textbox", { name: "群割当用コード", exact: true });
    await startForm.waitFor();
    await page.evaluate((id) => {
      localStorage.setItem("participant_id", id);
      localStorage.setItem("display_code", "P999");
    }, participant);
    await page.goto(new URL(path, base).href);

    const startNew = page.getByRole("button", { name: "新しい実験を開始", exact: true });
    if (initialStatus === 503) {
      const retry = page.getByRole("button", { name: "もう一度確認", exact: true });
      await retry.waitFor();
      assert.equal(await startNew.count(), 0);
      status = 401;
      await retry.click();
    }

    await page.getByRole("heading", { name: "参加者セッションを確認できません", exact: true }).waitFor();
    assert.equal(await startForm.count(), 0);
    assert.equal(await page.evaluate(() => localStorage.getItem("participant_id")), participant);
    await startNew.click();
    await page.waitForURL("**/start");
    await startForm.waitFor();
    assert.equal(await page.evaluate(() => localStorage.getItem("participant_id")), null);
    assert.equal(await page.evaluate(() => localStorage.getItem("display_code")), null);
    assert(requests.length > 0);
    assert(requests.every(([method, pathname]) =>
      method === "GET" && pathname === `/api/participants/${participant}/current-step`
    ));
  } finally {
    await context.close();
  }
}

try {
  await checkRecovery("/start", 401);
  await checkRecovery("/consent", 503);
  await checkRecovery("/diagnosing", 401);
  await checkRecovery("/learning/transformer", 401);
  console.log("Participant session recovery browser checks passed.");
} finally {
  await browser.close();
}
