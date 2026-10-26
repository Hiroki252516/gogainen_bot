// Use only a temporary Mock backend; never submit synthetic answers to the study instance.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

const { RETEST_VERIFY_ISOLATED, RETEST_UI_BASE_URL, RETEST_PLAYWRIGHT_MODULE, RETEST_SCREENSHOT_DIR } = process.env;
assert.equal(RETEST_VERIFY_ISOLATED, "1");
assert(RETEST_UI_BASE_URL && RETEST_PLAYWRIGHT_MODULE && RETEST_SCREENSHOT_DIR);
const base = new URL(RETEST_UI_BASE_URL);
assert(["localhost", "127.0.0.1", "[::1]"].includes(base.hostname));
assert(base.port && base.port !== "3000", "Never use the study frontend.");
const { chromium } = await import(RETEST_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, channel: "chrome" });
await mkdir(RETEST_SCREENSHOT_DIR, { recursive: true });

const expected = {
  "retest_v1": {
    "variant_key": "retest_v1",
    "scenario": "企業が、社員からの「パスワードを忘れた」「社内Wi-Fiにつながらない」「パソコンの電源が入らない」といった問い合わせに対応するAIを開発している。このAIは、問い合わせを「アカウント」「ネットワーク」「機器」の3種類に分類し、分類結果と対応手順を決められた形式で案内する。最近、社内の対応手順書が改訂されたため、開発担当者は新しい手順を案内に反映したい。また、担当者が正しく分類した過去の問い合わせ事例を利用して、AIの分類精度も改善したいと考えている。",
    "task": "これらの目的を実現するための開発担当者の対応として、適切なものを3つ選びなさい。",
    "choices": {
      "correct": [
        "社員が「社内Wi-Fiにつながらない」と相談したら、改訂後の対応手順書から関係する箇所を検索し、見つけた情報をAIに示して、その内容を参考に案内を作成させる。",
        "問い合わせを「アカウント」「ネットワーク」「機器」のいずれかに分類し、分類名と対応手順を指定した順番で表示するよう、AIへ渡すプロンプトに指示を加える。",
        "担当者が「パスワードを忘れた→アカウント」などと確認した問い合わせ文と分類結果の組を学習用データにし、対応モデルを追加訓練して分類方法を調整する。"
      ],
      "M1": [
        "担当者が分類した過去の問い合わせ事例を開発時に一度AIへ渡しておけば、その判断基準がモデルの重みに記憶されると考え、その後は事例を提示せずに分類させる。",
        "参照用フォルダーに保存した対応手順書を最新版に差し替えると、それに合わせてAIの学習済みの重みも更新されると考え、回答時には文書を検索させない。",
        "問い合わせを3種類に分類するよう毎回同じ指示をAIへ送れば、分類を繰り返すうちにモデルの重みも調整されると考え、担当者が確認した事例を使う追加訓練は行わない。"
      ],
      "M3": [
        "担当者が分類した問い合わせ事例を文書検索用の索引に登録し、似た質問を探せるようにする処理を、モデルの分類方法を学習させる追加訓練と同じ仕組みとして扱う。",
        "改訂された対応手順書から、社員の問い合わせに必要な箇所を探すため、モデルを追加訓練するファインチューニングを文書検索の機能として組み込む。",
        "改訂後の対応手順書の本文をAIへの共通プロンプトに記載し、そのプロンプト自体を、手順書を継続的に保存し、必要な箇所を探す文書データベースとして扱う。"
      ]
    }
  },
  "retest_v2": {
    "variant_key": "retest_v2",
    "scenario": "企業が、会議の文字起こしをもとに議事録を作成するAIを開発している。\n\n議事録には、会議で決まった内容を「決定事項・担当者・期限」の3項目に整理して記載したい。また、会議で使われた社内の略称は、改訂される用語集に載っている正式表記に統一したいと考えている。\n\n現在は、AIが作成する議事録の文章構成や表現にばらつきがあるため、担当者が内容を確認した過去の文字起こしと完成済みの議事録も改善に活用したい。",
    "task": "これらの目的を実現する開発担当者の対応として、適切なものを3つ選びなさい。",
    "choices": {
      "correct": [
        "会議の文字起こしに社内の略称が出てきた場合は、最新の用語集からその正式表記を検索し、見つかった情報をAIに参照させて議事録を作成する仕組みを設ける。",
        "文字起こしから議事録を作る際、「決定事項・担当者・期限」の順に内容を整理するよう、AIに渡す指示文（プロンプト）に書式や説明の順番を指定する。",
        "担当者が内容を確認した文字起こしと完成した議事録の組を学習用データにまとめ、追加訓練に対応するモデルを使って、議事録の文章構成やまとめ方を調整する。"
      ],
      "M1": [
        "最新の用語集を開発時に一度AIに読ませておけば、そこにある正式表記がモデルの重みに保存されると考え、その後の会議では用語集を参照させずに議事録を作る。",
        "担当者が完成させた議事録を毎回プロンプトに見本として含めて回答させれば、使用するたびにモデルの重みも調整されると考え、別途の追加訓練は行わない。",
        "最初の会議で「決定事項・担当者・期限」の順に書くよう指示すると、その書式がモデルの重みに定着すると考え、次の独立した会話では同じ指示を与えずに議事録を作らせる。"
      ],
      "M3": [
        "過去の文字起こしと完成済みの議事録を検索対象に登録し、似た会議の事例を取り出して参照させる処理を、モデルに議事録の書き方を学習させる追加訓練と同じ種類の仕組みとして扱う。",
        "議事録に社内の略称が出てきたとき、ファインチューニングの仕組みにその語を渡せば最新の用語集から正式表記を検索できると考え、文書検索機能の代わりに組み込む。",
        "最新の用語集の本文をAIへの共通の指示文（プロンプト）に含め、そのプロンプト自体を、用語集を継続的に保存・管理し、必要な表記を検索する文書データベースとして扱う。"
      ]
    }
  }
};

async function api(request, path, method = "GET", data) {
  const response = await request.fetch(new URL(path, base).href, { method, ...(data ? { data } : {}) });
  assert(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}

async function register(request, group, mode, layout) {
  await api(request, "/api/admin/question-set", "PUT", { mode });
  await api(request, "/api/admin/option-order", "PUT", { mode: layout });
  return api(request, "/api/registrations", "POST", { assignment_code: group, consent_checked: true, student_number: "LLM-RETEST-BROWSER-SYNTHETIC" });
}

async function answerApiPhase(request, records, phase, labels) {
  const route = phase === "final_test" ? "final-test" : phase;
  const canonical = (await api(request, `/api/experiment/${records[0].participant_id}/${route}`)).questions;
  for (const record of records) {
    const questions = (await api(request, `/api/experiment/${record.participant_id}/${route}`)).questions;
    for (const [index, question] of questions.entries()) {
      const target = question.term_slug === "llm_knowledge" ? labels : "ABC";
      const bodies = canonical[index].options.filter(option => target.includes(option.label)).map(option => option.body);
      await api(request, "/api/attempts", "POST", { participant_id: record.participant_id, question_id: question.question_id,
        selected_option_ids: question.options.filter(option => bodies.includes(option.body)).map(option => option.option_id) });
    }
  }
}

async function learn(request, records) {
  const turns = [];
  for (const record of records) {
    const session = await api(request, "/api/tutor-sessions", "POST", { participant_id: record.participant_id, term_slug: "llm_knowledge" });
    turns.push(await api(request, `/api/tutor-sessions/${session.tutor_session_id}/turns`, "POST", {}));
  }
  const correct = turns[0].practice_question.options.filter(option => "ABC".includes(option.label)).map(option => option.body);
  for (const turn of turns) {
    await api(request, `/api/tutor-turns/${turn.turn_id}/respond`, "POST", {
      selected_option_ids: turn.practice_question.options.filter(option => correct.includes(option.body)).map(option => option.option_id),
    });
  }
}

async function assertLayout(page) {
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "horizontal overflow");
  assert(await page.locator(".option").evaluateAll(labels => labels.every((label, index) => {
    const box = label.getBoundingClientRect();
    const input = label.querySelector("input").getBoundingClientRect();
    const text = label.querySelector("span").getBoundingClientRect();
    return text.right <= box.right + 1 && input.right <= text.left + 1
      && text.top >= box.top && text.bottom <= box.bottom + 1
      && (index === 0 || labels[index - 1].getBoundingClientRect().bottom <= box.top);
  })), "option overlap or text overflow");
}

try {
  for (const width of [1440, 390]) for (const group of ["A", "B"]) for (const layout of ["debug_fixed", "randomized"])
  for (const mode of ["standard", "easy"]) for (const initialPerfect of [false, true]) {
    const name = `${mode}-${width}-${group}-${layout}-${initialPerfect ? "final" : "learning"}`;
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    assert.equal((await api(page.request, "/api/admin/ai/status")).ai_backend, "mock");
    const reference = await register(page.request, group, mode, "debug_fixed");
    const created = await register(page.request, group, mode, layout);
    const records = [reference, created];
    await answerApiPhase(page.request, records, "pretest", initialPerfect ? "ABC" : "DEF");
    for (const record of records) await api(page.request, `/api/participants/${record.participant_id}/diagnose-pretest`, "POST", {});
    await page.addInitScript(record => {
      localStorage.setItem("participant_id", record.participant_id);
      localStorage.setItem("display_code", record.display_code);
    }, created);
    for (const index of [1, 2]) {
      const phase = index === 1 && initialPerfect ? "final_test" : "retest";
      if (phase === "retest") await learn(page.request, records);
      const route = phase === "final_test" ? "final-test" : phase;
      const canonical = (await api(page.request, `/api/experiment/${reference.participant_id}/${route}`)).questions;
      const questions = (await api(page.request, `/api/experiment/${created.participant_id}/${route}`)).questions;
      const llm = questions.find(question => question.term_slug === "llm_knowledge");
      if (mode === "standard") {
        const source = expected[`retest_v${index}`];
        assert.equal(llm.body, source.scenario + "\n\n" + source.task);
        assert.deepEqual(llm.options.map(option => option.body).sort(), [...Object.values(source.choices).flat(), "わからない。"].sort());
        assert.equal(llm.body.split("\n\n").length, index === 1 ? 2 : 4);
      }
      await page.goto(new URL("/" + route, base).href);
      for (const [questionIndex, question] of questions.entries()) {
        await page.getByText(question.body, { exact: true }).waitFor();
        assert.equal(await page.getByRole("checkbox").count(), 10);
        assert.equal(await page.locator(".learning-glossary").count(), 0);
        for (const option of question.options) assert.deepEqual(Object.keys(option).sort(), ["body", "exclusive", "label", "option_id"]);
        await assertLayout(page);
        if (question.term_slug === "llm_knowledge") {
          const paragraph = page.locator(".notice > p");
          assert.equal(await paragraph.evaluate(element => getComputedStyle(element).whiteSpace), mode === "standard" ? "pre-wrap" : "normal");
          assert.equal(await paragraph.locator("strong").count(), 0);
          await page.screenshot({ path: `${RETEST_SCREENSHOT_DIR}/${name}-retest${index}.png`, fullPage: true });
          const longest = question.options.reduce((a, b) => a.body.length > b.body.length ? a : b);
          await page.getByRole("checkbox", { name: `${longest.label}. ${longest.body}`, exact: true }).scrollIntoViewIfNeeded();
          await page.screenshot({ path: `${RETEST_SCREENSHOT_DIR}/${name}-retest${index}-long-choice.png` });
          const unknown = page.getByRole("checkbox", { name: /^J\./ });
          await unknown.check();
          assert.equal(await page.getByRole("checkbox", { checked: true }).count(), 1);
          assert.equal(await page.getByRole("checkbox", { disabled: true }).count(), 9);
          await unknown.uncheck();
        }
        const selectedLabels = question.term_slug === "llm_knowledge" ? (index === 1 ? "DEF" : "GHI") : "ABC";
        const bodies = canonical[questionIndex].options.filter(option => selectedLabels.includes(option.label)).map(option => option.body);
        for (const option of question.options.filter(option => bodies.includes(option.body))) {
          await page.getByRole("checkbox", { name: `${option.label}. ${option.body}`, exact: true }).check();
        }
        assert.equal(await page.getByRole("checkbox", { checked: true }).count(), 3);
        await page.getByRole("button", { name: questionIndex === 2 ? "完了" : "次へ", exact: true }).click();
      }
      await page.waitForURL(url => url.pathname === "/learning-targets");
      await answerApiPhase(page.request, [reference], phase, index === 1 ? "DEF" : "GHI");
      const scoreRoute = phase === "final_test" ? "score-final-test" : "score-retest";
      await api(page.request, `/api/participants/${reference.participant_id}/${scoreRoute}`, "POST", {});
      const review = await api(page.request, `/api/participants/${created.participant_id}/learning-targets`);
      assert.equal(review.post_pretest_tests_completed, index);
      const row = review.test_results.results.find(row => row.term_slug === "llm_knowledge");
      assert.equal(row.question_body, llm.body);
      assert.equal(row.is_correct, false);
      for (const selected of row.selected_options) assert(llm.options.some(option => option.body === selected.body && option.label === selected.label));
      if (index === 2) assert.equal(review.retest_cycle_limit_reached, true);
    }
    assert.deepEqual(errors, []);
    console.log(`ok ${name}: revised retests1/2, selection, paragraphs, review and two-test limit`);
    await context.close();
  }
} finally {
  await browser.close();
}
