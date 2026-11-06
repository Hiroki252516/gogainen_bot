// Synthetic responses belong only in a separate Mock database.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const { LEARNING_VERIFY_ISOLATED, LEARNING_UI_BASE_URL, LEARNING_PLAYWRIGHT_MODULE, LEARNING_SCREENSHOT_DIR, LEARNING_TERM_SLUG, LEARNING_VARIANT_INDEX, LEARNING_FIXTURE_DB_URL } = process.env;
assert.equal(LEARNING_VERIFY_ISOLATED, "1");
assert(LEARNING_UI_BASE_URL && LEARNING_PLAYWRIGHT_MODULE && LEARNING_SCREENSHOT_DIR);
const base = new URL(LEARNING_UI_BASE_URL);
const termSlug = LEARNING_TERM_SLUG ?? "llm_knowledge";
const variantIndex = Number(LEARNING_VARIANT_INDEX ?? 1);
assert([1, 2, 3].includes(variantIndex));
if (variantIndex === 3) assert(LEARNING_FIXTURE_DB_URL, "V3 requires an explicit isolated fixture database.");
assert(variantIndex === 1 || termSlug === "multi_agent" || (["llm_knowledge", "memory_process"].includes(termSlug) && variantIndex === 2));
assert(["llm_knowledge", "multi_agent", "memory_process"].includes(termSlug));
assert(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname));
assert(base.port && base.port !== "3000", "Never use the study frontend.");
const { chromium } = await import(LEARNING_PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true, channel: "chrome" });
await mkdir(LEARNING_SCREENSHOT_DIR, { recursive: true });
const llmBodies = [
  "学生から履修登録の変更期限を尋ねられたとき、改訂後の履修規程から質問に関係する箇所を検索し、見つけた内容をAIに示して、その情報を参考に案内を作成させる。",
  "学生への回答を「必要な手続き・提出期限・注意点」の順にそろえるため、AIへ渡す指示文（プロンプト）に説明の順序を指定し、問い合わせへの回答時にその指示を利用する。",
  "担当職員が確認した履修登録の質問と適切な回答の組を学習用データとしてまとめ、その例を使ってAIモデルを追加訓練し、回答の構成や表現を調整する。",
  "開発中のテストでAIに改訂後の履修規程を見せ、変更期限を正しく答えられたため、モデルの重みが更新されたことで、新しい規程をAIが覚えたと判断し、実際の学生からの問い合わせでは規程を示さずに案内させる。",
  "職員が確認した質問と回答の例を学生の問い合わせのたびにAIへ渡せば、回答を重ねるうちにモデルの重みも更新されると考え、別の追加訓練は行わない。",
  "「必要な手続き・提出期限・注意点」の順に説明する指示文をAIへ与えると、その順序がモデルの重みに定着すると考え、以後の問い合わせには同じ指示を与えずに回答させる。",
  "職員が確認した質問と回答の例を文書検索の対象として登録し、似た質問が来たときに取り出せるようにする処理を、回答方法を覚えさせる追加訓練と同じ仕組みとして扱う。",
  "改訂後の履修規程を使ってAIを追加訓練し、学生から変更期限を尋ねられた際には、AIが学習に使った規程の該当箇所を探して参照できるものとして、文書検索の仕組みの代わりに用いる。",
  "改訂後の履修規程の本文をAIへの指示文（プロンプト）に書き込み、そのプロンプトそのものを、規程を継続的に保存したり必要な条文を検索したりする文書データベースとして扱う。"
];
const llmQuestionBody = "大学が、学生からの履修登録に関する質問に回答するAIを開発している。今年度は履修規程が改訂され、履修登録の変更手続きや提出期限が以前と異なっている。学生への回答は「必要な手続き・提出期限・注意点」の順にそろえたいが、質問によって説明の仕方にばらつきがある。また、担当職員が内容を確認した過去の質問と回答の例も用意しており、回答の改善に活用したい。\n\nこれらの目的を実現する開発担当者の対応として、適切なものを3つ選びなさい。";

const llmRoundTwoBodies = [
  "学生から自習室の予約変更期限を尋ねられたとき、改訂後の施設利用規程から質問に関係する箇所を検索し、見つけた内容をAIに示して、その情報を参考に案内を作成させる。",
  "学生への回答を「必要な手続き・申請期限・注意点」の順にそろえるため、AIへ渡す指示文（プロンプト）に説明の順序を指定し、問い合わせへの回答時にその指示を利用する。",
  "担当職員が確認した自習室の利用予約に関する質問と適切な回答の組を学習用データとしてまとめ、その例を使ってAIモデルを追加訓練し、回答の構成や表現を調整する。",
  "開発中のテストでAIに改訂後の施設利用規程を見せ、変更期限を正しく答えられたため、モデルの重みが更新されたことで、新しい規程をAIが覚えたと判断し、実際の学生からの問い合わせでは規程を示さずに案内させる。",
  "職員が確認した質問と回答の例を学生の問い合わせのたびにAIへ渡せば、回答を重ねるうちにモデルの重みも更新されると考え、別の追加訓練は行わない。",
  "「必要な手続き・申請期限・注意点」の順に説明する指示文をAIへ与えると、その順序がモデルの重みに定着すると考え、以後の問い合わせには同じ指示を与えずに回答させる。",
  "職員が確認した質問と回答の例を文書検索の対象として登録し、似た質問が来たときに取り出せるようにする処理を、回答方法を覚えさせる追加訓練と同じ仕組みとして扱う。",
  "改訂後の施設利用規程を使ってAIを追加訓練し、学生から予約変更期限を尋ねられた際には、AIが学習に使った規程の該当箇所を探して参照できるものとして、文書検索の仕組みの代わりに用いる。",
  "改訂後の施設利用規程の本文をAIへの指示文（プロンプト）に書き込み、そのプロンプトそのものを、規程を継続的に保存したり必要な条文を検索したりする文書データベースとして扱う。"
];
const llmRoundTwoQuestionBody = "大学が、学生からの自習室の利用予約に関する質問に回答するAIを開発している。今年度は施設利用規程が改訂され、予約の変更手続きや申請期限が以前と異なっている。学生への回答は「必要な手続き・申請期限・注意点」の順にそろえたいが、質問によって説明の仕方にばらつきがある。また、担当職員が内容を確認した過去の質問と回答の例も用意しており、回答の改善に活用したい。\n\nこれらの目的を実現する開発担当者の対応として、適切なものを3つ選びなさい。";

const multiBodies = [
  "被害状況や道路の情報を集めるAIが調査結果を避難方法の検討担当へ渡し、その検討結果を避難案内文作成担当に引き継ぐようにすれば、複数のAIが分担した作業を順番に繋げられる。",
  "情報収集担当が被害状況と道路の通行状況を整理して避難方法の検討担当に共有し、検討担当がその情報を自分の作業に利用することで、異なる役割のAIが協力して避難案内を作れる。",
  "避難方法の検討担当から避難経路の候補を受け取った避難案内文作成担当は、その情報を参考にして、住民に何をどのような順番で伝えるかを自分の役割として判断できる。",
  "情報収集担当のAIが道路の通行状況を調べて避難方法の検討担当へ渡した場合、検討担当は情報源が十分に確認されていると考え、その報告をもとに避難経路を決める。",
  "情報収集担当、避難方法の検討担当、避難案内文作成担当という役割名を各AIに付ければ、どの情報をどの順番で渡すかも自動的に決まるので、受け渡しの仕組みを設計する必要はない。",
  "情報収集担当が道路の通行状況を報告し、避難案内文作成担当がその情報を使って説明を作る場合でも、両者が同じ回答内容を出さなければ、結果を引き継いで連携することはできない。",
  "情報収集担当のAIが道路情報のデータベースから通行止めの一覧を取得する検索ツールを使う場合、そのツールも情報を調べて結果を渡すので、別のAIエージェントとして数える。",
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
const roundThreeBodies = [
  "案1でWi-Fiの設定手順が検索ツールから返ってきた場合、その手順が学生の端末に合うかを確認し、どの対処を案内するかは、ツールを使うAIエージェントが判断する。",
  "案2では、調査担当のAIが見つけた設定手順や障害情報を、回答担当のAIが受け取り、学生の問い合わせ内容に合わせて説明を組み立てることで、2つのAIが連携できる。",
  "案1で検索ツールを2種類利用しても、AIエージェントが2つに増えるわけではない。案2では調査と回答を別々のAIに担当させ、結果を受け渡している。",
  "案1でWi-Fiの設定手順が検索結果の上位に表示された場合、その手順は学生の端末やOSに合うものとして選ばれていると考え、適用条件を確かめずに案内する。",
  "案2で調査担当のAIが設定マニュアルを調べ、接続設定のやり直しを提案した場合、同じ資料を共有する回答担当のAIも同じ対処方法を選ぶと考える。",
  "案1でマニュアル検索と障害情報確認の2つのツールを使って回答すると、使った情報はそのAIの記憶に残るため、記録を保存する仕組みがなくても次の問い合わせに利用できる。",
  "案1で検索ツールが返したWi-Fi設定手順の説明文は、学生への回答を作るために使われるので、その文章も案2の調査担当のAIと同じ、1つのエージェントとして数える。",
  "案1ではマニュアル検索と障害情報確認という2つのツールが別々に結果を返すので、ツールが2つあることを、調査担当と回答担当の2つのAIが協力する構成と同じものとして扱う。",
  "案2で調査担当のAIが資料を読んで質問に必要な情報を整理しても、その処理は案1のマニュアル検索ツールと同じ種類の検索機能として分類できる。"
];
const roundThreeQuestionBody = "大学が、学生からの「学内Wi-Fiにつながらない」という問い合わせに対応するAIシステムを開発している。開発担当者は、次の2つの設計を比較している。\n\n案1： 1つのAIエージェントが、Wi-Fiの設定マニュアルを検索するツールと、大学のネットワーク障害情報を調べるツールを使い、学生への回答を作成する。\n\n案2： 調査担当のAIエージェントが設定マニュアルや障害情報を調べて必要な内容を整理し、その結果を受け取った回答担当のAIエージェントが、学生への回答を作成する。\n\nなお、ここでいう検索ツールとは、指定された資料や情報を探して結果を返す機能を指す。\n\n案1と案2の仕組みの違いについて、適切な説明を3つ選びなさい。";
const memoryBodies = [
  "学生が「具体例を先に示してほしい」と伝えたら、その希望を学生ごとの記録に保存し、別の日に質問があった際に関係する記録を取り出して、説明の仕方に反映させる。",
  "説明の順番や文章の詳しさなど、記録する希望の項目を決め、学生ごとに情報を管理できるようにするとともに、記録を保持する期間や削除方法も設定する。",
  "「具体例を先に」と希望していた学生が後から「結論を先に」と伝えた場合、以前の記録を新しい希望に合わせて更新し、次回の説明には変更後の希望を反映する。",
  "以前「具体例を先に」と希望した学生が後から「結論を先に」と伝えても、最初の希望がその学生の基本的な好みを表すと考え、次回以降も古い記録を優先して使う。",
  "過去の会話をすべて保存しておけば、そこに書かれた説明方法の希望が次の相談でも自動的に使われると考え、今回必要な情報を取り出す方法は特に設計しない。",
  "以前保存した「具体例を先に」という希望をAIに渡して説明させたところ、希望どおりに回答できたので、AIはその希望を新たに覚えたと考え、次の相談では記録を参照させない。",
  "学生の説明方法の希望を記憶するため、会話から得た希望を追加訓練のデータに使い、更新されたモデルの重みを、学生ごとの希望を保存する記録として扱う。",
  "同じ会話で「具体例を先に」と伝えた後、続く質問にも希望が反映されたので、会話中の履歴を利用する仕組みを、別の日の新しい会話でも希望を保持する長期記憶と同じものとして扱う。",
  "前回の会話を次の質問と一緒にプロンプトへ貼り付ける操作を、学生ごとの希望を継続して保存し、変更に応じて更新できる記憶管理の仕組みと同じものとして扱う。"
];
const memoryQuestionBody = "大学が、授業内容について質問できる学習支援AIを開発している。学生は会話の中で「具体例を先に示してほしい」「結論から説明してほしい」など、説明の仕方について希望を伝えることがある。また、同じ学生でも、相談を重ねる中で希望が変わることがある。\n\n開発担当者は、同じ学生が別の日に新しく質問したとき、説明の仕方について希望を毎回伝え直さなくても、その学生が最後に伝えた希望に合わせて説明できるようにしたいと考えている。\n\nこのAIに記憶機能を設ける場合の対応として、適切なものを3つ選びなさい。";
const memoryRoundTwoBodies = [
  "利用者が「辛い料理が好き」と伝えたら、その希望を利用者ごとの記録に保存し、別の日に相談があった際に関係する記録を取り出して、献立の提案に反映させる。",
  "料理の辛さや調理時間など、記録する希望の項目を決め、利用者ごとに情報を管理できるようにするとともに、記録を保持する期間や削除方法も設定する。",
  "「辛い料理が好き」と希望していた利用者が後から「辛い料理を控えたい」と伝えた場合、以前の記録を新しい希望に合わせて更新し、次回の提案には変更後の希望を反映する。",
  "以前「辛い料理が好き」と希望した利用者が後から「辛い料理を控えたい」と伝えても、最初の希望がその利用者の基本的な好みを表すと考え、次回以降も古い記録を優先して使う。",
  "過去の会話をすべて保存しておけば、そこに書かれた料理の好みや調理条件の希望が次の相談でも自動的に使われると考え、今回必要な情報を取り出す方法は特に設計しない。",
  "以前保存した「辛い料理が好き」という希望をAIに渡して献立を提案させたところ、希望どおりに回答できたので、AIはその希望を新たに覚えたと考え、次の相談では記録を参照させない。",
  "利用者の料理の好みや調理条件の希望を記憶するため、会話から得た希望を追加訓練のデータに使い、更新されたモデルの重みを、利用者ごとの希望を保存する記録として扱う。",
  "同じ会話で「辛い料理が好き」と伝えた後、続く相談にも希望が反映されたので、会話中の履歴を利用する仕組みを、別の日の新しい会話でも希望を保持する長期記憶と同じものとして扱う。",
  "前回の会話を次の相談と一緒にプロンプトへ貼り付ける操作を、利用者ごとの希望を継続して保存し、変更に応じて更新できる記憶管理の仕組みと同じものとして扱う。"
];
const memoryRoundTwoQuestionBody = "料理の献立を提案するAIを開発している。利用者は会話の中で「辛い料理が好き」「調理は20分以内がよい」など、料理の好みや調理条件について希望を伝えることがある。また、同じ利用者でも、相談を重ねる中で希望が変わることがある。\n\n開発担当者は、同じ利用者が別の日に新しく献立を相談したとき、料理の好みや調理条件について希望を毎回伝え直さなくても、その利用者が最後に伝えた希望に合わせて提案できるようにしたいと考えている。\n\nこのAIに記憶機能を設ける場合の対応として、適切なものを3つ選びなさい。";
const questionFixtures = {
  "llm_knowledge:1": [llmBodies, llmQuestionBody],
  "llm_knowledge:2": [llmRoundTwoBodies, llmRoundTwoQuestionBody],
  "multi_agent:1": [multiBodies, multiQuestionBody],
  "multi_agent:2": [roundTwoBodies, roundTwoQuestionBody],
  "multi_agent:3": [roundThreeBodies, roundThreeQuestionBody],
  "memory_process:1": [memoryBodies, memoryQuestionBody],
  "memory_process:2": [memoryRoundTwoBodies, memoryRoundTwoQuestionBody],
};
const fixture = questionFixtures[`${termSlug}:${variantIndex}`];
assert(fixture, "Missing browser question fixture.");
const [bodies, questionBody] = fixture;

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
    const caseName = `${termSlug}-round${variantIndex}-${width}-${group}-${layout}-${role}`;
    const context = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await context.newPage();
    assert.equal((await api(page.request, "/api/admin/ai/status")).ai_backend, "mock");
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

    if (variantIndex === 3) {
      const session = await api(page.request, "/api/tutor-sessions", "POST", { participant_id: created.participant_id, term_slug: termSlug });
      // Only the explicitly selected temporary Mock DB may contain a synthetic third session.
      const fixture = spawnSync(fileURLToPath(new URL("../../backend/.venv/bin/python", import.meta.url)), ["-c", `
import sys
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.core.experiment_spec import can_resume
from app.models import Participant, TutorSession, TutorTurn
url = make_url(sys.argv[1])
assert url.drivername == "sqlite" and url.database
path = Path(url.database).resolve()
assert path.is_file() and any(path.is_relative_to(root.resolve()) for root in (Path("/tmp"), Path(tempfile.gettempdir())))
engine = create_engine(url)
with Session(engine) as db:
    participant = db.get(Participant, sys.argv[2])
    session = db.get(TutorSession, sys.argv[3])
    assert participant and can_resume(participant)
    assert participant.current_step == "learning_targets"
    assert session and session.participant_id == participant.id and session.ended_at is None
    assert db.scalar(select(TutorTurn.id).where(TutorTurn.tutor_session_id == session.id)) is None
    session.session_index = 3
    db.commit()
engine.dispose()
`, LEARNING_FIXTURE_DB_URL, created.participant_id, session.tutor_session_id], { cwd: fileURLToPath(new URL("../../backend", import.meta.url)), encoding: "utf8" });
      assert.equal(fixture.status, 0, fixture.stderr || fixture.stdout);
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
    const preserveLines = (termSlug === "multi_agent" && [2, 3].includes(variantIndex)) || (["llm_knowledge", "memory_process"].includes(termSlug) && [1, 2].includes(variantIndex));
    assert.equal(await page.locator(".problem-block > p").evaluate((element) => getComputedStyle(element).whiteSpace), preserveLines ? "pre-wrap" : "normal");
    assert.equal(await page.locator(".problem-block > p strong").count(), 0);
    await page.screenshot({ path: `${LEARNING_SCREENSHOT_DIR}/${caseName}-question.png`, fullPage: true });
    const focusIndex = variantIndex === 1
      ? termSlug === "multi_agent" ? 6 : termSlug === "memory_process" ? 7 : 8
      : 8;
    const lastChoice = question.options.find((option) => option.body === bodies[focusIndex]);
    await page.getByRole("checkbox", { name: `${lastChoice.label}. ${lastChoice.body}`, exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${LEARNING_SCREENSHOT_DIR}/${caseName}-long-choice.png` });
    const unknown = page.getByRole("checkbox", { name: /^J\./ });
    await unknown.check();
    assert.equal(await page.getByRole("checkbox", { checked: true }).count(), 1);
    await unknown.uncheck();
    const responseRole = role === "M3" ? "correct" : role === "M1" ? "unknown" : "mixed";
    const revisedMemory = termSlug === "memory_process" && variantIndex === 1;
    const mixedBeliefIndex = revisedMemory ? 5 : 3;
    const mixedCategoryIndex = (termSlug === "llm_knowledge" && variantIndex === 1) || revisedMemory ? 7 : 6;
    const selectedBodies = responseRole === "correct" ? bodies.slice(0, 3) : responseRole === "unknown" ? ["わからない。"] : [bodies[0], bodies[mixedBeliefIndex], bodies[mixedCategoryIndex]];
    for (const option of question.options.filter((option) => selectedBodies.includes(option.body))) {
      await page.getByRole("checkbox", { name: `${option.label}. ${option.body}`, exact: true }).check();
    }
    const feedbackResponse = page.waitForResponse((response) => /\/api\/tutor-turns\/[^/]+\/respond$/.test(response.url()));
    await page.getByRole("button", { name: "回答を確認", exact: true }).click();
    const feedback = await (await feedbackResponse).json();
    assert.equal(feedback.is_sufficient, responseRole === "correct");
    if (responseRole !== "correct") assert.equal(feedback.learning_misconception_type, responseRole === "mixed" ? "M3" : "unknown");
    await page.getByText(responseRole === "correct" ? "正解です。" : "不正解です。", { exact: true }).waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: `${LEARNING_SCREENSHOT_DIR}/${caseName}.png`, fullPage: true });
    if (responseRole !== "correct") {
      await page.getByRole("button", { name: "次の確認へ", exact: true }).click();
      await page.getByRole("button", { name: "回答を確認", exact: true }).waitFor();
      assert.equal(await page.getByText(questionBody, { exact: true }).count(), 1);
      assert.equal(await page.getByRole("checkbox").count(), 10);
    }
    console.log(`ok ${termSlug} round${variantIndex} ${width}px ${group} ${layout} ${role} -> ${responseRole}`);
    await context.close();
  }
} finally {
  await browser.close();
}
