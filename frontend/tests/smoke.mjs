import fs from "node:fs";

const required = [
  "app/start/page.tsx",
  "app/consent/page.tsx",
  "app/pretest/page.tsx",
  "app/learning/[termSlug]/page.tsx",
  "app/final-test/page.tsx",
  "app/survey/page.tsx",
  "app/admin/page.tsx",
  "components/QuestionRunner.tsx",
  "components/GiveUpButton.tsx",
  "components/ParticipantFlowGuard.tsx",
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
for (const expectedText of [
  "REASONING_EFFORTS",
  '"low", "medium", "high"',
  "reasoning-effort-buttons",
  "aria-pressed",
  "/api/admin/ai/reasoning-effort",
  "保存中...",
  "実験中でも変更できます",
  "AI_BACKEND=mock"
]) {
  if (!groupAdminPage.includes(expectedText)) {
    throw new Error(`admin page missing reasoning effort control: ${expectedText}`);
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
for (const expectedText of ["学習内容：", "教材", "問題", "分析中..."]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing participant-facing learning text: ${expectedText}`);
  }
}
for (const expectedText of [":initial`,", ":after:${completedTurnId}`"]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page must use a distinct idempotency key per turn generation: ${expectedText}`);
  }
}
for (const expectedText of ['localStorage.getItem("learning_targets")', "idx + 1 < targets.length", "`/learning/${targets[idx + 1]}`", ' : "/retest"']) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing ordered target continuation: ${expectedText}`);
  }
}
if (learningPage.includes("足場掛けレベル:")) {
  throw new Error("learning page must not show scaffolding level in stage-based UI");
}
if (learningPage.includes("ターン: {turn.turn_index}")) {
  throw new Error("learning page must not show fixed turn progress in stage-based UI");
}
for (const expectedText of ["学習内容：", "教材フィードバック", "正解です。", "不正解です。", "feedback-card-ok", "feedback-card-error", "item_results", "次の確認へ", "次の確認を準備中..."]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing final feedback/debug update behavior: ${expectedText}`);
  }
}
if (learningPage.indexOf("className=\"learning-layout\"") > learningPage.indexOf("{feedback ? (")) {
  throw new Error("learning page must keep the question layout above feedback");
}
for (const expectedText of ["disabled={submitting || Boolean(feedback)}", "submitting ? (feedback ? <ContinueProgress /> : <SubmitProgress />)", "!feedback ? ("]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing inline feedback behavior: ${expectedText}`);
  }
}
for (const expectedText of ["SubmitProgress", "分析中です", "秒経過", "回答を記録しています", "選択内容を確認しています", "解説を生成しています", "次の教材を準備しています", "analysis-progress", "spinner"]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing submit progress behavior: ${expectedText}`);
  }
}
for (const expectedText of ["GiveUpButton", 'mode="learning"', "give-up-footer"]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing learning give-up behavior: ${expectedText}`);
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
for (const expectedText of ["selectedOptionIds", "selected_option_ids", "type={isMultiple ? \"checkbox\" : \"radio\"}", "question-progress", "turn.turn_index", "turn.max_turns", "{turn.turn_index} / {turn.max_turns}", "/${requiredSelections} 選択済み", "上限に達しました", "わからないを選択中", "option-disabled", "option-unknown", "nextMultipleSelection"]) {
  if (!learningPage.includes(expectedText)) {
    throw new Error(`learning page missing multiple-selection/progress behavior: ${expectedText}`);
  }
}
if (learningPage.includes("toFullWidthDigits") || learningPage.includes("問{toFullWidthDigits")) {
  throw new Error("learning session must keep its existing question display format");
}
if (learningPage.includes("問{turn.turn_index} / {turn.max_turns}")) {
  throw new Error("learning session progress must not include the 問 prefix");
}
for (const removedText of ["今回の学習", "対象概念:", "段階:", "概念変化", "豊富化", "誤った捉え方を見直します", "不足知識を補います"]) {
  if (learningPage.includes(removedText)) {
    throw new Error(`learning page must not expose researcher-facing stage guidance: ${removedText}`);
  }
}
for (const removedText of ["term_understanding", "concept_understanding"]) {
  if (learningPage.includes(`turn.learning_stage === "${removedText}"`)) {
    throw new Error(`learning page must not branch participant display on old stage: ${removedText}`);
  }
}

const questionRunner = fs.readFileSync(new URL("../components/QuestionRunner.tsx", import.meta.url), "utf8");
if (!questionRunner.includes("result.next_url || nextPath")) {
  throw new Error("QuestionRunner must follow the backend transition after scoring");
}
for (const expectedText of ["learning_target_slugs", 'localStorage.setItem("learning_targets"', "result.next_url || nextPath", "router.replace(result.next_url || nextPath)", "allowExperimentGiveUp", 'mode="experiment"', "give-up-footer"]) {
  if (!questionRunner.includes(expectedText)) {
    throw new Error(`question runner missing retest transition support: ${expectedText}`);
  }
}
for (const expectedText of ["test_round_label", "setDisplayTitle"]) {
  if (!questionRunner.includes(expectedText)) {
    throw new Error(`question runner missing test round display behavior: ${expectedText}`);
  }
}
for (const expectedText of ["${index + 1} / ${questions.length}", "question-heading", "問{toFullWidthDigits(index + 1)}：", "<strong>{current.term_label}</strong>", "<p>{current.body}</p>", "className=\"muted question-progress\""]) {
  if (!questionRunner.includes(expectedText)) {
    throw new Error(`QuestionRunner missing question progress display: ${expectedText}`);
  }
}
if (questionRunner.includes("問${toFullWidthDigits(index + 1)} /")) {
  throw new Error("test and retest progress must not include the 問 prefix");
}
for (const expectedText of ["answer_status", "submitted_answer", "回答済み・変更不可", "次の問題へ", "option-selected-locked", "displayedSelectedIds", "postIdempotent", "clearPendingIdempotency"]) {
  if (!questionRunner.includes(expectedText)) {
    throw new Error(`question runner missing immutable answer behavior: ${expectedText}`);
  }
}

const apiClient = fs.readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
for (const expectedText of ["class ApiError", "postIdempotent", "clearParticipantSession", "sessionStorage", "Idempotency-Key", "PendingIdempotentRequest", "type ApiRequestInit", "AbortController", "timeoutMs: options?.timeoutMs"]) {
  if (!apiClient.includes(expectedText)) {
    throw new Error(`API client missing idempotency behavior: ${expectedText}`);
  }
}

const flowGuard = fs.readFileSync(new URL("../components/ParticipantFlowGuard.tsx", import.meta.url), "utf8");
for (const expectedText of ["/current-step", "ParticipantEntryGuard", "useLearningTargetFlowGuard", "router.replace", "Do not expose a stale page", "もう一度確認"]) {
  if (!flowGuard.includes(expectedText)) {
    throw new Error(`flow guard missing browser-back protection: ${expectedText}`);
  }
}

const pretestPage = fs.readFileSync(new URL("../app/pretest/page.tsx", import.meta.url), "utf8");
for (const expectedText of ['step="テスト"', 'title="テスト"']) {
  if (!pretestPage.includes(expectedText)) {
    throw new Error(`pretest page missing unified test label: ${expectedText}`);
  }
}
const retestPage = fs.readFileSync(new URL("../app/retest/page.tsx", import.meta.url), "utf8");
for (const expectedText of ['phase="retest"', 'useState("再テスト1")', 'step={roundTitle}', 'title="再テスト1"', 'onDisplayTitle={setRoundTitle}', "allowExperimentGiveUp"]) {
  if (!retestPage.includes(expectedText)) {
    throw new Error(`retest page missing round label: ${expectedText}`);
  }
}

const learningTargetsPage = fs.readFileSync(new URL("../app/learning-targets/page.tsx", import.meta.url), "utf8");
for (const expectedText of ["pretest_results", "test_results", "今回の確認結果", "test_round_label", "className=\"question-heading\"", "問{toFullWidthDigits(i + 1)}：<strong>{result.term_label}</strong>", "question_body", 'result.question_body || "問題文を確認できません。"', "selected_options", "自分が選んだ選択肢", "result_label", "result_summary", "is_learning_target", "current_stage_for_display", "pretest-result-correct", "pretest-result-incorrect", "result-verdict"]) {
  if (!learningTargetsPage.includes(expectedText)) {
    throw new Error(`learning targets page missing pretest result behavior: ${expectedText}`);
  }
}
const globalStyles = fs.readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
for (const expectedText of [".pretest-result-correct .result-verdict {\n  color: var(--ok);", ".pretest-result-incorrect .result-verdict {\n  color: var(--danger);", ".question-heading {\n  font-family: inherit;\n  font-size: 1rem;", ".question-heading strong {\n  font: inherit;\n  font-weight: 700;"]) {
  if (!globalStyles.includes(expectedText)) {
    throw new Error(`test result page missing correct/incorrect color styling: ${expectedText}`);
  }
}
for (const forbiddenText of ["misconception_type", "M1", "M2", "M3", "M4", "taxonomy"]) {
  if (learningTargetsPage.includes(forbiddenText)) {
    throw new Error(`learning targets page must not expose internal diagnosis text: ${forbiddenText}`);
  }
}
for (const expectedText of ["current_step", 'currentStep === "learning_targets"', "学習対象を確認しています。", "GiveUpButton", 'startsWith("retest_")', "give-up-footer"]) {
  if (!learningTargetsPage.includes(expectedText)) {
    throw new Error(`learning targets page missing guarded final-test transition: ${expectedText}`);
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
for (const expectedText of ["selection_mode", "selectedIds", "selected_option_ids", "type={isMultipleQuestion ? \"checkbox\" : \"radio\"}", "min_selections", "max_selections", "/${requiredSelections} 選択済み", "上限に達しました", "わからないを選択中", "disabled={isAnswered || isDisabled}", "option-disabled", "option-unknown", "nextMultipleSelection"]) {
  if (!questionRunner.includes(expectedText)) {
    throw new Error(`QuestionRunner missing multiple-selection behavior: ${expectedText}`);
  }
}
const finalTestPage = fs.readFileSync(new URL("../app/final-test/page.tsx", import.meta.url), "utf8");
for (const expectedText of ['phase="final_test"', 'step="再テスト1"', 'title="再テスト1"', '/api/experiment/${id}/final-test', '/api/participants/${id}/score-final-test', 'nextPath="/survey"', "allowExperimentGiveUp"]) {
  if (!finalTestPage.includes(expectedText)) {
    throw new Error(`final test page missing: ${expectedText}`);
  }
}
const giveUpButton = fs.readFileSync(new URL("../components/GiveUpButton.tsx", import.meta.url), "utf8");
for (const expectedText of ["window.confirm", "/give-up-learning", "/give-up", "next_url", "router.replace(result.next_url ||"]) {
  if (!giveUpButton.includes(expectedText)) {
    throw new Error(`give-up button missing API behavior: ${expectedText}`);
  }
}
const startPage = fs.readFileSync(new URL("../app/start/page.tsx", import.meta.url), "utf8");
for (const expectedText of ["assignmentCode", "pending_assignment_code", 'router.push("/consent")', "同意書を確認する"]) {
  if (!startPage.includes(expectedText)) {
    throw new Error(`start page missing consent transition: ${expectedText}`);
  }
}
for (const forbiddenText of ["pending_group_condition", "group_condition", "提案群", "統制群", "<select"]) {
  if (startPage.includes(forbiddenText)) {
    throw new Error(`start page must not expose participant group selection: ${forbiddenText}`);
  }
}
const consentPage = fs.readFileSync(new URL("../app/consent/page.tsx", import.meta.url), "utf8");
for (const expectedText of ["研究参加同意書（仮）", "assignment_code", "consent_checked: true", 'router.replace("/pretest")', "同意してテストを開始", "学習方法の割り当て", "timeoutMs: 15000", 'role="alert"']) {
  if (!consentPage.includes(expectedText)) {
    throw new Error(`consent page missing test-start behavior: ${expectedText}`);
  }
}
for (const forbiddenText of ["GROUP_LABELS", "pending_group_condition", "group_condition", "提案群", "統制群"]) {
  if (consentPage.includes(forbiddenText)) {
    throw new Error(`consent page must not expose participant group condition: ${forbiddenText}`);
  }
}
const apiHelper = fs.readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
for (const expectedText of ["type ApiRequestInit", "AbortController", "timeoutMs", "サーバーからの応答がありません。接続を確認して、もう一度お試しください。"]) {
  if (!apiHelper.includes(expectedText)) {
    throw new Error(`api helper missing request timeout behavior: ${expectedText}`);
  }
}
const surveyPage = fs.readFileSync(new URL("../app/survey/page.tsx", import.meta.url), "utf8");
for (const expectedText of ["実験後アンケート（仮）", "/survey", "usability_rating", "required label=\"AI利用経験\"", "required label=\"プログラミング経験\"", "required label=\"LLM利用頻度\"", "required label=\"AIに関する自己評価\"", "{required ? <span className=\"required-indicator\">必須選択</span> : null}", "回答を保存して終了", 'router.replace("/finish")']) {
  if (!surveyPage.includes(expectedText)) {
    throw new Error(`survey page missing save-and-finish behavior: ${expectedText}`);
  }
}

const finishPage = fs.readFileSync(new URL("../app/finish/page.tsx", import.meta.url), "utf8");
for (const expectedText of ["clearParticipantSession", "新しい実験を開始", 'router.replace("/start")']) {
  if (!finishPage.includes(expectedText)) {
    throw new Error(`finish page missing new experiment reset behavior: ${expectedText}`);
  }
}

const adminPage = fs.readFileSync(new URL("../app/admin/page.tsx", import.meta.url), "utf8");
if (!adminPage.includes("clearParticipantSession") || !adminPage.includes("participantId()")) {
  throw new Error("admin page must clear a deleted participant's browser session");
}
for (const expectedText of ["全体ログ", "誤概念推移（群集計）", "eligible_count", "全体ログCSV UTF-8", "全体ログ Excel互換CSV", "被験者ログを見る", "被験者ログCSV UTF-8", "被験者ログ Excel互換CSV", "ギブアップ回数", "参加者を削除", "window.confirm", "/api/admin/participants/", "/api/admin/logs/overview", "/api/admin/logs/overview.csv", "/api/admin/logs/overview_excel.csv", "/logs.csv", "/logs_excel.csv"]) {
  if (!adminPage.includes(expectedText)) {
    throw new Error(`admin page missing log UI: ${expectedText}`);
  }
}
for (const buttonLabel of ["実験開始画面へ戻る", "実験途中に戻る"]) {
  if (!adminPage.includes(buttonLabel)) {
    throw new Error(`admin participant navigation is missing button label: ${buttonLabel}`);
  }
}
for (const expectedText of ["最近の回答履歴", "recent_answer_history", "回答履歴（テスト＋学習）", "アンケート回答", "answer_history", "source_type", "学習ターン詳細", "completion_reason", "give_up_learning_count", "give_up_experiment_count", "LOG_FIELD_LABELS"]) {
  if (!adminPage.includes(expectedText)) {
    throw new Error(`admin page missing unified answer history UI: ${expectedText}`);
  }
}
for (const removedText of ["学習十分", "学習不十分", "後戻り", "最近の操作監査ログ", "操作監査ログ", "最近のAI呼び出し", "AI呼び出しログ", "再発イベント"]) {
  if (adminPage.includes(removedText)) {
    throw new Error(`admin page must not show outdated evaluation label: ${removedText}`);
  }
}
for (const expectedText of ["実験フロー", "どのフェーズで、どの問題に、何を選び", "FlowCard", "phaseLabel", "selected_option_body", "question_body_snapshot"]) {
  if (!adminPage.includes(expectedText)) {
    throw new Error(`admin page missing visual participant flow UI: ${expectedText}`);
  }
}
for (const expectedText of ["firstRetestRound", 'roundLabel(firstRetestRound?.round || "retest_1")', "最終到達", 'retest: "再テスト1"']) {
  if (!adminPage.includes(expectedText)) {
    throw new Error(`admin page missing consistent test round summary: ${expectedText}`);
  }
}
if (adminPage.includes('Metric label="再テスト"')) {
  throw new Error("admin page must use numbered retest labels");
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
