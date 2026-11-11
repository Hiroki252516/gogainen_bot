// Use only a temporary Mock backend; never submit synthetic answers to the study instance.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { newResearchCode } from "./research-code.mjs";

const { RETEST_VERIFY_ISOLATED, RETEST_UI_BASE_URL, RETEST_PLAYWRIGHT_MODULE, RETEST_SCREENSHOT_DIR, RETEST_TERM_SLUG } = process.env;
assert.equal(RETEST_VERIFY_ISOLATED, "1");
assert(RETEST_UI_BASE_URL && RETEST_PLAYWRIGHT_MODULE && RETEST_SCREENSHOT_DIR);
const base = new URL(RETEST_UI_BASE_URL);
const termSlug = RETEST_TERM_SLUG ?? "llm_knowledge";
assert(["llm_knowledge", "multi_agent", "memory_process"].includes(termSlug));
assert(["localhost", "127.0.0.1", "[::1]"].includes(base.hostname));
assert(base.port && base.port !== "3000", "Never use the study frontend.");
const { chromium } = await import(RETEST_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, channel: "chrome" });
await mkdir(RETEST_SCREENSHOT_DIR, { recursive: true });

const llmExpected = {
  "retest_v1": {
    "variant_key": "retest_v1",
    "scenario": "企業が、社員からの「パスワードを忘れた」「社内Wi-Fiにつながらない」「パソコンの電源が入らない」といった問い合わせに対応するAIを開発している。\n\nこのAIは、問い合わせ内容を「アカウント」「ネットワーク」「機器」の3種類に分類し、その分類に応じた対応手順を社員に案内する。\n\n社員への案内は、「確認すること・対応手順・注意点」の順に、わかりやすく説明する形式にそろえたい。\n\nまた、最近、社内の対応手順書が改訂されたため、開発担当者は新しい手順を案内に反映したいと考えている。さらに、担当者が正しく分類した過去の問い合わせ事例を利用して、AIの分類精度も改善したい。",
    "task": "これらの目的を実現するための開発担当者の対応として、適切なものを3つ選びなさい。",
    "choices": {
      "correct": [
        "社員が「社内Wi-Fiにつながらない」と相談したら、改訂後の対応手順書から関係する箇所を検索し、見つけた情報を元に、その内容を参考に案内を作成させる。",
        "社員への回答を「確認すること・対応手順・注意点」の順にそろえるため、AIへ渡す指示文（プロンプト）に説明する項目と順序を指定し、問い合わせへの回答時に利用する。",
        "担当者が「パスワードを忘れた→アカウント」などと確認した問い合わせ文と分類結果の組を学習用データにし、対応モデルを追加訓練して分類方法を調整する。"
      ],
      "M1": [
        "開発中、「パスワードを忘れた→アカウント」などの分類例を質問に添えるとAIが正しく分類できたため、モデル自体がその分類方法を学習したと考え、新しい会話では例を示さずに分類させる。",
        "参照用フォルダーに保存した対応手順書を最新版に差し替えると、それに合わせてAIの学習済みの重みも更新されると考え、回答時には文書を検索させない。",
        "問い合わせを3種類に分類するよう毎回同じ指示をAIへ送れば、分類を繰り返すうちにモデルの重みも調整されると考え、担当者が確認した事例を使う追加訓練は行わない。"
      ],
      "M3": [
        "担当者が確認した「パスワードを忘れた→アカウント」等の分類例を保存し、問い合わせの度にシステムが似た事例を検索してAIに渡すようにする方法を、モデル自体を追加訓練する仕組みとして扱う。",
        "改訂後の対応手順書を使ってAIを追加訓練し、そのAIが学習した内容から回答する方法を、問い合わせのたびに最新の手順書を検索して確認する方法と同じ仕組みとして扱う。",
        "社員からの質問に応じて「最新版の対応手順書を確認して答える」とAIへの共通指示文（プロンプト）に書き、その指示文を、手順書から必要な箇所を検索して取り出す仕組みと同じものとして扱う。"
      ]
    }
  },
  "retest_v2": {
  "variant_key": "retest_v2",
  "scenario": "大学が、教職員からの「学内ポータルのパスワードを忘れた」「学内VPNにつながらない」「貸与タブレットの電源が入らない」といった問い合わせに対応するAIを開発している。\n\nこのAIは、問い合わせ内容を「アカウント」「ネットワーク」「機器」の3種類に分類し、その分類に応じた対応手順を教職員に案内する。\n\n教職員への案内は、「確認すること・対応手順・注意点」の順に、わかりやすく説明する形式にそろえたい。\n\nまた、最近、学内のITサポートマニュアルが改訂されたため、開発担当者は新しい手順を案内に反映したいと考えている。さらに、担当者が正しく分類した過去の問い合わせ事例を利用して、AIの分類精度も改善したい。",
  "task": "これらの目的を実現するための開発担当者の対応として、適切なものを3つ選びなさい。",
  "choices": {
    "correct": [
      "教職員が「学内VPNにつながらない」と相談したら、改訂後のITサポートマニュアルから関係する箇所を検索し、見つけた情報を元に、その内容を参考に案内を作成させる。",
      "教職員への回答を「確認すること・対応手順・注意点」の順にそろえるため、AIへ渡す指示文（プロンプト）に説明する項目と順序を指定し、問い合わせへの回答時に利用する。",
      "担当者が「学内ポータルのパスワードを忘れた→アカウント」などと確認した問い合わせ文と分類結果の組を学習用データにし、対応モデルを追加訓練して分類方法を調整する。"
    ],
    "M1": [
      "開発中、「学内ポータルのパスワードを忘れた→アカウント」などの分類例を質問に添えるとAIが正しく分類できたため、モデル自体がその分類方法を学習したと考え、新しい会話では例を示さずに分類させる。",
      "参照用フォルダーに保存したITサポートマニュアルを最新版に差し替えると、それに合わせてAIの学習済みの重みも更新されると考え、回答時には文書を検索させない。",
      "問い合わせを3種類に分類するよう毎回同じ指示をAIへ送れば、分類を繰り返すうちにモデルの重みも調整されると考え、担当者が確認した事例を使う追加訓練は行わない。"
    ],
    "M3": [
      "担当者が確認した「学内ポータルのパスワードを忘れた→アカウント」等の分類例を保存し、問い合わせの度にシステムが似た事例を検索してAIに渡すようにする方法を、モデル自体を追加訓練する仕組みとして扱う。",
      "改訂後のITサポートマニュアルを使ってAIを追加訓練し、そのAIが学習した内容から回答する方法を、問い合わせのたびに最新のマニュアルを検索して確認する方法と同じ仕組みとして扱う。",
      "教職員からの質問に応じて「最新版のITサポートマニュアルを確認して答える」とAIへの共通指示文（プロンプト）に書き、その指示文を、マニュアルから必要な箇所を検索して取り出す仕組みと同じものとして扱う。"
    ]
  }
}
};

const fixtures = { llm_knowledge: llmExpected, ...{
  "multi_agent": {
    "retest_v1": {
      "variant_key": "retest_v1",
      "scenario": "旅行会社が、公共交通を利用する日帰り観光プランを提案するAIシステムを開発している。\n\n例えば、利用者が「午前に美術館、午後に水族館を訪れ、17時までに出発駅へ戻りたい」と希望した場合、観光候補の情報、訪問する順番や滞在時間、電車やバスの移動条件などを考慮して、実行可能な旅行計画を案内する必要がある。\n\n開発担当者は、複数のAIエージェントに仕事を分担させ、協力して旅行計画を作成する仕組みを検討している。",
      "task": "このような旅行計画AIを実現するための開発担当者の対応として、適切なものを3つ選びなさい。",
      "choices": {
        "correct": [
          "観光候補を調べるAI、訪問順や滞在時間を決めるAI、電車やバスの移動条件を確認するAIを設け、それぞれが何を調べ、何を判断するかを設定する。",
          "観光候補担当が見つけた施設や営業時間を日程担当へ渡し、日程担当が作成した訪問順と予定時刻を移動確認担当に引き継ぐ仕組みを設ける。",
          "移動確認担当が、予定された出発時刻では17時までに駅へ戻れないと判断したら、その結果を日程担当へ返し、訪問順や滞在時間を見直せるようにする。"
        ],
        "M1": [
          "観光調査・日程作成・移動確認のAIに役割を設定して個別に質問すれば、他の担当が出した結果も共有されると考え、調査内容を次の担当へ渡す仕組みは設けない。",
          "観光候補担当が選んだ施設について、日程担当が別の候補を求めると役割分担が崩れると考え、移動時間や営業時間が合わない場合も、担当間で候補の見直しを行う仕組みは設けない。",
          "観光候補担当が営業時間に合う施設を選び、移動確認担当が利用できる電車を調べれば、各担当の結果を組み合わせるだけで17時までに出発駅へ戻れると考え、計画全体の時刻は確認しない。"
        ],
        "M3": [
          "1つのAIに「観光候補」「日程」「移動」の3つの見出しで回答させれば、各見出しが別のAIの担当に当たると考え、複数のエージェントが協力する構成として扱う。",
          "電車の発着時刻だけを返す乗換検索ツールも、日程担当へ交通情報を渡す役割があるので、移動条件を判断するAIエージェントの一つとして数える。",
          "1つのAIが移動距離に応じて徒歩と電車の案内を切り替える場合、切り替え先の処理をそれぞれ独立したAIエージェントとして数え、複数のAIが連携する構成とみなす。"
        ]
      }
    },
    "retest_v2": {
  "variant_key": "retest_v2",
  "scenario": "博物館が、館内を移動する短時間の見学コースを提案するAIシステムを開発している。\n\n例えば、来館者が「最初に恐竜展示、次に化石展示を訪れ、40分以内に入口へ戻りたい」と希望した場合、展示候補の情報、見学する順番や滞在時間、展示室間の移動経路や所要時間などを考慮して、実行可能な見学計画を案内する必要がある。\n\n開発担当者は、複数のAIエージェントに仕事を分担させ、協力して見学計画を作成する仕組みを検討している。",
  "task": "このような見学計画AIを実現するための開発担当者の対応として、適切なものを3つ選びなさい。",
  "choices": {
    "correct": [
      "展示候補を調べるAI、見学順や滞在時間を決めるAI、展示室間の移動条件を確認するAIを設け、それぞれが何を調べ、何を判断するかを設定する。",
      "展示候補担当が見つけた展示室や公開時間を見学計画担当へ渡し、見学計画担当が作成した見学順と予定時刻を移動確認担当に引き継ぐ仕組みを設ける。",
      "移動確認担当が、予定された出発時刻では40分以内に入口へ戻れないと判断したら、その結果を見学計画担当へ返し、見学順や滞在時間を見直せるようにする。"
    ],
    "M1": [
      "展示調査・見学計画・移動確認のAIに役割を設定して個別に質問すれば、他の担当が出した結果も共有されると考え、調査内容を次の担当へ渡す仕組みは設けない。",
      "展示候補担当が選んだ展示について、見学計画担当が別の候補を求めると役割分担が崩れると考え、移動時間や公開時間が合わない場合も、担当間で候補の見直しを行う仕組みは設けない。",
      "展示候補担当が公開時間に合う展示を選び、移動確認担当が利用できる館内経路を調べれば、各担当の結果を組み合わせるだけで40分以内に入口へ戻れると考え、計画全体の時刻は確認しない。"
    ],
    "M3": [
      "1つのAIに「展示候補」「見学計画」「移動」の3つの見出しで回答させれば、各見出しが別のAIの担当に当たると考え、複数のエージェントが協力する構成として扱う。",
      "展示室間の所要時間だけを返す館内経路検索ツールも、見学計画担当へ移動情報を渡す役割があるので、移動条件を判断するAIエージェントの一つとして数える。",
      "1つのAIが展示室の階数に応じて階段とエレベーターの案内を切り替える場合、切り替え先の処理をそれぞれ独立したAIエージェントとして数え、複数のAIが連携する構成とみなす。"
    ]
  }
}
  },
  "memory_process": {
    "retest_v1": {
      "variant_key": "retest_v1",
      "scenario": "料理の献立を提案するAIサービスを開発している。ある利用者は以前の相談で「ピーマンは苦手なので、今後の献立には入れないでほしい」と伝えた。その後、別の日に「最近は食べられるようになったので、これからはピーマンも献立に入れてほしい」と希望を変更した。また、提案された料理について「味が濃かったので、次からは薄味にしてほしい」と感想を伝えた。開発担当者は、別の日に新しい相談が始まった場合にも、その利用者の新しい希望や過去の感想を適切に反映できる仕組みを作りたいと考えている。",
      "task": "この目的を実現するための情報の保存・利用方法として、適切な説明を3つ選びなさい。",
      "choices": {
        "correct": [
          "利用者が「ピーマンを避けたい」と話した段階で、その希望を利用者別の記録に保存し、別の日の相談でも必要に応じて取り出し、献立の提案に利用できるようにする。",
          "本人が「今後はピーマンも使ってほしい」と希望を変更したら、以前の「避けたい」という記録を現在の希望と区別して更新し、その後の献立には変更後の条件を反映する。",
          "料理への「味が濃かった」という感想から「次から薄味にしてほしい」という希望を記録し、後日の提案でも必要に応じて取り出して、味付けを考える際の参考にする。"
        ],
        "M1": [
          "過去の相談を全文保存しておけば、AIは別の日の相談でもそこに書かれた好みを自動的に把握できると考え、保存した会話から必要な情報を取り出す処理は設けない。",
          "利用者が「今後はピーマンも使ってほしい」と伝えたら、以前の「避けたい」という記録を残して新しい希望を追加し、どちらが現在の希望かを判断する仕組みがなくても、次回はAIが新しい方を使うと考える。",
          "「味が濃かった」という感想をもとにAIが一度薄味の献立を提案できれば、その改善内容は次の相談にも引き継がれると考え、感想や新しい希望を保存する処理は設けない。"
        ],
        "M3": [
          "利用者が伝えた「ピーマンを避けたい」という希望を追加訓練でモデルの重みに覚えさせる処理を、利用者別の好みを保存し、必要に応じて更新・検索する記憶管理と同じ仕組みとして扱う。",
          "以前AIが提案した「ピーマンを使わない献立」の履歴を保存し、その履歴を、利用者自身が伝えた現在の食材の希望を管理する記憶と同じものとして扱う。",
          "同じ会話で「ピーマンも使ってほしい」と伝えた後の提案に希望が反映されたため、会話中の発言を参照する仕組みを、別の日の新しい会話でも好みを保存・更新する記憶機能と同じものとして扱う。"
        ]
      }
    },
    "retest_v2": {
  "variant_key": "retest_v2",
  "scenario": "企業が、利用者からの問い合わせに対応するAIサービスを開発している。ある利用者は以前の相談で「メールは使いにくいので、今後の連絡は電話にしてほしい」と伝えた。その後、別の日に「最近はメールを使えるようになったので、これからはメールで連絡してほしい」と希望を変更した。また、送られた案内メールについて「文章が長かったので、次からは要点を先に書いてほしい」と感想を伝えた。開発担当者は、別の日に新しい相談が始まった場合にも、その利用者の新しい希望や過去の感想を適切に反映できる仕組みを作りたいと考えている。",
  "task": "この目的を実現するための情報の保存・利用方法として、適切な説明を3つ選びなさい。",
  "choices": {
    "correct": [
      "利用者が「電話で連絡してほしい」と話した段階で、その希望を利用者別の記録に保存し、別の日の相談でも必要に応じて取り出し、連絡方法の決定に利用できるようにする。",
      "本人が「今後はメールで連絡してほしい」と希望を変更したら、以前の「電話で連絡してほしい」という記録を現在の希望と区別して更新し、その後の案内には変更後の条件を反映する。",
      "案内メールへの「文章が長かった」という感想から「次からは要点を先に書いてほしい」という希望を記録し、後日の案内でも必要に応じて取り出して、文章を作成する際の参考にする。"
    ],
    "M1": [
      "過去の相談を全文保存しておけば、AIは別の日の相談でもそこに書かれた連絡方法の好みを自動的に把握できると考え、保存した会話から必要な情報を取り出す処理は設けない。",
      "利用者が「今後はメールで連絡してほしい」と伝えたら、以前の「電話で連絡してほしい」という記録を残して新しい希望を追加し、どちらが現在の希望かを判断する仕組みがなくても、次回はAIが新しい方を使うと考える。",
      "「文章が長かった」という感想をもとにAIが一度要点を先に書いた案内文を作成できれば、その改善内容は次の相談にも引き継がれると考え、感想や新しい希望を保存する処理は設けない。"
    ],
    "M3": [
      "利用者が伝えた「電話で連絡してほしい」という希望を追加訓練でモデルの重みに覚えさせる処理を、利用者別の連絡方法の好みを保存し、必要に応じて更新・検索する記憶管理と同じ仕組みとして扱う。",
      "以前AIが提案した「電話で連絡する方法」の履歴を保存し、その履歴を、利用者自身が伝えた現在の連絡方法の希望を管理する記憶と同じものとして扱う。",
      "同じ会話で「メールで連絡してほしい」と伝えた後の案内に希望が反映されたため、会話中の発言を参照する仕組みを、別の日の新しい会話でも連絡方法の好みを保存・更新する記憶機能と同じものとして扱う。"
    ]
  }
}
  }
} };
const expected = fixtures[termSlug];

async function api(request, path, method = "GET", data) {
  const response = await request.fetch(new URL(path, base).href, { method, ...(data ? { data } : {}) });
  assert(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}

async function register(request, group, layout) {
  await api(request, "/api/admin/option-order", "PUT", { mode: layout });
  return api(request, "/api/registrations", "POST", { assignment_code: group, consent_checked: true, research_code: newResearchCode() });
}

async function answerApiPhase(request, records, phase, labels) {
  const route = phase === "final_test" ? "final-test" : phase;
  const canonical = (await api(request, `/api/experiment/${records[0].participant_id}/${route}`)).questions;
  for (const record of records) {
    const questions = (await api(request, `/api/experiment/${record.participant_id}/${route}`)).questions;
    for (const [index, question] of questions.entries()) {
      const target = question.term_slug === termSlug ? labels : "ABC";
      const bodies = canonical[index].options.filter(option => target.includes(option.label)).map(option => option.body);
      await api(request, "/api/attempts", "POST", { participant_id: record.participant_id, question_id: question.question_id,
        selected_option_ids: question.options.filter(option => bodies.includes(option.body)).map(option => option.option_id) });
    }
  }
}

async function learn(request, records) {
  const turns = [];
  for (const record of records) {
    const session = await api(request, "/api/tutor-sessions", "POST", { participant_id: record.participant_id, term_slug: termSlug });
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
  for (const initialPerfect of [false, true]) {
    const name = `${termSlug}-${width}-${group}-${layout}-${initialPerfect ? "final" : "learning"}`;
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    assert.equal((await api(page.request, "/api/admin/ai/status")).ai_backend, "mock");
    const reference = await register(page.request, group, "debug_fixed");
    const created = await register(page.request, group, layout);
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
      const targetQuestion = questions.find(question => question.term_slug === termSlug);
      const source = expected[`retest_v${index}`];
      assert.equal(targetQuestion.body, source.scenario + "\n\n" + source.task);
      assert.deepEqual(targetQuestion.options.map(option => option.body).sort(), [...Object.values(source.choices).flat(), "わからない。"].sort());
      assert.equal(targetQuestion.body.split("\n\n").length, source.scenario.split("\n\n").length + 1);
      await page.goto(new URL("/" + route, base).href);
      for (const [questionIndex, question] of questions.entries()) {
        await page.getByText(question.body, { exact: true }).waitFor();
        assert.equal(await page.getByRole("checkbox").count(), 10);
        assert.equal(await page.locator(".learning-glossary").count(), 0);
        for (const option of question.options) assert.deepEqual(Object.keys(option).sort(), ["body", "exclusive", "label", "option_id"]);
        await assertLayout(page);
        if (question.term_slug === termSlug) {
          const paragraph = page.locator(".notice > p");
          assert.equal(await paragraph.evaluate(element => getComputedStyle(element).whiteSpace), "pre-wrap");
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
        const selectedLabels = question.term_slug === termSlug ? (index === 1 ? "DEF" : "GHI") : "ABC";
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
      const row = review.test_results.results.find(row => row.term_slug === termSlug);
      assert.equal(row.question_body, targetQuestion.body);
      assert.equal(row.is_correct, false);
      for (const selected of row.selected_options) assert(targetQuestion.options.some(option => option.body === selected.body && option.label === selected.label));
      if (index === 2) assert.equal(review.retest_cycle_limit_reached, true);
    }
    assert.deepEqual(errors, []);
    console.log(`ok ${name}: revised retests1/2, selection, paragraphs, review and two-test limit`);
    await context.close();
  }
} finally {
  await browser.close();
}
