// Use only a temporary Mock backend; never submit synthetic answers to the study instance.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

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
          "観光候補担当が人気順に並べた施設は、その順番も日程担当が引き継ぐべきだと考え、移動時間に合わせて訪問順を変更する必要があっても、元の並びを優先する。",
          "移動確認担当が前日に調べた電車の運行情報は、旅行当日もそのまま使えると考え、計画を案内する直前に運休や時刻変更がないかを確認する仕組みは設けない。"
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
      "scenario": "博物館が、来館者に短い見学コースを提案するAIシステムを開発している。ある来館者は「恐竜の展示を優先したい。化石も見られるとうれしい。見学時間は40分以内にしたい」と希望している。博物館には、展示ごとの内容、展示室の場所、見学時間の目安をまとめた資料がある。開発担当者は、複数のAIエージェントを協力させ、来館者の希望と時間の制限に合う見学案を作りたいと考えている。",
      "task": "このAIシステムで複数のAIエージェントを協力させる設計として、適切な記述を3つ選びなさい。",
      "choices": {
        "correct": [
          "来館者の希望を整理するAIと、展示の内容・場所・見学時間を調べるAIを別々に設け、それぞれの担当が何をまとめ、どの情報を次の担当へ渡すかをあらかじめ設計する。",
          "希望整理担当が「恐竜を優先し、40分以内で見たい」とまとめた結果を展示調査担当へ渡し、その条件をもとに展示の内容や見学時間を調べて候補を選べるようにする。",
          "展示調査担当が挙げた候補と希望整理担当がまとめた条件を照らし合わせ、全部見ると40分を超える場合は候補の変更や見学順の調整を依頼し、無理のない案を作れるようにする。"
        ],
        "M1": [
          "希望整理と展示調査を別々のAIに担当させれば、各AIはほかの担当がまとめた内容も把握できると考え、希望や展示候補を受け渡すための情報共有の仕組みは用意しない。",
          "希望整理担当が「恐竜を優先」とまとめたなら、展示調査担当も同じ内容の結論を返すことが連携の条件だと考え、展示の場所や所要時間を調べて異なる情報を示すことは避ける。",
          "展示調査担当が候補として挙げた展示は、来館者の希望や40分の制限にも合っていると考え、希望整理担当がまとめた条件と候補の所要時間を照らし合わせず、そのまま案内へ採用する。"
        ],
        "M3": [
          "1つのAIに「希望整理役として考え、次に展示調査役として考える」と指示し、1回の回答を二段階に分けることを、別々のAIエージェントが協力する仕組みと同じものとして扱う。",
          "博物館の展示データから名前や場所を返す検索ツールが、調査担当のAIへ結果を渡す場合、そのツールも情報の受け渡しに参加しているので、独立したAIエージェントの一つとして数える。",
          "来館者が恐竜を希望した場合と化石を希望した場合で案内を切り替える条件分岐を用意し、分岐先が複数あることを、別々のAIエージェントが協力する構成と同じものとして扱う。"
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
          "最初に登録した「ピーマンを避けたい」という希望は、利用者の基本的な好みを表すと考え、本人が「今後は使ってほしい」と変更しても、以前の記録を優先して献立を作る。",
          "「味が濃かった」という感想をもとにAIが一度薄味の献立を提案できれば、その改善内容は次の相談にも引き継がれると考え、感想や新しい希望を保存する処理は設けない。"
        ],
        "M3": [
          "利用者が伝えた「ピーマンを避けたい」という希望を追加訓練でモデルの重みに覚えさせる処理を、利用者別の好みを保存し、必要に応じて更新・検索する記憶管理と同じ仕組みとして扱う。",
          "公開レシピから「ピーマンを使わない献立」を検索できれば、以前その利用者が「ピーマンを避けたい」と伝えたことも覚えていると考え、レシピ検索を個人の記憶機能として扱う。",
          "新しい会話で以前の相談文をプロンプトに貼り付けて好みを参照できれば、その入力操作自体を、好みを継続的に保存し、変更に合わせて記録を更新する記憶管理の仕組みと同じものとして扱う。"
        ]
      }
    },
    "retest_v2": {
      "variant_key": "retest_v2",
      "scenario": "企業が、利用者からの問い合わせに対応するAIを開発している。ある利用者は以前の相談で「今後の連絡は電話でしてほしい」と伝えたが、別の日に「これからはメールで連絡してほしい」と希望を変更した。\n\nさらに、案内メールを受け取った際に、「文章が長いとわかりにくいので、次からは要点を先に書いてほしい」と感想を伝えた。\n\n開発担当者は、利用者が別の日に新しい問い合わせをした場合にも、その利用者の現在の連絡方法や案内文への希望を反映できる記憶機能を設けたいと考えている。",
      "task": "この目的を実現するための情報の保存・利用方法として、適切な説明を3つ選びなさい。",
      "choices": {
        "correct": [
          "利用者が「電話で連絡してほしい」と伝えたら、その希望を利用者ごとの記録に残し、別の日の問い合わせで連絡方法を決める際に、関連する記録を取り出して利用できるようにする。",
          "利用者が後から「今後はメールで連絡してほしい」と伝えたら、以前の電話希望と新しい指定を照合し、現在有効な連絡方法をメールに更新して、次回の案内に反映する。",
          "案内メールへの「次からは要点を先に書いてほしい」という感想を、今後の案内にも役立つ希望として保存し、後の問い合わせで必要に応じて取り出し、文章の作り方に利用する。"
        ],
        "M1": [
          "これまでの問い合わせ履歴を利用者ごとに保存しておけば、次の相談ではAIがその履歴を自動的に把握すると考え、回答前に保存内容を取得する仕組みは用意しない。",
          "最初の「電話希望」は利用者が登録した基本設定なので、後から「今後はメール」と伝えられても、変更は一時的なものだと考え、確認せずに以前の電話希望を優先して案内する。",
          "前回の案内メールで「要点を先に書いてほしい」と言われ、その場で文章を直せたなら、AIはその改善点を次回も覚えていると考え、感想を記録する仕組みは用意しない。"
        ],
        "M3": [
          "利用者から聞いた「今後はメール希望」という情報を追加訓練用データとしてモデルの重みに覚えさせる処理を、利用者ごとの連絡方法を保存・更新する記憶管理と同じ仕組みとして設計する。",
          "過去の問い合わせで似た質問をした人への対応例を検索し、「メールで案内した例」が見つかったら、その検索結果を、今回の利用者が以前指定した連絡方法の記憶として扱う。",
          "前回の会話文を新しい問い合わせの入力欄に貼り付ければ、その入力欄が連絡方法を継続して保存・更新する記憶の仕組みにもなると考え、利用者別の記録は管理しない。"
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
  for (const mode of ["standard", "easy"]) for (const initialPerfect of [false, true]) {
    const name = `${termSlug}-${mode}-${width}-${group}-${layout}-${initialPerfect ? "final" : "learning"}`;
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
      const targetQuestion = questions.find(question => question.term_slug === termSlug);
      if (mode === "standard") {
        const source = expected[`retest_v${index}`];
        assert.equal(targetQuestion.body, source.scenario + "\n\n" + source.task);
        assert.deepEqual(targetQuestion.options.map(option => option.body).sort(), [...Object.values(source.choices).flat(), "わからない。"].sort());
        assert.equal(targetQuestion.body.split("\n\n").length, source.scenario.split("\n\n").length + 1);
      }
      await page.goto(new URL("/" + route, base).href);
      for (const [questionIndex, question] of questions.entries()) {
        await page.getByText(question.body, { exact: true }).waitFor();
        assert.equal(await page.getByRole("checkbox").count(), 10);
        assert.equal(await page.locator(".learning-glossary").count(), 0);
        for (const option of question.options) assert.deepEqual(Object.keys(option).sort(), ["body", "exclusive", "label", "option_id"]);
        await assertLayout(page);
        if (question.term_slug === termSlug) {
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
