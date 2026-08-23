import fs from "node:fs";

const required = [
  "app/start/page.tsx",
  "app/pretest/page.tsx",
  "app/learning/[termSlug]/page.tsx",
  "app/final-test/page.tsx",
  "app/survey/page.tsx",
  "app/admin/page.tsx",
  "components/QuestionRunner.tsx",
  "components/MarkdownText.tsx"
];

for (const file of required) {
  if (!fs.existsSync(new URL(`../${file}`, import.meta.url))) {
    throw new Error(`missing ${file}`);
  }
}

console.log("frontend smoke ok");

const groupAdminPage = fs.readFileSync(new URL("../app/admin/page.tsx", import.meta.url), "utf8");
for (const expectedText of ['"control", "proposed"', "role=\"tablist\"", "activeGroup", "group_condition"]) {
  if (!groupAdminPage.includes(expectedText)) {
    throw new Error(`admin page missing group filtering behavior: ${expectedText}`);
  }
}
if (groupAdminPage.includes("条件統制チェック")) {
  throw new Error("admin page must not show the condition control check card");
}


const learningPage = fs.readFileSync(new URL("../app/learning/[termSlug]/page.tsx", import.meta.url), "utf8");
if (learningPage.includes("{feedback ? <div className=\"notice\">{feedback.feedback}</div>")) {
  throw new Error("learning page must not show standalone feedback after submit");
}
for (const forbiddenText of ["<strong>デバッグ</strong>", "事前テスト由来の誤概念:", "学習内の現在判定:", "teaching_strategy:"]) {
  if (learningPage.includes(forbiddenText)) {
    throw new Error(`learning page must not expose internal debug text: ${forbiddenText}`);
  }
}
for (const expectedText of ["今回の学習", "対象概念:", "教材", "問題", "分析中..."]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing participant-facing learning text: ${expectedText}`);
  }
}
if (learningPage.includes("足場掛けレベル:")) {
  throw new Error("learning page must not show scaffolding level in stage-based UI");
}
if (learningPage.includes("ターン: {turn.turn_index}")) {
  throw new Error("learning page must not show fixed turn progress in stage-based UI");
}
for (const expectedText of ["対象概念:", "教材フィードバック", "正解です。", "不正解です。", "feedback-card-ok", "feedback-card-error", "item_results", "次の確認へ", "次の確認を準備中..."]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing final feedback/debug update behavior: ${expectedText}`);
  }
}
for (const expectedText of ["SubmitProgress", "分析中です", "秒経過", "回答を記録しています", "選択内容を確認しています", "解説を生成しています", "次の教材を準備しています", "analysis-progress", "spinner"]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing submit progress behavior: ${expectedText}`);
  }
}
for (const expectedText of ["SessionLoadProgress", "ContinueProgress", "学習セッションを準備しています", "教材を生成しています", "確認問題を準備しています", "学習画面を表示しています", "aria-busy={submitting", "学習セッション読み込みの進行状況", "次の確認読み込みの進行状況"]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing initial loading progress behavior: ${expectedText}`);
  }
}
if (learningPage.includes("読み込み中...")) {
  throw new Error("learning page must not show a standalone loading message");
}
if (!learningPage.includes("learning_stage: data.next_learning_stage")) {
  throw new Error("learning page must update stage from next_learning_stage after response");
}
for (const expectedText of [
  "import { MarkdownText } from \"@/components/MarkdownText\";",
  "<MarkdownText>{turn.tutor_message}</MarkdownText>",
  "<MarkdownText>{feedback.feedback}</MarkdownText>",
  "<MarkdownText className=\"markdown-compact\">{item.material}</MarkdownText>",
  "<MarkdownText className=\"markdown-compact\">{item.feedback}</MarkdownText>"
]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing Markdown material/feedback rendering: ${expectedText}`);
  }
}
if (learningPage.includes("className=\"preserve-lines\">{turn.tutor_message}") || learningPage.includes("className=\"preserve-lines\">{feedback.feedback}")) {
  throw new Error("learning page must render material and feedback through MarkdownText");
}
if (!learningPage.includes("turnShownAt") || !learningPage.includes("question_shown_at: turnShownAt") || !learningPage.includes("answered_at: answeredAt")) {
  throw new Error("learning page must send turn timing timestamps");
}
for (const expectedText of ["selectedOptionIds", "selected_option_ids", "type={isMultiple ? \"checkbox\" : \"radio\"}", "概念変化", "豊富化", "/${requiredSelections} 選択済み", "上限に達しました", "わからないを選択中", "option-disabled", "option-unknown", "nextMultipleSelection"]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing multiple-selection/new-stage behavior: ${expectedText}`);
  }
}
for (const removedText of ["term_understanding", "concept_understanding"]) {
  if (learningPage.includes(`turn.learning_stage === "${removedText}"`)) {
    throw new Error(`learning page must not branch participant display on old stage: ${removedText}`);
  }
}

const questionRunner = fs.readFileSync(new URL("../components/QuestionRunner.tsx", import.meta.url), "utf8");
if (!questionRunner.includes("result.next_url || nextPath")) {
  throw new Error("QuestionRunner must follow backend next_url after scoring");
}

const learningTargetsPage = fs.readFileSync(new URL("../app/learning-targets/page.tsx", import.meta.url), "utf8");
for (const expectedText of ["pretest_results", "今回の確認結果", "result_label", "result_summary", "is_learning_target", "pretest-result-correct", "pretest-result-incorrect"]) {
  if (!learningTargetsPage.includes(expectedText)) {
    throw new Error(`learning targets page missing pretest result behavior: ${expectedText}`);
  }
}
for (const forbiddenText of ["misconception_type", "M1", "M2", "M3", "M4", "taxonomy"]) {
  if (learningTargetsPage.includes(forbiddenText)) {
    throw new Error(`learning targets page must not expose internal diagnosis text: ${forbiddenText}`);
  }
}

const markdownText = fs.readFileSync(new URL("../components/MarkdownText.tsx", import.meta.url), "utf8");
for (const expectedText of ["react-markdown", "skipHtml", "allowedElements", "unwrapDisallowed", "markdown-body"]) {
  if (!markdownText.includes(expectedText)) {
    throw new Error(`MarkdownText missing safe Markdown behavior: ${expectedText}`);
  }
}
if (markdownText.includes("rehype-raw")) {
  throw new Error("MarkdownText must not enable raw HTML rendering");
}

if (questionRunner.includes("response_time_sec: 10")) {
  throw new Error("QuestionRunner must not send fixed response_time_sec");
}
if (!questionRunner.includes("responseTimeSec") || !questionRunner.includes("questionStartedAt")) {
  throw new Error("QuestionRunner must send measured response_time_sec");
}
if (!questionRunner.includes("questionShownAt") || !questionRunner.includes("question_shown_at: questionShownAt") || !questionRunner.includes("answered_at: answeredAt")) {
  throw new Error("QuestionRunner must send question timing timestamps");
}
for (const expectedText of ["selection_mode", "selectedIds", "selected_option_ids", "type={isMultipleQuestion ? \"checkbox\" : \"radio\"}", "min_selections", "max_selections", "/${requiredSelections} 選択済み", "上限に達しました", "わからないを選択中", "disabled={isDisabled}", "option-disabled", "option-unknown", "nextMultipleSelection"]) {
  if (!questionRunner.includes(expectedText)) {
    throw new Error(`QuestionRunner missing multiple-selection behavior: ${expectedText}`);
  }
}
const finalTestPage = fs.readFileSync(new URL("../app/final-test/page.tsx", import.meta.url), "utf8");
for (const expectedText of ['phase="final_test"', '/api/experiment/${id}/final-test', '/api/participants/${id}/score-final-test', 'nextPath="/survey"']) {
  if (!finalTestPage.includes(expectedText)) {
    throw new Error(`final test page missing: ${expectedText}`);
  }
}

const adminPage = fs.readFileSync(new URL("../app/admin/page.tsx", import.meta.url), "utf8");
for (const expectedText of ["全体ログ", "誤概念推移（群集計）", "eligible_count", "全体ログCSV UTF-8", "全体ログCSV Excel", "被験者ログを見る", "被験者ログCSV UTF-8", "被験者ログCSV Excel", "実験開始画面へ戻る", "参加者を削除", "window.confirm", "/api/admin/participants/", "/api/admin/logs/overview", "/api/admin/logs/overview.csv", "/api/admin/logs/overview_excel.csv", "/logs.csv", "/logs_excel.csv"]) {
  if (!adminPage.includes(expectedText)) {
    throw new Error(`admin page missing log UI: ${expectedText}`);
  }
}
for (const expectedText of ["最近の回答履歴", "recent_answer_history", "回答履歴（テスト＋学習）", "answer_history", "source_type", "is_sufficient", "学習ターン詳細"]) {
  if (!adminPage.includes(expectedText)) {
    throw new Error(`admin page missing unified answer history UI: ${expectedText}`);
  }
}
for (const expectedText of ["実験フロー", "どのフェーズで、どの問題に、何を選び", "FlowCard", "phaseLabel", "selected_option_body", "question_body_snapshot"]) {
  if (!adminPage.includes(expectedText)) {
    throw new Error(`admin page missing visual participant flow UI: ${expectedText}`);
  }
}
if (adminPage.indexOf("/api/admin/logs/overview_excel.csv") > adminPage.indexOf("/api/admin/logs/overview.csv")) {
  throw new Error("admin page must prioritize Excel overview CSV before UTF-8 CSV");
}
if (adminPage.indexOf("/logs_excel.csv") > adminPage.indexOf("/logs.csv")) {
  throw new Error("admin page must prioritize Excel participant CSV before UTF-8 CSV");
}
for (const removedText of ["participants.csv", "attempts.csv", "learner_states.csv", "tutor_turns.csv", "recurrence_events.csv", "ai_call_logs.csv", "evaluation_summary.csv"]) {
  if (adminPage.includes(removedText)) {
    throw new Error(`admin page must not show legacy CSV link: ${removedText}`);
  }
}
