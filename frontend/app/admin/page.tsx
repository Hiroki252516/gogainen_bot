"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { IdentityMappings } from "@/components/IdentityMappings";
import { HypothesisMetrics, ParticipantHypothesisMetrics } from "@/components/HypothesisMetrics";
import { API_BASE, ApiError, api, clearParticipantSession, participantId } from "@/lib/api";

type Participant = {
  participant_id: string;
  display_code: string;
  group_condition: string;
  current_step: string;
  can_resume: boolean;
  experiment_spec_version: number | null;
  question_set_mode: "standard" | "easy";
  show_question_reviews: boolean | null;
  first_question_only: boolean | null;
  show_pretest_results: boolean;
  show_retest_results: boolean;
  learning_material_glossary_mode: "annotation_only" | "integrated_material" | null;
  retest_cycles_completed: number | null;
  post_pretest_tests_completed: number | null;
  post_pretest_test_limit: number | null;
  completed_at: string | null;
  completion_reason: string | null;
  give_up_learning_count: number;
  give_up_experiment_count: number;
};
type GroupCondition = "control" | "proposed";
const REASONING_EFFORTS = ["low", "medium", "high"] as const;
type ReasoningEffort = (typeof REASONING_EFFORTS)[number];
const AI_MODELS = [["gpt-6.1-sol", "GPT-6.1 Sol"], ["gpt-6-luna", "GPT-6 Luna"]] as const;
type AiModel = (typeof AI_MODELS)[number][0];
type OptionOrderMode = "debug_fixed" | "randomized";
type OptionOrderSetting = { mode: OptionOrderMode; applies_to: "new_participants_only" };
type LearningMaterialGlossaryMode = "annotation_only" | "integrated_material";
type LearningMaterialGlossarySetting = { mode: LearningMaterialGlossaryMode; applies_to: "new_participants_only" };
const questionSetLabel = (mode: string | null | undefined) => mode === "easy" ? "易しい版" : "通常版";
const materialGlossaryModeLabel = (mode: string | null | undefined) => mode === "annotation_only"
  ? "注釈欄のみ"
  : mode === "integrated_material"
    ? "教材内解説"
    : "未記録（旧仕様）";
type CurrentStepResponse = { step: string; next_url: string; can_resume: boolean };
type AiStatus = {
  study_settings_warning?: string | null;
  ai_backend: string;
  account_label?: string;
  app_server_reachable?: boolean | null;
  logged_in?: boolean | null;
  last_error?: string | null;
  model?: string;
  allowed_models?: AiModel[];
  can_change_model?: boolean;
  model_applies?: boolean;
  reasoning_effort?: ReasoningEffort;
  allowed_reasoning_efforts?: ReasoningEffort[];
  can_change_reasoning_effort?: boolean;
  reasoning_effort_change_block_reason?: string | null;
  reasoning_effort_applies?: boolean;
};

const ADMIN_RESUME_PARTICIPANT_ID_KEY = "admin_resume_participant_id";
const ADMIN_RESUME_DISPLAY_CODE_KEY = "admin_resume_display_code";

function rememberAdminResumeParticipant(id: string) {
  localStorage.setItem(ADMIN_RESUME_PARTICIPANT_ID_KEY, id);
  const displayCode = localStorage.getItem("display_code");
  if (displayCode) {
    localStorage.setItem(ADMIN_RESUME_DISPLAY_CODE_KEY, displayCode);
  } else {
    localStorage.removeItem(ADMIN_RESUME_DISPLAY_CODE_KEY);
  }
}

function clearAdminResumeParticipant(id?: string) {
  if (!id || localStorage.getItem(ADMIN_RESUME_PARTICIPANT_ID_KEY) === id) {
    localStorage.removeItem(ADMIN_RESUME_PARTICIPANT_ID_KEY);
    localStorage.removeItem(ADMIN_RESUME_DISPLAY_CODE_KEY);
  }
}

const MISCONCEPTION_TRANSITION_LABELS: Record<string, string> = {
  resolved: "解消",
  same_type_recurred: "同種再発",
  changed_type: "別タイプ化",
  unknown_persisted: "unknown継続",
  regressed: "誤概念",
  unclassified: "未分類"
};
const MISCONCEPTION_TRANSITION_TYPES = Object.keys(MISCONCEPTION_TRANSITION_LABELS);
const LOG_FIELD_LABELS: Record<string, string> = {
  display_code: "被験者",
  legacy_read_only: "閲覧専用",
  question_set_mode: "問題版",
  test_page_mode: "テスト表示方式（登録値）",
  effective_test_page_mode: "テスト表示方式",
  test_timing_unit: "テスト時間の単位",
  response_time_unit: "回答時間の単位",
  test_page_timing_json: "用語ページ計測",
  source_type: "記録種別",
  test_round: "周回",
  term_slug: "用語",
  group_condition: "群",
  phase: "フェーズ",
  learning_stage: "学習段階",
  component_term: "構成要素",
  current_status: "状態",
  current_stage_for_display: "学習段階",
  primary_misconception: "主な誤概念",
  is_correct: "判定",
  misconception_type: "誤概念",
  learning_misconception_type: "学習時の誤概念",
  teaching_strategy: "教授方略",
  question_shown_at: "問題表示時刻",
  answered_at: "回答時刻",
  response_time_sec: "回答時間(秒)",
  created_at: "記録時刻",
  updated_at: "更新時刻",
  pretest_score: "テスト正答率",
  retest_score: "再テスト正答率",
  attainment_correct_rate: "到達正答率",
  same_misconception_recurrence_rate: "同種再発率",
  completed: "完了",
  completion_reason: "終了理由",
  retest_cycles_completed: "学習後の再テスト回数",
  post_pretest_tests_completed: "事前テスト後のテスト回数",
  post_pretest_test_limit: "事前テスト後のテスト上限",
  actor: "実行者",
  action: "操作",
  purpose: "呼び出し目的",
  status: "状態",
  error_code: "エラーコード",
  latency_ms: "遅延(ms)",
  turn_index: "ターン",
  next_learning_stage: "次の学習段階",
  before_json: "変更前",
  after_json: "変更後",
  previous_misconception_type: "前回の誤概念",
  current_misconception_type: "今回の誤概念",
  ai_experience_level: "AI利用経験",
  programming_experience_level: "プログラミング経験",
  llm_usage_level: "LLM利用頻度",
  self_rated_ai_knowledge: "AI自己評価",
  usability_rating: "操作のしやすさ",
  helpfulness_rating: "役立ち度",
  perceived_hint_amount: "ヒント・説明の量",
  free_comment: "自由記述",
  show_question_reviews: "設問ごとの答え合わせ",
  first_question_only: "設問1のみ出題",
  learning_material_glossary_mode: "教材の用語解説モード",
  question_review_acknowledged_at: "答え合わせ確認時刻"
};

export default function AdminPage() {
  const router = useRouter();
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [activeGroup, setActiveGroup] = useState<GroupCondition>("control");
  const [summary, setSummary] = useState<any>(null);
  const [overview, setOverview] = useState<any>(null);
  const [participantLog, setParticipantLog] = useState<any>(null);
  const [ai, setAi] = useState<AiStatus | null>(null);
  const [optionOrder, setOptionOrder] = useState<OptionOrderSetting | null>(null);
  const [optionOrderSaving, setOptionOrderSaving] = useState(false);
  const [optionOrderError, setOptionOrderError] = useState("");
  const [pretestDisplay, setPretestDisplay] = useState<{ enabled: boolean } | null>(null);
  const [pretestDisplaySaving, setPretestDisplaySaving] = useState(false);
  const [pretestDisplayError, setPretestDisplayError] = useState("");
  const [firstQuestionOnly, setFirstQuestionOnly] = useState<{ enabled: boolean } | null>(null);
  const [firstQuestionOnlySaving, setFirstQuestionOnlySaving] = useState(false);
  const [firstQuestionOnlyError, setFirstQuestionOnlyError] = useState("");
  const [summaryFirstOnly, setSummaryFirstOnly] = useState(false);
  const [questionReviewDisplay, setQuestionReviewDisplay] = useState<{ enabled: boolean } | null>(null);
  const [questionReviewDisplaySaving, setQuestionReviewDisplaySaving] = useState(false);
  const [questionReviewDisplayError, setQuestionReviewDisplayError] = useState("");
  const [materialGlossaryMode, setMaterialGlossaryMode] = useState<LearningMaterialGlossarySetting | null>(null);
  const [materialGlossaryModeSaving, setMaterialGlossaryModeSaving] = useState(false);
  const [materialGlossaryModeError, setMaterialGlossaryModeError] = useState("");
  const [summaryError, setSummaryError] = useState("");
  const [summaryRefresh, setSummaryRefresh] = useState(0);
  const [login, setLogin] = useState<any>(null);
  const [loginError, setLoginError] = useState("");
  const [aiStatusError, setAiStatusError] = useState("");
  const [reasoningEffortSaving, setReasoningEffortSaving] = useState(false);
  const [reasoningEffortError, setReasoningEffortError] = useState("");
  const [modelSaving, setModelSaving] = useState(false);
  const [modelError, setModelError] = useState("");
  const [logError, setLogError] = useState("");
  const [recalculating, setRecalculating] = useState(false);
  const [deletingParticipantId, setDeletingParticipantId] = useState<string | null>(null);
  const [resumingExperiment, setResumingExperiment] = useState(false);
  const [flowNavigationError, setFlowNavigationError] = useState("");

  useEffect(() => {
    const activeParticipantId = participantId();
    if (activeParticipantId) rememberAdminResumeParticipant(activeParticipantId);
    api<{ participants: Participant[] }>("/api/admin/participants").then((data) => setParticipants(data.participants)).catch((err) => setLogError(err.message));
    api("/api/admin/logs/overview").then(setOverview).catch((err) => setLogError(err.message));
    api<{ enabled: boolean }>("/api/admin/pretest-result-display").then(setPretestDisplay).catch((err) => setPretestDisplayError(err.message));
    api<{ enabled: boolean }>("/api/admin/first-question-only").then(setFirstQuestionOnly).catch((err) => setFirstQuestionOnlyError(err.message));
    api<{ enabled: boolean }>("/api/admin/question-review-display").then(setQuestionReviewDisplay).catch((err) => setQuestionReviewDisplayError(err.message));
    api<LearningMaterialGlossarySetting>("/api/admin/learning-material-glossary-mode").then(setMaterialGlossaryMode).catch((err) => setMaterialGlossaryModeError(err.message));
    api<AiStatus>("/api/admin/ai/status").then(setAi).catch((err) => setAiStatusError(err instanceof Error ? err.message : String(err)));
    api<OptionOrderSetting>("/api/admin/option-order")
      .then(setOptionOrder)
      .catch((err) => setOptionOrderError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    let active = true;
    setSummary(null);
    setSummaryError("");
    api("/api/admin/evaluation-summary?question_set_mode=standard")
      .then((data) => { if (active) setSummary(data); })
      .catch((err) => { if (active) setSummaryError(err.message); });
    return () => { active = false; };
  }, [summaryRefresh]);

  useEffect(() => {
    setParticipantLog(null);
    setLogError("");
  }, [activeGroup]);

  function returnToExperimentStart() {
    const activeParticipantId = participantId();
    if (activeParticipantId) rememberAdminResumeParticipant(activeParticipantId);
    setFlowNavigationError("");
    clearParticipantSession();
    router.push("/start");
  }

  async function resumeExperiment() {
    const activeParticipantId = participantId();
    const resumeParticipantId = activeParticipantId || localStorage.getItem(ADMIN_RESUME_PARTICIPANT_ID_KEY);
    if (!resumeParticipantId) {
      setFlowNavigationError("このブラウザで再開できる実験が見つかりません。");
      return;
    }

    setFlowNavigationError("");
    setResumingExperiment(true);
    try {
      const current = await api<CurrentStepResponse>(`/api/participants/${resumeParticipantId}/current-step`);
      if (!current.can_resume) {
        setFlowNavigationError("この試用記録は閲覧専用です。新しい実験を開始してください。");
        return;
      }
      const displayCode = activeParticipantId
        ? localStorage.getItem("display_code")
        : localStorage.getItem(ADMIN_RESUME_DISPLAY_CODE_KEY);
      localStorage.setItem("participant_id", resumeParticipantId);
      if (displayCode) {
        localStorage.setItem("display_code", displayCode);
      } else {
        localStorage.removeItem("display_code");
      }
      localStorage.removeItem("pending_assignment_code");
      clearAdminResumeParticipant(resumeParticipantId);
      router.push(current.next_url || "/start");
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        clearAdminResumeParticipant(resumeParticipantId);
        if (participantId() === resumeParticipantId) clearParticipantSession();
      }
      setFlowNavigationError(error instanceof Error ? error.message : String(error));
    } finally {
      setResumingExperiment(false);
    }
  }

  async function startLogin(type: "chatgpt" | "chatgptDeviceCode") {
    setLoginError("");
    try {
      const result = await api("/api/admin/ai/login/start", {
        method: "POST",
        body: JSON.stringify({ type })
      });
      setLogin(result);
      if ((result as any).authUrl) {
        window.open((result as any).authUrl, "_blank", "noopener,noreferrer");
      }
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : String(err));
    }
  }

  async function updateReasoningEffort(reasoningEffort: ReasoningEffort) {
    if (
      reasoningEffortSaving || modelSaving ||
      !ai ||
      ai.ai_backend !== "codex_app_server" ||
      ai.reasoning_effort === reasoningEffort
    ) {
      return;
    }

    setReasoningEffortError("");
    setReasoningEffortSaving(true);
    try {
      const result = await api<AiStatus>("/api/admin/ai/reasoning-effort", {
        method: "POST",
        body: JSON.stringify({ reasoning_effort: reasoningEffort })
      });
      setAi((current) => ({ ...current, ...result }));
    } catch (err) {
      setReasoningEffortError(err instanceof Error ? err.message : String(err));
    } finally {
      setReasoningEffortSaving(false);
    }
  }

  async function updateAiModel(model: AiModel) {
    if (modelSaving || reasoningEffortSaving || !ai || ai.ai_backend !== "codex_app_server" || ai.model === model) return;
    setModelError("");
    setModelSaving(true);
    try {
      const result = await api<AiStatus>("/api/admin/ai/model", {
        method: "POST",
        body: JSON.stringify({ model })
      });
      setAi((current) => ({ ...current, ...result }));
    } catch (err) {
      setModelError(err instanceof Error ? err.message : String(err));
    } finally {
      setModelSaving(false);
    }
  }

  async function updateOptionOrder(mode: OptionOrderMode) {
    if (optionOrderSaving || !optionOrder || optionOrder.mode === mode) return;
    setOptionOrderError("");
    setOptionOrderSaving(true);
    try {
      const updated = await api<OptionOrderSetting>("/api/admin/option-order", {
        method: "PUT",
        body: JSON.stringify({ mode })
      });
      setOptionOrder(updated);
    } catch (err) {
      setOptionOrderError(err instanceof Error ? err.message : String(err));
    } finally {
      setOptionOrderSaving(false);
    }
  }

  async function updatePretestDisplay(enabled: boolean) {
    if (!pretestDisplay || pretestDisplaySaving) return;
    setPretestDisplaySaving(true);
    setPretestDisplayError("");
    try {
      setPretestDisplay(await api<{ enabled: boolean }>("/api/admin/pretest-result-display", { method: "PUT", body: JSON.stringify({ enabled }) }));
    } catch (err) {
      setPretestDisplayError(err instanceof Error ? err.message : String(err));
    } finally {
      setPretestDisplaySaving(false);
    }
  }

  async function updateFirstQuestionOnly(enabled: boolean) {
    if (!firstQuestionOnly || firstQuestionOnlySaving) return;
    setFirstQuestionOnlySaving(true);
    setFirstQuestionOnlyError("");
    try {
      setFirstQuestionOnly(await api<{ enabled: boolean }>("/api/admin/first-question-only", { method: "PUT", body: JSON.stringify({ enabled }) }));
    } catch (err) {
      setFirstQuestionOnlyError(err instanceof Error ? err.message : String(err));
    } finally {
      setFirstQuestionOnlySaving(false);
    }
  }

  async function updateQuestionReviewDisplay(enabled: boolean) {
    if (!questionReviewDisplay || questionReviewDisplaySaving) return;
    setQuestionReviewDisplaySaving(true);
    setQuestionReviewDisplayError("");
    try {
      setQuestionReviewDisplay(await api<{ enabled: boolean }>("/api/admin/question-review-display", { method: "PUT", body: JSON.stringify({ enabled }) }));
    } catch (err) {
      setQuestionReviewDisplayError(err instanceof Error ? err.message : String(err));
    } finally {
      setQuestionReviewDisplaySaving(false);
    }
  }

  async function updateMaterialGlossaryMode(mode: LearningMaterialGlossaryMode) {
    if (!materialGlossaryMode || materialGlossaryModeSaving || materialGlossaryMode.mode === mode) return;
    setMaterialGlossaryModeSaving(true);
    setMaterialGlossaryModeError("");
    try {
      setMaterialGlossaryMode(await api<LearningMaterialGlossarySetting>("/api/admin/learning-material-glossary-mode", {
        method: "PUT",
        body: JSON.stringify({ mode })
      }));
    } catch (err) {
      setMaterialGlossaryModeError(err instanceof Error ? err.message : String(err));
    } finally {
      setMaterialGlossaryModeSaving(false);
    }
  }

  async function loadParticipantLog(participantId: string) {
    setLogError("");
    try {
      const result = await api(`/api/admin/participants/${participantId}/logs`);
      setParticipantLog(result);
    } catch (err) {
      setLogError(err instanceof Error ? err.message : String(err));
    }
  }

  async function recalculateParticipantSummary(participantId: string) {
    setLogError("");
    setRecalculating(true);
    try {
      await api(`/api/participants/${participantId}/evaluation-summary/recalculate`, { method: "POST" });
      await loadParticipantLog(participantId);
      setSummaryRefresh((count) => count + 1);
      api("/api/admin/logs/overview").then(setOverview);
    } catch (err) {
      setLogError(err instanceof Error ? err.message : String(err));
    } finally {
      setRecalculating(false);
    }
  }

  async function deleteParticipant(participant: Participant) {
    const confirmed = window.confirm(`参加者 ${participant.display_code} の研究DB内の回答・教材・AIログ等とアプリ内の対応表を削除します。元に戻せません。ダウンロード済みCSV・USBの対応表・バックアップは自動削除されません。撤回時は別途処理してください。続行しますか？`);
    if (!confirmed) return;

    setLogError("");
    setDeletingParticipantId(participant.participant_id);
    try {
      await api(`/api/admin/participants/${participant.participant_id}`, { method: "DELETE" });
      if (participantId() === participant.participant_id) {
        clearParticipantSession();
      }
      clearAdminResumeParticipant(participant.participant_id);
      if (participantLog?.participant?.participant_id === participant.participant_id) {
        setParticipantLog(null);
      }
      const [participantData, overviewData] = await Promise.all([
        api<{ participants: Participant[] }>("/api/admin/participants"),
        api("/api/admin/logs/overview")
      ]);
      setParticipants(participantData.participants);
      setSummaryRefresh((count) => count + 1);
      setOverview(overviewData);
    } catch (err) {
      setLogError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeletingParticipantId(null);
    }
  }

  const activeParticipants = participants.filter((participant) => participant.group_condition === activeGroup);
  const currentParticipantCount = activeParticipants.filter((participant) => participant.can_resume && participant.question_set_mode === "standard").length;
  const readOnlyParticipantCount = activeParticipants.filter((participant) => !participant.can_resume).length;
  const retiredEasyParticipantCount = activeParticipants.filter((participant) => !participant.can_resume && participant.question_set_mode === "easy").length;
  const activeGroupSummary = summary?.groups?.find((group: any) => group.group_condition === activeGroup && (group.first_question_only === true) === summaryFirstOnly);
  const activeAnswerHistory = (overview?.recent_answer_history || []).filter((row: any) => row.group_condition === activeGroup);
  const activeEvaluationSummaries = (overview?.evaluation_summaries || []).filter((row: any) => row.group_condition === activeGroup && !row.legacy_read_only && row.question_set_mode === "standard");

  return (
    <AppShell step="管理画面">
      <div className="stack admin-content">
        <section className="panel stack">
          <h1>管理画面</h1>
          <div className="group-tabs" role="tablist" aria-label="実験群">
            {(["proposed", "control"] as GroupCondition[]).map((group) => (
              <button
                key={group}
                className={activeGroup === group ? "group-tab active" : "group-tab"}
                role="tab"
                aria-selected={activeGroup === group}
                onClick={() => setActiveGroup(group)}
              >
                {group}
              </button>
            ))}
          </div>
          <div className="grid">
            <div className="notice">
              <strong>AI Backend</strong>
              <p>{ai ? `${ai.ai_backend} / ${ai.account_label}` : aiStatusError ? "取得できません" : "確認中"}</p>
              {ai?.app_server_reachable === false ? <p className="danger">Codex app-serverに接続できません。</p> : null}
              {ai?.last_error ? <p className="muted">{ai.last_error}</p> : null}
              {ai?.study_settings_warning ? <p className="danger" role="alert">{ai.study_settings_warning}</p> : null}
              {ai?.logged_in === false ? (
                <div className="actions">
                  <button className="secondary" onClick={() => startLogin("chatgpt")}>
                    ChatGPTログイン
                  </button>
                  <button className="secondary" onClick={() => startLogin("chatgptDeviceCode")}>
                    デバイスコード
                  </button>
                </div>
              ) : null}
              {login?.verificationUrl ? (
                <p>
                  <a href={login.verificationUrl} target="_blank" rel="noreferrer">
                    認証ページ
                  </a>
                  {" / code: "}
                  <strong>{login.userCode}</strong>
                </p>
              ) : null}
              {aiStatusError ? <p className="danger" role="alert">AI接続状態を取得できませんでした: {aiStatusError}</p> : null}
              {loginError ? <p className="danger">{loginError}</p> : null}
              {ai ? (
                <div className="reasoning-effort-control" aria-labelledby="ai-model-title">
                  <strong id="ai-model-title">AIモデル</strong>
                  <p>{ai.ai_backend === "codex_app_server" ? "有効モデル" : "設定値（Mockでは未使用）"}: {ai.model || "不明"}</p>
                  <div className="reasoning-effort-buttons" role="group" aria-labelledby="ai-model-title">
                    {AI_MODELS.map(([model, label]) => (
                      <button
                        key={model}
                        type="button"
                        className={ai.model === model ? "reasoning-effort-button active" : "reasoning-effort-button"}
                        aria-pressed={ai.model === model}
                        disabled={
                          modelSaving || reasoningEffortSaving ||
                          ai.ai_backend !== "codex_app_server" ||
                          ai.can_change_model === false ||
                          !(ai.allowed_models || []).includes(model)
                        }
                        onClick={() => updateAiModel(model)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {modelSaving ? <p className="muted">切替中...</p> : null}
                  <p className="muted">次回のAI呼び出しから適用します。実験中に切り替えると、同じ参加者の記録内でモデルが混在する場合があります。</p>
                  {ai.ai_backend !== "codex_app_server" ? (
                    <p className="muted">Mock実行中のためモデル切替は適用されません。</p>
                  ) : null}
                  {modelError ? <p className="danger" role="alert">{modelError}</p> : null}
                </div>
              ) : null}
              {ai ? (
                <div className="reasoning-effort-control" aria-labelledby="reasoning-effort-title">
                  <strong id="reasoning-effort-title">推論レベル</strong>
                  <div className="reasoning-effort-buttons" role="group" aria-label="Codex推論レベル">
                    {REASONING_EFFORTS.map((effort) => (
                      <button
                        key={effort}
                        type="button"
                        className={ai.reasoning_effort === effort ? "reasoning-effort-button active" : "reasoning-effort-button"}
                        aria-pressed={ai.reasoning_effort === effort}
                        disabled={
                          reasoningEffortSaving || modelSaving ||
                          ai.ai_backend !== "codex_app_server"
                        }
                        onClick={() => updateReasoningEffort(effort)}
                      >
                        {effort}
                      </button>
                    ))}
                  </div>
                  {reasoningEffortSaving ? <p className="muted">保存中...</p> : null}
                  <p className="muted">管理画面からは実験中でも変更できます。次回のCodex app-server呼び出しから適用されます。</p>
                  {ai.ai_backend !== "codex_app_server" ? (
                    <p className="muted">AI_BACKEND=mockのため、推論レベルはCodex app-serverには適用されません。</p>
                  ) : null}
                  {reasoningEffortError ? <p className="danger">{reasoningEffortError}</p> : null}
                </div>
              ) : null}
            </div>
            <div className="notice question-set-setting">
              <label className="pretest-display-toggle">
                <input type="checkbox" role="switch" checked={pretestDisplay?.enabled ?? false}
                  disabled={!pretestDisplay || pretestDisplaySaving}
                  onChange={(event) => updatePretestDisplay(event.target.checked)} />
                テスト結果の表示
              </label>
              <p className="muted">事前テスト・再テスト1/2・内部final_testに適用。新規参加者のみ</p>
              {pretestDisplaySaving ? <p role="status">保存中...</p> : null}
              {pretestDisplayError ? <p className="danger" role="alert">{pretestDisplayError}</p> : null}
            </div>
            <div className="notice question-set-setting">
              <label className="pretest-display-toggle">
                <input type="checkbox" role="switch" checked={questionReviewDisplay?.enabled ?? false}
                  disabled={!questionReviewDisplay || questionReviewDisplaySaving}
                  onChange={(event) => updateQuestionReviewDisplay(event.target.checked)} />
                設問ごとの答え合わせ
              </label>
              <p className="muted">通常版の新規参加者のみ（初期値ON）</p>
              {questionReviewDisplaySaving ? <p role="status">保存中...</p> : null}
              {questionReviewDisplayError ? <p className="danger" role="alert">{questionReviewDisplayError}</p> : null}
            </div>
            <div className="notice question-set-setting">
              <label className="pretest-display-toggle">
                <input type="checkbox" role="switch" checked={firstQuestionOnly?.enabled ?? false}
                  disabled={!firstQuestionOnly || firstQuestionOnlySaving}
                  onChange={(event) => updateFirstQuestionOnly(event.target.checked)} />
                設問1のみ出題
              </label>
              <p className="muted">ON：各用語の設問1のみ（計3問）。OFF：設問1・2（計6問）。事前テスト・再テスト・学習確認に適用します。新規参加者のみ、登録時に固定されます（初期値OFF）。</p>
              {firstQuestionOnlySaving ? <p role="status">保存中...</p> : null}
              {firstQuestionOnlyError ? <p className="danger" role="alert">{firstQuestionOnlyError}</p> : null}
            </div>
            <div className="notice question-set-setting">
              <strong>教材の用語解説モード</strong>
              <div className="reasoning-effort-buttons" role="group" aria-label="教材の用語解説モード">
                {([
                  ["annotation_only", "注釈欄のみ"],
                  ["integrated_material", "教材内解説"]
                ] as [LearningMaterialGlossaryMode, string][]).map(([mode, label]) => (
                  <button
                    key={mode}
                    type="button"
                    className={materialGlossaryMode?.mode === mode ? "reasoning-effort-button active" : "reasoning-effort-button"}
                    aria-pressed={materialGlossaryMode?.mode === mode}
                    disabled={!materialGlossaryMode || materialGlossaryModeSaving}
                    onClick={() => updateMaterialGlossaryMode(mode)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="muted">新規参加者のみ。初期値は「注釈欄のみ」です。教材内解説では、教材に登場する登録語を本文中で説明し、教材右側の注釈欄は表示しません。</p>
              {materialGlossaryModeSaving ? <p role="status">保存中...</p> : null}
              {materialGlossaryModeError ? <p className="danger" role="alert">{materialGlossaryModeError}</p> : null}
            </div>
            <div className="notice question-set-setting">
              <strong>新規参加者に適用する問題版</strong>
              <p>通常版</p>
              <p className="muted">今後の新規参加者には通常版を適用します。易しい版の参加者は閲覧専用で、群集計には含まれません。</p>
            </div>
            <div className="notice">
              <strong>選択肢の配置</strong>
              <p>{optionOrder ? (optionOrder.mode === "debug_fixed" ? "デバッグ配置" : "ランダム配置") : "設定を確認中"}</p>
              <div className="reasoning-effort-buttons option-order-buttons" role="group" aria-label="選択肢の配置モード">
                {([
                  ["debug_fixed", "デバッグ配置"],
                  ["randomized", "ランダム配置"]
                ] as [OptionOrderMode, string][]).map(([mode, label]) => (
                  <button
                    key={mode}
                    type="button"
                    className={optionOrder?.mode === mode ? "reasoning-effort-button active" : "reasoning-effort-button"}
                    aria-pressed={optionOrder?.mode === mode}
                    disabled={!optionOrder || optionOrderSaving}
                    onClick={() => updateOptionOrder(mode)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="muted">モードの切替は新規参加者から適用します。開始済みの参加者の配置モードは変わりません。</p>
              <p className="muted">ランダム配置ではA〜Iを並べ替え、「わからない」は最後のJに固定します。</p>
              {optionOrder?.mode === "debug_fixed" ? (
                <p className="danger" role="alert">デバッグ配置は正解位置の手掛かりになるため、実験データの収集には使用しないでください。</p>
              ) : null}
              {optionOrderSaving ? <p className="muted">保存中...</p> : null}
              {optionOrderError ? <p className="danger" role="alert">{optionOrderError}</p> : null}
            </div>
            <label>集計の出題条件
              <select value={summaryFirstOnly ? "q1" : "q12"} onChange={(event) => setSummaryFirstOnly(event.target.value === "q1")}>
                <option value="q12">設問1・2（6問）</option>
                <option value="q1">設問1のみ（3問）</option>
              </select>
            </label>
            {activeGroupSummary ? (
              <div className="notice">
                <strong>{activeGroupSummary.group_condition} / 通常版</strong>
                <p>参加者: {activeGroupSummary.participant_count}</p>
                <p>確認テスト正答率: {formatRate(activeGroupSummary.attainment_correct_rate)}</p>
                <p>事前比改善: {formatPoints(activeGroupSummary.avg_score_delta_from_pretest_pt)}</p>
              </div>
            ) : null}
          </div>
          {flowNavigationError ? <p className="danger" role="alert">{flowNavigationError}</p> : null}
          <div className="actions">
            <button className="secondary" type="button" onClick={returnToExperimentStart} disabled={resumingExperiment}>
              実験開始画面へ戻る
            </button>
            <button className="secondary" type="button" onClick={resumeExperiment} disabled={resumingExperiment}>
              {resumingExperiment ? "実験途中を確認中..." : "実験途中に戻る"}
            </button>
            <a className="button secondary" href={`${API_BASE}/api/admin/logs/overview_excel.csv`}>
              全体ログ Excel互換CSV
            </a>
            <a className="button secondary" href={`${API_BASE}/api/admin/logs/overview.xlsx`}>
              全体ログ Excel (.xlsx)
            </a>
            <a className="button secondary" href={`${API_BASE}/api/admin/logs/overview.csv`}>
              全体ログCSV UTF-8
            </a>
            {participantLog?.participant?.participant_id ? (
              <>
                <a className="button secondary" href={`${API_BASE}/api/admin/participants/${participantLog.participant.participant_id}/logs_excel.csv`}>
                  被験者ログ Excel互換CSV
                </a>
                <a className="button secondary" href={`${API_BASE}/api/admin/participants/${participantLog.participant.participant_id}/logs.xlsx`}>
                  被験者ログ Excel (.xlsx)
                </a>
                <a className="button secondary" href={`${API_BASE}/api/admin/participants/${participantLog.participant.participant_id}/logs.csv`}>
                  被験者ログCSV UTF-8
                </a>
              </>
            ) : null}
          </div>
        </section>
        <section className="panel stack">
          <h2>全体ログ</h2>
          <p><strong>集計対象: 通常版</strong>。1回6設問・単一選択で集計します。生ログと被験者一覧は、閲覧専用の易しい版参加者を含めて表示します。</p>
          {summaryError ? <p className="danger" role="alert">{summaryError}</p> : null}
          <p className="muted">{activeGroup}群の進捗、回答履歴、評価サマリーを確認します。</p>
          <div className="grid">
            <div className="notice">
              <strong>現行参加者数（集計版）</strong>
              <p>{currentParticipantCount}</p>
            </div>
            <div className="notice">
              <strong>閲覧専用参加者数</strong>
              <p>{readOnlyParticipantCount}</p>
            </div>
            <div className="notice">
              <strong>停止した易しい版</strong>
              <p>{retiredEasyParticipantCount}</p>
            </div>
          </div>
          <p className="muted">以下の従来保存値・推移は参考情報です。6仮説の確定指標は専用の集計欄を参照してください。</p>
          <MisconceptionTransitionSummary summary={activeGroupSummary?.misconception_transition_summary} />
          <LogList title="最近の回答履歴" rows={activeAnswerHistory} fields={["question_set_mode", "test_page_mode", "test_timing_unit", "display_code", "legacy_read_only", "source_type", "test_round", "term_slug", "learning_stage", "component_term", "is_correct", "misconception_type", "teaching_strategy", "question_shown_at", "answered_at", "question_review_acknowledged_at", "response_time_sec", "response_time_unit", "test_page_timing_json", "created_at"]} />
          <LogList title="現行参加者の評価サマリー" rows={activeEvaluationSummaries} fields={["question_set_mode", "display_code", "group_condition", "pretest_score", "retest_score", "attainment_correct_rate", "same_misconception_recurrence_rate", "completed", "completion_reason", "created_at"]} />
        </section>
        <HypothesisMetrics data={summary?.hypotheses} />
        <section className="panel">
          <h2>{activeGroup}群の被験者一覧</h2>
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>条件</th>
                <th>問題版</th>
                <th>出題設問</th>
                <th>設問ごとの答え合わせ</th>
                <th>教材の用語解説</th>
                <th>進捗</th>
                <th>完了</th>
                <th>事前テスト後の回数</th>
                <th>ギブアップ回数</th>
                <th>ログ</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {activeParticipants.map((p) => (
                <tr key={p.participant_id}>
                  <td>{p.display_code}</td>
                  <td>{p.group_condition}</td>
                  <td>{questionSetLabel(p.question_set_mode)}</td>
                  <td>{p.can_resume ? (p.first_question_only ? "設問1のみ" : "設問1・2") : "旧仕様"}</td>
                  <td>{p.show_question_reviews === null ? "対象外" : p.show_question_reviews ? "ON" : "OFF"}</td>
                  <td>{materialGlossaryModeLabel(p.learning_material_glossary_mode)}</td>
                  <td>{p.can_resume ? p.current_step : `${p.question_set_mode === "easy" ? "易しい版停止" : "旧仕様"}（閲覧専用）: ${p.current_step}`}</td>
                  <td>{p.completion_reason === "give_up" ? "中断" : p.completed_at ? "完了" : "未完了"}</td>
                  <td>
                    <div>{p.post_pretest_tests_completed ?? "-"} / {p.post_pretest_test_limit ?? "-"}</div>
                    <div className="muted">学習後: {p.retest_cycles_completed ?? "-"}回</div>
                  </td>
                  <td>
                    <div>学習: {p.give_up_learning_count ?? 0}回</div>
                    <div>実験: {p.give_up_experiment_count ?? 0}回</div>
                  </td>
                  <td>
                    <button className="secondary" onClick={() => loadParticipantLog(p.participant_id)}>
                      被験者ログを見る
                    </button>
                  </td>
                  <td>
                    <button
                      className="danger-button"
                      disabled={deletingParticipantId === p.participant_id || !p.can_resume}
                      onClick={() => deleteParticipant(p)}
                    >
                      {!p.can_resume ? "閲覧専用" : deletingParticipantId === p.participant_id ? "削除中..." : "参加者を削除"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="panel stack">
          <h2>被験者別ログ</h2>
          {logError ? <p className="danger">{logError}</p> : null}
          {participantLog?.participant ? (
            <>
              <div className="notice">
                <strong>{participantLog.participant.display_code}</strong>
                <p>問題版: {questionSetLabel(participantLog.participant.question_set_mode)}</p>
                <p>テスト表示方式: {participantLog.participant.effective_test_page_mode === "per_term" ? "用語ごと（2設問／ページ）" : "設問ごと"}</p>
                <p>テスト時間の計測単位: {participantLog.participant.test_timing_unit === "term_page" ? "用語ページ" : "設問"}</p>
                <p>
                  {participantLog.participant.group_condition} / {participantLog.participant.current_step}
                </p>
                <p>学習後の再テスト: {participantLog.participant.retest_cycles_completed ?? "-"}回</p>
                <p>事前テスト後のテスト: {participantLog.participant.post_pretest_tests_completed ?? "-"} / {participantLog.participant.post_pretest_test_limit ?? "-"}回（学習前の追加テストを含む）</p>
                <p>事前テストの結果表示: {participantLog.participant.show_pretest_results === false ? "非表示" : "表示"}</p>
                <p>再テスト（内部final_testを含む）の結果表示: {participantLog.participant.show_retest_results === false ? "非表示" : "表示"}</p>
                <p>出題設問: {participantLog.participant.can_resume ? (participantLog.participant.first_question_only ? "設問1のみ（3問）" : "設問1・2（6問）") : "旧仕様の保存記録"}</p>
                <p>設問ごとの答え合わせ: {participantLog.participant.show_question_reviews === null ? "対象外" : participantLog.participant.show_question_reviews ? "表示" : "非表示"}</p>
                <p>教材の用語解説モード: {materialGlossaryModeLabel(participantLog.participant.learning_material_glossary_mode)}</p>
                <p>
                  終了理由: {participantLog.participant.completion_reason === "give_up"
                    ? "実験ギブアップ"
                    : participantLog.participant.completion_reason === "completed"
                      ? "通常終了"
                      : "未終了"}
                </p>
                <p>
                  学習ギブアップ: {participantLog.participant.give_up_learning_count ?? 0}回 / 実験ギブアップ: {participantLog.participant.give_up_experiment_count ?? 0}回
                </p>
                {!participantLog.participant.can_resume ? <p>{participantLog.participant.question_set_mode === "easy" ? "易しい版の実行を停止しています。保存済み記録は閲覧専用で、群集計から除外されます。" : "旧仕様の保存記録は閲覧専用です。"}</p> : null}
                <button className="secondary" disabled={recalculating || !participantLog.participant.can_resume} onClick={() => recalculateParticipantSummary(participantLog.participant.participant_id)}>
                  {recalculating ? "評価サマリー再計算中..." : "評価サマリーを再計算"}
                </button>
              </div>
              {participantLog.latest_evaluation_summary ? (
                <><ParticipantHypothesisMetrics data={participantLog.latest_evaluation_summary.hypothesis_metrics} /><EvaluationSummary summary={participantLog.latest_evaluation_summary} /></>
              ) : (
                <section className="insight-panel stack">
                  <div>
                    <h3>評価ログ早見</h3>
                    <p className="muted">採点済みのテスト回答がそろうと、スコア推移・誤概念推移・学習負担を自動計算します。</p>
                  </div>
                </section>
              )}
              <ParticipantFlow logs={participantLog} />
              {!participantLog.participant.can_resume ? (
                <details className="raw-json">
                  <summary>旧仕様の保存フィールド（閲覧専用）</summary>
                  <pre>{JSON.stringify({
                    attempts: participantLog.attempts.map((row: any) => ({ id: row.attempt_id, legacy_fields: row.legacy_fields })),
                    learner_states: participantLog.learner_states,
                    tutor_sessions: participantLog.tutor_sessions,
                    evaluation: participantLog.latest_evaluation_summary,
                  }, null, 2)}</pre>
                </details>
              ) : null}
              <LogList title="アンケート回答" rows={participantLog.surveys} fields={["phase", "survey_version", "responses", "ai_experience_level", "programming_experience_level", "llm_usage_level", "self_rated_ai_knowledge", "usability_rating", "helpfulness_rating", "perceived_hint_amount", "free_comment", "created_at"]} />
              <LogList title="回答履歴（テスト＋学習）" rows={participantLog.answer_history} fields={["question_set_mode", "test_page_mode", "test_timing_unit", "response_time_unit", "test_page_timing_json", "source_type", "test_round", "term_slug", "learning_stage", "component_term", "is_correct", "misconception_type", "teaching_strategy", "question_shown_at", "answered_at", "question_review_acknowledged_at", "response_time_sec", "created_at"]} />
              <LogList title="学習状態" rows={participantLog.learner_states} fields={["term_slug", "current_status", "current_stage_for_display", "primary_misconception", "teaching_strategy", "updated_at"]} />
              <SessionLog sessions={participantLog.tutor_sessions || []} />
            </>
          ) : (
            <p className="muted">被験者一覧の「被験者ログを見る」を押すと、1人分の流れを確認できます。</p>
          )}
        </section>
        <IdentityMappings key={participants.length} />
      </div>
    </AppShell>
  );
}

function formatRate(value: number | null) {
  if (value === null || value === undefined) return "-";
  return `${Math.round(value * 100)}%`;
}

function formatPoints(value: number | null) {
  if (value === null || value === undefined) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value * 10) / 10}pt`;
}

function MisconceptionTransitionSummary({ summary }: { summary: any }) {
  if (!summary) return null;
  const terms = summary.terms || [];
  return (
    <section className="insight-panel stack" aria-labelledby="group-misconception-title">
      <div>
        <h3 id="group-misconception-title">誤概念推移（群集計）</h3>
        <p className="muted">用語ごとの事前テスト実施者を分母に、誤概念の変化を集計しています。</p>
      </div>
      {terms.length ? (
        <div className="insight-grid">
          {terms.map((term: any) => (
            <div className="insight-card" key={term.term_slug}>
              <div className="term-row-head">
                <strong>{term.term_label || term.term_slug}</strong>
                <span className="muted">集計対象 {term.eligible_count}人 / 未受験 {term.missing_count}人</span>
              </div>
              {term.eligible_count > 0 ? (
                <table className="table compact-table">
                  <thead>
                    <tr>
                      <th>変化</th>
                      <th>人数</th>
                      <th>割合</th>
                    </tr>
                  </thead>
                  <tbody>
                    {MISCONCEPTION_TRANSITION_TYPES.map((transitionType) => (
                      <tr key={transitionType}>
                        <td>{MISCONCEPTION_TRANSITION_LABELS[transitionType]}</td>
                        <td>{term.counts?.[transitionType] ?? 0}人</td>
                        <td>{formatRate(term.rates?.[transitionType])}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted">集計対象データなし</p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">集計対象データなし</p>
      )}
    </section>
  );
}

function EvaluationSummary({ summary }: { summary: any }) {
  const rounds = summary.score_timeline?.rounds || [];
  const burden = summary.learning_burden || {};
  const misconceptionTerms = summary.misconception_timeline?.terms || [];
  const finalTestSkipped = summary.score_timeline?.final_test_skipped_after_retest_mastery === true;
  const firstRetestRound = rounds.find((round: any) => String(round.round || "").startsWith("retest_"));
  const finalRound = rounds.find((round: any) => round.phase === "final_test");
  const hasFinalOutcome = summary.attainment_correct_rate !== null && summary.attainment_correct_rate !== undefined;
  const finalDelta = finalTestSkipped && summary.pretest_score !== null && summary.pretest_score !== undefined && summary.attainment_correct_rate !== null && summary.attainment_correct_rate !== undefined
    ? (summary.attainment_correct_rate - summary.pretest_score) * 100
    : finalRound?.score_delta_from_pretest_pt;
  return (
    <section className="insight-panel stack" aria-labelledby="evaluation-insight-title">
      <div className="insight-head">
        <div>
          <h3 id="evaluation-insight-title">評価ログ早見</h3>
          <p className="muted">得点率の推移、誤概念の変化、学習負担をここで確認します。</p>
        </div>
        <div className={`delta-badge ${(finalDelta || 0) >= 0 ? "ok" : "bad"}`}>
          事前比 {formatPoints(finalDelta)}
        </div>
      </div>
      <div className="flow-summary">
        <Metric label="テスト" value={formatRate(summary.pretest_score)} />
        <Metric label={roundLabel(firstRetestRound?.round || "retest_1")} value={formatRate(firstRetestRound?.score_rate ?? summary.retest_score)} />
        {hasFinalOutcome ? <Metric label={finalTestSkipped ? "最終到達（再テスト満点）" : "最終到達"} value={formatRate(summary.attainment_correct_rate)} /> : null}
        <Metric label="再テスト回数" value={`${burden.retest_count ?? 0}回`} />
      </div>
      {finalTestSkipped ? <p className="muted">再テスト満点のため、追加の確認を省略しています。</p> : null}
      {rounds.length ? (
        <div className="score-road" aria-label="得点率推移">
          {rounds.map((round: any) => (
            <div className="score-step" key={`${round.round}-${round.attempt_index}`}>
              <div className="score-step-head">
                <strong>{roundLabel(round.round)}</strong>
                <span>{formatRate(round.score_rate)}</span>
              </div>
              <div className="score-bar">
                <span style={{ width: `${Math.max(0, Math.min(100, Number(round.score_rate || 0) * 100))}%` }} />
              </div>
              <div className="score-meta">
                <span>事前比 {formatPoints(round.score_delta_from_pretest_pt)}</span>
                <span>直前比 {formatPoints(round.score_delta_from_previous_test_pt)}</span>
                <span>未達 {round.remaining_learning_target_count ?? "-"}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      <div className="insight-grid">
        <div className="insight-card">
          <h4>誤概念推移</h4>
          {misconceptionTerms.length ? (
            <div className="term-timeline">
              {misconceptionTerms.map((term: any) => (
                <div className="term-row" key={term.term_slug || term.term_label}>
                  <div className="term-row-head">
                    <strong>{term.term_label || term.term_slug}</strong>
                    <span className={`change-pill ${term.change_type || "neutral"}`}>{changeLabel(term.change_type)}</span>
                  </div>
                  <div className="event-chips">
                    {(term.events || []).map((event: any) => (
                      <span className={`event-chip ${event.is_correct ? "ok" : "bad"}`} key={`${event.round}-${event.attempt_index}`}>
                        {roundLabel(event.round)}: {event.is_correct ? "正答" : event.misconception_type || "誤答"}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">誤概念推移はまだありません。</p>
          )}
        </div>
        <div className="insight-card">
          <h4>学習負担</h4>
          <div className="mini-metrics">
            <Metric label="学習セッション" value={`${burden.tutor_session_count ?? 0}回`} />
            <Metric label="学習ターン" value={`${burden.tutor_turn_count ?? 0}回`} />
            <Metric label="学習時間" value={formatSeconds(burden.total_learning_time_sec)} />
            <Metric label="テスト時間" value={formatSeconds(burden.total_test_time_sec)} />
          </div>
        </div>
      </div>
      <details className="raw-json">
        <summary>詳細JSON</summary>
        <pre>{JSON.stringify(summary, null, 2)}</pre>
      </details>
    </section>
  );
}

function roundLabel(round: string) {
  if (!round) return "-";
  if (round === "test" || round === "pretest") return "テスト";
  if (round === "final_test") return "再テスト1";
  if (round.startsWith("retest_")) return `再テスト${round.replace("retest_", "")}`;
  return round;
}

function changeLabel(type: string | null | undefined) {
  return (
    {
      resolved: "解消",
      same_type_recurred: "同種再発",
      changed_type: "別タイプ化",
      unknown_persisted: "unknown継続",
      regressed: "誤概念",
      neutral: "変化なし",
    } as Record<string, string>
  )[type || "neutral"] || type || "変化なし";
}

function ParticipantFlow({ logs }: { logs: any }) {
  const rows = [...(logs.answer_history || [])].sort((a: any, b: any) => flowTime(a).localeCompare(flowTime(b)));
  const testRows = rows.filter((row: any) => row.source_type === "test_attempt");
  const correctCount = testRows.filter((row: any) => row.is_correct === true).length;
  const incorrectCount = testRows.filter((row: any) => row.is_correct === false).length;
  return (
    <section className="flow-panel stack" aria-labelledby="participant-flow-title">
      <div>
        <h3 id="participant-flow-title">実験フロー</h3>
        <p className="muted">どのフェーズで、どの問題に、何を選び、どう判定されたかを時系列で確認します。</p>
      </div>
      <div className="flow-summary">
        <Metric label="テスト正解" value={`${correctCount}件`} />
        <Metric label="テスト不正解" value={`${incorrectCount}件`} tone={incorrectCount ? "bad" : "ok"} />
      </div>
      <div className="flow-timeline">
        {rows.length ? rows.map((row: any) => <FlowCard key={row.answer_log_id || row.source_id} row={row} />) : <p className="muted">回答ログはまだありません。</p>}
      </div>
    </section>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "ok" | "bad" }) {
  return (
    <div className={`metric ${tone || ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FlowCard({ row }: { row: any }) {
  const isTest = row.source_type === "test_attempt";
  const status = isTest ? answerStatus(row.is_correct, "正解", "不正解") : { label: "学習回答", tone: "neutral" as const };
  return (
    <article className={`flow-card ${status.tone}`}>
      <div className="flow-card-head">
        <div>
          <span className="phase-pill">{phaseLabel(row.phase, row.test_round)}</span>
          {row.legacy_read_only ? <span className="muted">旧試用（閲覧専用） </span> : null}
          <strong>{row.term_label || row.term_slug}</strong>
          {row.component_term ? <span className="muted"> / {row.component_term}</span> : null}
        </div>
        <span className="status-pill">{status.label}</span>
      </div>
      <div className="flow-card-body">
        <div>
          <span className="field-label">問題</span>
          <p>{row.question_body_snapshot || row.question_body || "-"}</p>
        </div>
        <div>
          <span className="field-label">選択した回答</span>
          <p>{row.selected_option_body || row.learner_response || "-"}</p>
        </div>
        <div className="flow-meta">
          <span>誤概念: {row.misconception_type || row.learning_misconception_type || "none"}</span>
          <span>回答時間: {formatSeconds(row.response_time_sec)}</span>
          <span>{formatDateTime(row.answered_at || row.created_at)}</span>
        </div>
      </div>
    </article>
  );
}

function answerStatus(value: boolean | null | undefined, okLabel: string, badLabel: string) {
  if (value === true) return { label: okLabel, tone: "ok" };
  if (value === false) return { label: badLabel, tone: "bad" };
  return { label: "未判定", tone: "neutral" };
}

function phaseLabel(phase: string, testRound?: string) {
  if (testRound === "test") return "テスト";
  const retestMatch = /^retest_(\d+)$/.exec(testRound || "");
  if (retestMatch) return `再テスト${retestMatch[1]}`;
  const labels: Record<string, string> = {
    pretest: "テスト",
    learning: "学習",
    retest: "再テスト1",
    final_test: "再テスト1",
    l0_check: "L0確認",
  };
  return labels[phase] || phase || "-";
}

function flowTime(row: any) {
  return row.answered_at || row.created_at || row.question_shown_at || "";
}

function formatSeconds(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  return `${Math.round(Number(value) * 10) / 10}秒`;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "-";
  return value.replace("T", " ").slice(0, 19);
}

function LogList({ title, rows, fields }: { title: string; rows?: any[]; fields: string[] }) {
  const visibleRows = (rows || []).slice(0, 12);
  return (
    <details className="notice">
      <summary>{title}</summary>
      {visibleRows.length ? (
        <table className="table compact-table">
          <thead>
            <tr>
              {fields.map((field) => (
                <th key={field}>{LOG_FIELD_LABELS[field] || field}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, index) => (
              <tr key={row.id || row.attempt_id || row.tutor_turn_id || index}>
                {fields.map((field) => (
                  <td key={field}>{formatCell(field, row?.[field])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">ログはまだありません。</p>
      )}
    </details>
  );
}

function SessionLog({ sessions }: { sessions: any[] }) {
  return (
    <details className="notice">
      <summary>学習セッション</summary>
      {sessions.length ? (
        <div className="stack">
          {sessions.map((session) => (
            <div className="notice" key={session.tutor_session_id}>
              <strong>
                {session.term_label} session {session.session_index}
              </strong>
              <LogList title="学習ターン詳細" rows={session.turns} fields={["turn_index", "learning_stage", "component_term", "next_learning_stage", "learning_misconception_type", "teaching_strategy", "question_shown_at", "answered_at", "response_time_sec", "created_at"]} />
              {session.turns?.slice(0, 3).map((turn: any) => (
                <details key={turn.tutor_turn_id}>
                  <summary>turn {turn.turn_index} 詳細</summary>
                  <pre>{JSON.stringify(turn, null, 2)}</pre>
                </details>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">学習セッションはまだありません。</p>
      )}
    </details>
  );
}

function formatCell(field: string, value: any) {
  if (field === "learning_material_glossary_mode") return materialGlossaryModeLabel(value);
  if (value === null || value === undefined) return "-";
  if (field === "question_set_mode") return questionSetLabel(value);
  if (field === "test_page_mode" || field === "effective_test_page_mode") return value === "per_term" ? "用語ごと（2設問／ページ）" : "設問ごと";
  if (field === "test_timing_unit" || field === "response_time_unit") return value === "term_page" ? "用語ページ" : value === "per_question" ? "設問" : String(value);
  if (typeof value === "boolean") {
    if (field === "legacy_read_only") return value ? "閲覧専用" : "現行";
    if (field === "is_correct") return value ? "正解" : "不正解";
    if (field === "completed") return value ? "完了" : "未完了";
    return value ? "あり" : "なし";
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
