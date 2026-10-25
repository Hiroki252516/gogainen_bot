// Synthetic responses belong only in a separate Mock database.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

const { LEARNING_VERIFY_ISOLATED, LEARNING_UI_BASE_URL, LEARNING_PLAYWRIGHT_MODULE, LEARNING_SCREENSHOT_DIR, LEARNING_TERM_SLUG, LEARNING_VARIANT_INDEX, LEARNING_QUESTION_SET_MODE } = process.env;
assert.equal(LEARNING_VERIFY_ISOLATED, "1");
assert(LEARNING_UI_BASE_URL && LEARNING_PLAYWRIGHT_MODULE && LEARNING_SCREENSHOT_DIR);
const base = new URL(LEARNING_UI_BASE_URL);
const termSlug = LEARNING_TERM_SLUG ?? "llm_knowledge";
const variantIndex = Number(LEARNING_VARIANT_INDEX ?? 1);
const questionSet = LEARNING_QUESTION_SET_MODE ?? "standard";
assert([1, 2].includes(variantIndex));
assert(["standard", "easy"].includes(questionSet));
assert(variantIndex === 1 || termSlug === "multi_agent");
assert(questionSet === "standard" || (termSlug === "multi_agent" && variantIndex === 2));
assert(["llm_knowledge", "multi_agent"].includes(termSlug));
assert(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname));
assert(base.port && base.port !== "3000", "Never use the study frontend.");
const { chromium } = await import(LEARNING_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, channel: "chrome" });
await mkdir(LEARNING_SCREENSHOT_DIR, { recursive: true });
const llmBodies = [
  "利用者の質問に応じて履修規程の該当箇所を検索し、質問と一緒にAIへ渡して回答を作らせる。",
  "「必要な手続き・提出期限・注意点」の順に説明するよう、AIへ渡すプロンプトに指示を加える。",
  "担当者が確認した質問と回答の例を学習用データにして、AIを追加訓練する。",
  "履修規程を一度AIへ渡せば、その内容がモデルの重みに保存され、以後は検索しなくてもよい。",
  "回答例を毎回の質問に加えれば、学習用データによる訓練をしなくてもモデルの重みを調整できる。",
  "回答の順番を指示する文章をプロンプトに加えることで、モデルの重みを更新する。",
  "回答例をRAGの検索対象に登録すれば、回答方法の追加訓練が完了する。",
  "履修規程の該当箇所を探すには、文書検索ではなくファインチューニングを使う。",
  "履修規程の本文をプロンプトに含めれば、プロンプト自体を文書の保存・検索先として使える。",
];
const llmQuestionBody = "大学の履修案内AIに、更新された履修規程を使わせたい。回答は「必要な手続き・提出期限・注意点」の順にそろえ、担当者が確認した質問と回答の例も改善に利用したい。\n\n担当者の対応として、適切なものを3つ選びなさい。";

const multiBodies = [
  "被害状況や道路の情報を集めるAIが調査結果を避難方法の検討担当へ渡し、その検討結果を避難案内文作成担当に引き継ぐようにすれば、複数のAIが分担した作業を順番に繋げられる。",
  "情報収集担当が被害状況と道路の通行状況を整理して避難方法の検討担当に共有し、検討担当がその情報を自分の作業に利用することで、異なる役割のAIが協力して避難案内を作れる。",
  "避難方法の検討担当から避難経路の候補を受け取った避難案内文作成担当は、その情報を参考にして、住民に何をどのような順番で伝えるかを自分の役割として判断できる。",
  "情報収集担当のAIが道路の通行状況を調べて避難方法の検討担当へ渡した場合、検討担当は情報源が十分に確認されていると考え、その報告をもとに避難経路を決める。",
  "情報収集担当、避難方法の検討担当、避難案内文作成担当という役割名を各AIに付ければ、どの情報をどの順番で渡すかも自動的に決まるので、受け渡しの仕組みを設計する必要はない。",
  "情報収集担当が道路の通行状況を報告し、避難案内文作成担当がその情報を使って説明を作る場合でも、両者が同じ回答内容を出さなければ、結果を引き継いで連携することはできない。",
  "情報収集担当のAIが被害状況や道路の情報をまとめたファイルは、避難方法の検討担当に情報を渡すために使われるので、そのファイルも連携するAIエージェントの一つとして数える。",
  "1つのAIエージェントに、道路が通れる場合と通れない場合で避難案内内容を切り替える仕組みを設け、案内の方法が2つあるので、AIエージェントも2つ存在する。",
  "性能の高いAIエージェントを1つ用意し、情報収集、避難方法の検討、住民向けの避難案内文作成をすべて担当させれば、複数のエージェントが連携するマルチエージェントの仕組みになる。"
];
const multiQuestionBody = "自治体が、災害時に住民向けの避難案内を作成するAIシステムを開発している。このシステムでは、被害状況や道路の情報を集めるAI、集めた情報をもとに避難方法を検討するAI、検討結果から住民向けの案内文を作成するAIにそれぞれ役割を分け、前の担当が出した結果を次の担当に引き継いで案内を行うシステムを作っている。\n\nこの仕組みを説明する記述を3つ選びなさい。";
const roundTwoBodies = [
  "案2では、情報収集担当のAIが集めた道路情報を避難方法の検討担当へ渡し、その検討結果を避難案内文作成担当へ引き継ぐことで、異なる担当の作業を一つの案内作成に繋げられる。",
  "案1では1つのAIが調査から避難案内文の作成まで担当するが、案2では役割ごとに別のAIを設けるため、各担当に異なる指示や必要な資料を設定する構成にできる。",
  "案2で複数のAIを連携させるには、どの担当から次の担当へ何を渡すかを決め、受け取った結果を各AIの作業に利用できるよう、情報の受け渡し方を設計する。",
  "案2では、道路情報の調査を専門に担当するAIを設けているため、調査内容の信頼性も確保されており、避難方法の検討担当はその報告を確認せずに利用する。",
  "案2では、情報収集担当がまとめた道路情報を避難計画担当へ渡しておけば、避難計画担当の役割に必要な情報が自動的に選ばれて届くと考え、受け渡す情報の内容は特に指定しない。",
  "案2で情報収集担当が「道路Aは通行可能」と報告し、避難計画担当が「避難には道路Bを使う」と判断した場合、担当同士の結論が一致していないため、両者の判断をそろえなければ連携を続けられない。",
  "案1では、1つのAIが情報収集、避難方法の検討、避難案内文の作成を3つの手順に分けて行っているため、3つのAIエージェントが連携している構成として分類できる。",
  "案2では、情報収集担当が作成した道路情報の報告ファイルも、計画担当が避難方法を判断する際に利用されるため、調査担当や避難計画担当と同じく、連携するAIエージェントの一つとして数える。",
  "案2で3つのAIに作業を分担させることは、1つのAIモデルの内部計算を複数に分割して処理速度を上げる方式と同じ種類の仕組みであると考える。"
];
const roundTwoQuestionBody = "自治体が、被害状況や道路の情報をもとに、住民向けの避難案内を作成するAIシステムについて、次の2つの設計を比較している。\n\n案1： 1つのAIエージェントが、情報収集、避難方法の検討、住民向け案内文の作成を順番に行う。\n\n案2： 情報収集、避難方法の検討、案内文の作成をそれぞれ別のAIエージェントに担当させ、前の担当の結果を次の担当へ引き継ぐ。\n\n案1から案2に変更した場合の仕組みの違いについて、適切な説明を3つ選びなさい。";
const easyRoundTwoBodies = [
  "結果を渡す機能がないので、予定の担当が調査結果を使えるとは限らない。",
  "役割を分けるだけでなく、どの情報を渡すか決める必要がある。",
  "担当が別々の判断をしても、結果を受け渡して一つの案を作れる。",
  "二つのAIがあるので、調査結果も自動で予定の担当へ伝わると考える。",
  "役割名があれば渡す内容も順番も決まるので、共有の設計は省けると考える。",
  "調査役が得た情報なので、確認せず予定に使っても正しいと考える。",
  "調査結果の文章を担当AIの一人と数え、文章自体に予定を判断させる。",
  "指示の中で手順を二つに分けたものを、別々の主体による協力として扱う。",
  "複数のAIの連携を、一つのモデルの処理速度を上げる機能として扱う。"
];
const easyRoundTwoQuestionBody = "調査するAIと予定を作るAIを用意した。しかし調査結果を予定の担当へ送る処理は作っていない。\n\nこの場面について正しい説明を3つ選びなさい。";
const bodies = questionSet === "easy" ? easyRoundTwoBodies : variantIndex === 2 ? roundTwoBodies : termSlug === "multi_agent" ? multiBodies : llmBodies;
const questionBody = questionSet === "easy" ? easyRoundTwoQuestionBody : variantIndex === 2 ? roundTwoQuestionBody : termSlug === "multi_agent" ? multiQuestionBody : llmQuestionBody;

async function assertQuestionLayout(page) {
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert(await page.locator(".problem-block .option").evaluateAll((labels) => labels.every((label, index) => {
    const box = label.getBoundingClientRect();
    const text = label.querySelector("span").getBoundingClientRect();
    return text.left >= box.left && text.right <= box.right + 1 && text.top >= box.top && text.bottom <= box.bottom + 1
      && (index === 0 || labels[index - 1].getBoundingClientRect().bottom <= box.top);
  })));
}

async function api(request, path, method = "GET", data) {
  const response = await request.fetch(new URL(path, base).href, { method, ...(data ? { data } : {}) });
  assert(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}

try {
  for (const width of [1440, 390]) for (const group of ["A", "B"]) for (const layout of ["debug_fixed", "randomized"]) for (const role of ["unknown", "M1", "M3"]) {
    const caseName = `${termSlug}-${questionSet}-round${variantIndex}-${width}-${group}-${layout}-${role}`;
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    assert.equal((await api(page.request, "/api/admin/ai/status")).ai_backend, "mock");
    await api(page.request, "/api/admin/question-set", "PUT", { mode: questionSet });
    await api(page.request, "/api/admin/option-order", "PUT", { mode: layout });
    const created = await api(page.request, "/api/registrations", "POST", { assignment_code: group, consent_checked: true, student_number: "LEARNING-BROWSER-SYNTHETIC" });
    const questions = (await api(page.request, `/api/experiment/${created.participant_id}/pretest`)).questions;
    const pretestLabels = role === "unknown" ? "J" : role === "M1" ? "DEF" : "GHI";
    // Get the source option bodies from a separate debug-fixed participant, not from public correctness metadata.
    await api(page.request, "/api/admin/option-order", "PUT", { mode: "debug_fixed" });
    const reference = await api(page.request, "/api/registrations", "POST", { assignment_code: group, consent_checked: true, student_number: "LEARNING-BROWSER-REFERENCE" });
    const canonical = (await api(page.request, `/api/experiment/${reference.participant_id}/pretest`)).questions;
    for (const [index, question] of questions.entries()) {
      const labels = question.term_slug === termSlug ? pretestLabels : "ABC";
      const selectedBodies = canonical[index].options.filter((option) => labels.includes(option.label)).map((option) => option.body);
      await api(page.request, "/api/attempts", "POST", { participant_id: created.participant_id, question_id: question.question_id, selected_option_ids: question.options.filter((option) => selectedBodies.includes(option.body)).map((option) => option.option_id) });
    }
    await api(page.request, `/api/participants/${created.participant_id}/diagnose-pretest`, "POST", {});

    if (variantIndex === 2) {
      for (const [index, question] of canonical.entries()) {
        const labels = question.term_slug === termSlug ? pretestLabels : "ABC";
        await api(page.request, "/api/attempts", "POST", { participant_id: reference.participant_id, question_id: question.question_id, selected_option_ids: question.options.filter((option) => labels.includes(option.label)).map((option) => option.option_id) });
      }
      await api(page.request, `/api/participants/${reference.participant_id}/diagnose-pretest`, "POST", {});
      const firstTurns = [];
      for (const participant of [created, reference]) {
        const session = await api(page.request, "/api/tutor-sessions", "POST", { participant_id: participant.participant_id, term_slug: termSlug });
        firstTurns.push(await api(page.request, `/api/tutor-sessions/${session.tutor_session_id}/turns`, "POST", {}));
      }
      const correctBodies = firstTurns[1].practice_question.options.filter((option) => "ABC".includes(option.label)).map((option) => option.body);
      for (const turn of firstTurns) {
        assert.equal(turn.practice_question.learning_variant_index, 1);
        await api(page.request, `/api/tutor-turns/${turn.turn_id}/respond`, "POST", { selected_option_ids: turn.practice_question.options.filter((option) => correctBodies.includes(option.body)).map((option) => option.option_id) });
      }
      const retest = (await api(page.request, `/api/experiment/${created.participant_id}/retest`)).questions;
      const canonicalRetest = (await api(page.request, `/api/experiment/${reference.participant_id}/retest`)).questions;
      for (const [index, question] of retest.entries()) {
        const labels = question.term_slug === termSlug ? pretestLabels : "ABC";
        const source = canonicalRetest[index];
        const selectedBodies = source.options.filter((option) => labels.includes(option.label)).map((option) => option.body);
        await api(page.request, "/api/attempts", "POST", { participant_id: created.participant_id, question_id: question.question_id, selected_option_ids: question.options.filter((option) => selectedBodies.includes(option.body)).map((option) => option.option_id) });
        await api(page.request, "/api/attempts", "POST", { participant_id: reference.participant_id, question_id: source.question_id, selected_option_ids: source.options.filter((option) => selectedBodies.includes(option.body)).map((option) => option.option_id) });
      }
      for (const participant of [created, reference]) {
        const scored = await api(page.request, `/api/participants/${participant.participant_id}/score-retest`, "POST", {});
        assert.equal(scored.post_pretest_tests_completed, 1);
        assert.equal(scored.next_step, "learning_targets");
      }
    }
    await page.addInitScript((record) => {
      localStorage.setItem("participant_id", record.participant_id);
      localStorage.setItem("display_code", record.display_code);
      localStorage.setItem("learning_targets", JSON.stringify([record.termSlug]));
    }, { ...created, termSlug });
    const materialResponse = page.waitForResponse((response) => /\/api\/tutor-sessions\/[^/]+\/turns$/.test(response.url()));
    await page.goto(new URL(`/learning/${termSlug}`, base).href);
    const material = await (await materialResponse).json();
    const question = material.practice_question;
    assert.equal(question.body, questionBody);
    assert.equal(question.learning_variant_index, variantIndex);
    assert.deepEqual(question.options.map((option) => option.body).sort(), [...bodies, "わからない。"].sort());
    for (const option of question.options) assert.deepEqual(Object.keys(option).sort(), ["body", "exclusive", "label", "option_id"]);
    await page.getByText(questionBody, { exact: true }).waitFor();
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => document.fonts.ready);
    await assertQuestionLayout(page);
    const preserveLines = questionSet === "standard" && termSlug === "multi_agent" && variantIndex === 2;
    assert.equal(await page.locator(".problem-block > p").evaluate((element) => getComputedStyle(element).whiteSpace), preserveLines ? "pre-wrap" : "normal");
    assert.equal(await page.locator(".problem-block > p strong").count(), 0);
    await page.screenshot({ path: `${LEARNING_SCREENSHOT_DIR}/${caseName}-question.png`, fullPage: true });
    const lastChoice = question.options.find((option) => option.body === bodies[8]);
    await page.getByRole("checkbox", { name: `${lastChoice.label}. ${lastChoice.body}`, exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${LEARNING_SCREENSHOT_DIR}/${caseName}-long-choice.png` });
    const unknown = page.getByRole("checkbox", { name: /^J\./ });
    await unknown.check();
    assert.equal(await page.getByRole("checkbox", { checked: true }).count(), 1);
    await unknown.uncheck();
    const responseRole = role === "M3" ? "correct" : role === "M1" ? "unknown" : "mixed";
    const selectedBodies = responseRole === "correct" ? bodies.slice(0, 3) : responseRole === "unknown" ? ["わからない。"] : [bodies[0], bodies[3], bodies[6]];
    for (const option of question.options.filter((option) => selectedBodies.includes(option.body))) {
      await page.getByRole("checkbox", { name: `${option.label}. ${option.body}`, exact: true }).check();
    }
    const feedbackResponse = page.waitForResponse((response) => /\/api\/tutor-turns\/[^/]+\/respond$/.test(response.url()));
    await page.getByRole("button", { name: "回答を確認", exact: true }).click();
    await feedbackResponse;
    await page.getByText(responseRole === "correct" ? "正解です。" : "不正解です。", { exact: true }).waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: `${LEARNING_SCREENSHOT_DIR}/${caseName}.png`, fullPage: true });
    if (responseRole !== "correct") {
      await page.getByRole("button", { name: "次の確認へ", exact: true }).click();
      await page.getByRole("button", { name: "回答を確認", exact: true }).waitFor();
      assert.equal(await page.getByText(questionBody, { exact: true }).count(), 1);
      assert.equal(await page.getByRole("checkbox").count(), 10);
    }
    console.log(`ok ${termSlug} ${questionSet} round${variantIndex} ${width}px ${group} ${layout} ${role} -> ${responseRole}`);
    await context.close();
  }
} finally {
  await browser.close();
}
