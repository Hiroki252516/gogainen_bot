"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { GiveUpButton } from "@/components/GiveUpButton";
import { MarkdownText } from "@/components/MarkdownText";
import { LearningGlossary, type Glossary } from "@/components/LearningGlossary";
import { CheckingFlow, useLearningTargetFlowGuard } from "@/components/ParticipantFlowGuard";
import { api, postIdempotent, requireParticipant } from "@/lib/api";

type Option = { option_id: string; label: string; body: string; exclusive?: boolean };

type Turn = {
  turn_id: string;
  term_slug?: string;
  term_label?: string;
  tutor_message: string;
  glossary?: Glossary | null;
  learner_prompt: string;
  practice_question: { body: string; options?: Option[]; selection_mode?: "multiple"; min_selections?: number; max_selections?: number; learning_variant_index?: number };
  turn_index: number;
  max_turns: number;
  learning_stage?: string;
  learning_stage_label?: string;
};


type Feedback = {
  feedback: string;
  glossary?: Glossary | null;
  next_action: string;
  is_sufficient: boolean;
  session_completed: boolean;
  learning_stage?: string;
  stage_completed?: boolean;
  next_learning_stage?: string;
  learning_misconception_type?: string | null;
  learning_misconception_confidence?: number | null;
  learning_misconception_reason?: string | null;
  turn_index: number;
  max_turns: number;
  attempts_used?: number;
  remaining_attempts?: number;
  session_ended_by_attempt_limit?: boolean;
  next_url?: string;
};

type QuestionProgress = { current: number; total: number; remainingAttempts: number };

const ATTEMPTS_PER_PROBLEM = 3;

function readLearningTargetSlugs(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem("learning_targets") || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((target) => {
        if (typeof target === "string") return target;
        if (target && typeof target === "object" && "term_slug" in target) {
          const slug = (target as { term_slug?: unknown }).term_slug;
          return typeof slug === "string" ? slug : null;
        }
        return null;
      })
      .filter((slug): slug is string => Boolean(slug));
  } catch {
    return [];
  }
}

function progressForNewQuestion(termSlug: string, turn: Pick<Turn, "turn_index" | "max_turns">): QuestionProgress {
  const targets = readLearningTargetSlugs();
  const turnIndex = Math.max(turn.turn_index, 1);
  const maxAttempts = Math.max(turn.max_turns || ATTEMPTS_PER_PROBLEM, 1);
  const targetIndex = targets.indexOf(termSlug);
  return {
    current: targetIndex >= 0 ? targetIndex + 1 : 1,
    total: targets.length || 1,
    remainingAttempts: Math.max(maxAttempts - turnIndex, 0),
  };
}


function multipleSelectionState(options: Option[], selectedIds: string[], requiredSelections = 3) {
  const selectedOptions = options.filter((option) => selectedIds.includes(option.option_id));
  const hasUnknown = selectedOptions.some((option) => option.exclusive);
  const normalSelectedCount = selectedOptions.filter((option) => !option.exclusive).length;
  const isComplete = (hasUnknown && selectedOptions.length === 1) || (!hasUnknown && normalSelectedCount === requiredSelections);
  return { selectedOptions, hasUnknown, normalSelectedCount, reachedLimit: !hasUnknown && normalSelectedCount >= requiredSelections, isComplete };
}

function nextMultipleSelection(options: Option[], selectedIds: string[], option: Option, requiredSelections = 3) {
  const isSelected = selectedIds.includes(option.option_id);
  if (isSelected) return selectedIds.filter((id) => id !== option.option_id);
  if (option.exclusive) return [option.option_id];
  const withoutUnknown = selectedIds.filter((id) => !options.find((item) => item.option_id === id)?.exclusive);
  return withoutUnknown.length >= requiredSelections ? selectedIds : [...withoutUnknown, option.option_id];
}

const SUBMIT_PROGRESS_STEPS = [
  "回答を記録しています",
  "選択内容を確認しています",
  "解説を生成しています",
  "次の教材を準備しています",
];

const SESSION_LOAD_PROGRESS_STEPS = [
  "学習セッションを準備しています",
  "教材を生成しています",
  "確認問題を準備しています",
  "学習画面を表示しています",
];

function ProgressCard({ title, steps, ariaLabel }: { title: string; steps: string[]; ariaLabel: string }) {
  const [elapsedSec, setElapsedSec] = useState(0);
  const activeIndex = Math.min(steps.length - 1, Math.floor(elapsedSec / 8));

  useEffect(() => {
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="analysis-progress" role="status" aria-live="polite">
      <div className="analysis-heading">
        <span className="spinner" aria-hidden="true" />
        <div>
          <strong>{title}</strong>
          <span className="analysis-elapsed">{elapsedSec}秒経過</span>
        </div>
      </div>
      <ol aria-label={ariaLabel}>
        {steps.map((step, index) => (
          <li className={index < activeIndex ? "done" : index === activeIndex ? "active" : ""} key={step}>
            <span aria-hidden="true" />
            {step}
          </li>
        ))}
      </ol>
    </div>
  );
}

function SubmitProgress() {
  return <ProgressCard title="分析中です" steps={SUBMIT_PROGRESS_STEPS} ariaLabel="回答処理の進行状況" />;
}

function SessionLoadProgress() {
  return (
    <ProgressCard
      title="学習セッションを準備しています"
      steps={SESSION_LOAD_PROGRESS_STEPS}
      ariaLabel="学習セッション読み込みの進行状況"
    />
  );
}

function ContinueProgress() {
  return (
    <ProgressCard
      title="学習セッションを準備しています"
      steps={SESSION_LOAD_PROGRESS_STEPS}
      ariaLabel="次の確認読み込みの進行状況"
    />
  );
}

export default function LearningPage() {
  const router = useRouter();
  const params = useParams<{ termSlug: string }>();
  const termSlug = params.termSlug;
  const [sessionId, setSessionId] = useState("");
  const [turn, setTurn] = useState<Turn | null>(null);
  const [selectedOptionIds, setSelectedOptionIds] = useState<string[]>([]);
  const [turnStartedAt, setTurnStartedAt] = useState(() => Date.now());
  const [turnShownAt, setTurnShownAt] = useState(() => new Date().toISOString());
  const [questionProgress, setQuestionProgress] = useState<QuestionProgress | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [materialViewError, setMaterialViewError] = useState("");
  const bootedTermRef = useRef<string | null>(null);
  const actionInFlightRef = useRef(false);
  const flow = useLearningTargetFlowGuard(termSlug);
  const flowReady = flow.ready;

  useEffect(() => {
    const turnId = turn?.turn_id;
    if (!turnId || !flowReady) return;
    let cancelled = false;
    const record = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        await api(`/api/tutor-turns/${turnId}/material-view`, { method: "POST", body: "{}" });
        if (!cancelled) setMaterialViewError("");
      } catch {
        if (!cancelled) setMaterialViewError("教材の表示記録を保存できませんでした。回答時に再試行します。");
      }
    };
    void record();
    document.addEventListener("visibilitychange", record);
    return () => { cancelled = true; document.removeEventListener("visibilitychange", record); };
  }, [turn?.turn_id, flowReady]);

  const nextHref = useMemo(() => {
    const targets = readLearningTargetSlugs();
    const idx = targets.indexOf(termSlug);
    return idx >= 0 && idx + 1 < targets.length ? `/learning/${targets[idx + 1]}` : "/retest";
  }, [termSlug]);

  useEffect(() => {
    async function boot() {
      if (!flowReady) return;
      if (bootedTermRef.current === termSlug) return;
      bootedTermRef.current = termSlug;
      setSessionId("");
      setTurn(null);
      setQuestionProgress(null);
      setFeedback(null);
      setSelectedOptionIds([]);
      setError("");
      try {
        const participantId = requireParticipant();
        const session = await postIdempotent<{ tutor_session_id: string }>(
          "/api/tutor-sessions",
          { participant_id: participantId, term_slug: termSlug },
          `tutor_session:${participantId}:${termSlug}`,
        );
        setSessionId(session.tutor_session_id);
        const data = await postIdempotent<Turn>(
          `/api/tutor-sessions/${session.tutor_session_id}/turns`,
          {},
          `tutor_turn_generate:${session.tutor_session_id}:initial`,
        );
        setTurn(data);
        setQuestionProgress(progressForNewQuestion(termSlug, data));
        setTurnStartedAt(Date.now());
        setTurnShownAt(new Date().toISOString());
      } catch (err) {
        bootedTermRef.current = null;
        setError(err instanceof Error ? err.message : String(err));
      }
    }
    boot();
  }, [flowReady, termSlug]);

  async function submit() {
    if (!turn || actionInFlightRef.current) return;
    const options = turn.practice_question?.options || [];
    const isMultiple = turn.practice_question?.selection_mode === "multiple";
    const requiredSelections = turn.practice_question?.min_selections ?? 3;
    const selectionState = multipleSelectionState(options, selectedOptionIds, requiredSelections);
    if (isMultiple && !selectionState.isComplete) {
      setError(`選択肢から正しい説明を${requiredSelections}つ、または「わからない」のみを選んでください。`);
      return;
    }
    actionInFlightRef.current = true;
    setSubmitting(true);
    setError("");
    try {
      const answeredAt = new Date().toISOString();
      await api(`/api/tutor-turns/${turn.turn_id}/material-view`, { method: "POST", body: "{}" });
      setMaterialViewError("");
      const responseTimeSec = Math.max(0.001, (Date.now() - turnStartedAt) / 1000);
      const responseBody = {
        selected_option_ids: selectedOptionIds,
        response_time_sec: responseTimeSec,
        question_shown_at: turnShownAt,
        answered_at: answeredAt,
      };
      const data = await postIdempotent<Feedback>(
        `/api/tutor-turns/${turn.turn_id}/respond`,
        responseBody,
        `tutor_turn_respond:${turn.turn_id}`,
      );
      const updatedTurn = {
        ...turn,
        learning_stage: data.next_learning_stage || turn.learning_stage,
      };
      // Grading feedback belongs to the current problem.  Keep its position
      // unchanged while the next retry is still part of the same problem.
      setQuestionProgress((previous) => previous ? {
        ...previous,
        remainingAttempts: data.is_sufficient ? 0 : (data.remaining_attempts ?? Math.max(previous.remainingAttempts - 1, 0)),
      } : previous);
      setTurn(updatedTurn);
      setFeedback(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      actionInFlightRef.current = false;
      setSubmitting(false);
    }
  }

  async function continueLearning() {
    if (!sessionId || actionInFlightRef.current) return;
    const completedTurnId = turn?.turn_id;
    if (!completedTurnId) return;
    actionInFlightRef.current = true;
    setSubmitting(true);
    setError("");
    try {
      const next = await postIdempotent<Turn>(
        `/api/tutor-sessions/${sessionId}/turns`,
        {},
        `tutor_turn_generate:${sessionId}:after:${completedTurnId}`,
      );
      setTurn(next);
      setQuestionProgress(progressForNewQuestion(termSlug, next));
      setTurnStartedAt(Date.now());
      setTurnShownAt(new Date().toISOString());
      setSelectedOptionIds([]);
      setFeedback(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      actionInFlightRef.current = false;
      setSubmitting(false);
    }
  }

  if (!flowReady) return <CheckingFlow legacy={flow.legacy} error={flow.error} onRetry={flow.retry} />;

  const progress = questionProgress || (turn ? progressForNewQuestion(termSlug, turn) : null);
  const displayedProgress = progress ? Math.min(progress.current, progress.total) : null;

  return (
    <AppShell step="学習セッション">
      <section className="panel stack" aria-busy={submitting || (!turn && !error)}>
        <div className="topbar learning-topbar">
          <h1>学習セッション</h1>
          {progress && displayedProgress !== null ? (
            <div className="learning-progress-summary" aria-label="学習セッションの進捗">
              <div className="learning-progress-row">
                <span>学習セッションの進捗</span>
                <strong>{displayedProgress} / {progress.total}</strong>
              </div>
              <div className="learning-progress-row">
                <span>この問題の残り挑戦回数</span>
                <strong>{progress.remainingAttempts}回</strong>
              </div>
            </div>
          ) : null}
        </div>
        {error ? <div className="danger">{error}</div> : null}
        {materialViewError ? <div className="danger" role="alert">{materialViewError}</div> : null}
        {turn ? (
          <>
            <div className="notice">
              <strong>学習内容：{turn.term_label || termSlug}</strong>
            </div>
            <div className="learning-layout">
              <section className="learning-block material-block" aria-labelledby="material-title">
                <h2 id="material-title">教材</h2>
                <MarkdownText>{turn.tutor_message}</MarkdownText>
                <LearningGlossary glossary={turn.glossary} label="教材の用語の補足" />
              </section>
              <section className="learning-block problem-block" aria-labelledby="problem-title">
                <h2 id="problem-title">問題</h2>
                <p>{turn.practice_question?.body || turn.learner_prompt}</p>
                {turn.practice_question?.options?.length ? (
                  <>
                    {turn.practice_question.selection_mode === "multiple" ? (() => {
                      const requiredSelections = turn.practice_question.min_selections ?? 3;
                      const selectionState = multipleSelectionState(turn.practice_question.options || [], selectedOptionIds, requiredSelections);
                      return (
                        <div className={`selection-status ${selectionState.isComplete ? "ok" : ""}`}>
                          <strong>{selectionState.hasUnknown ? "わからないを選択中" : `${selectionState.normalSelectedCount}/${requiredSelections} 選択済み`}</strong>
                          <span>
                            {selectionState.hasUnknown
                              ? "わからないを選ぶ場合は単独選択です。"
                              : selectionState.reachedLimit
                                ? "上限に達しました。変更するには選択済みの項目を外してください。"
                                : `選択肢から正しい説明を${requiredSelections}つ、または「わからない」のみを選んでください。`}
                          </span>
                        </div>
                      );
                    })() : null}
                    <div className="options">
                      {turn.practice_question.options.map((option) => {
                        const isMultiple = turn.practice_question?.selection_mode === "multiple";
                        const requiredSelections = turn.practice_question?.min_selections ?? 3;
                        const selectionState = multipleSelectionState(turn.practice_question?.options || [], selectedOptionIds, requiredSelections);
                        const isSelected = selectedOptionIds.includes(option.option_id);
                        const isUnknown = Boolean(option.exclusive);
                        const isDisabled =
                          isMultiple &&
                          !isSelected &&
                          ((selectionState.hasUnknown && !isUnknown) ||
                            (!isUnknown && selectionState.reachedLimit) ||
                            (isUnknown && selectionState.normalSelectedCount > 0));
                        return (
                          <label className={`option ${isDisabled ? "option-disabled" : ""} ${isUnknown ? "option-unknown" : ""}`} key={option.option_id}>
                            <input
                              type="checkbox"
                              name="learning-option"
                              value={option.option_id}
                              checked={isSelected}
                              disabled={submitting || Boolean(feedback) || isDisabled}
                              onChange={() => {
                                setSelectedOptionIds((currentIds) => nextMultipleSelection(turn.practice_question?.options || [], currentIds, option, requiredSelections));
                              }}
                            />
                            <span>
                              <strong>{option.label}.</strong> {option.body}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </>
                ) : null}
              </section>
            </div>
            {feedback ? (
              <section
                className={`learning-block material-block feedback-card ${feedback.is_sufficient ? "feedback-card-ok" : "feedback-card-error"}`}
                aria-labelledby="feedback-title"
                role="status"
                aria-live="polite"
              >
                <h2 id="feedback-title">教材フィードバック</h2>
                <strong className="feedback-status">
                  {feedback.is_sufficient ? "正解です。" : "不正解です。"}
                </strong>
                <MarkdownText>{feedback.feedback}</MarkdownText>
                <LearningGlossary glossary={feedback.glossary} label="回答後解説の用語の補足" />
              </section>
            ) : null}
            {submitting ? (feedback ? <ContinueProgress /> : <SubmitProgress />) : null}
            <div className="actions">
              {!feedback ? (
                <button
                  onClick={submit}
                  disabled={
                    submitting ||
                    (turn.practice_question?.selection_mode === "multiple" &&
                      !multipleSelectionState(turn.practice_question.options || [], selectedOptionIds, turn.practice_question.min_selections ?? 3).isComplete)
                  }
                >
                  {submitting ? "分析中..." : "回答を確認"}
                </button>
              ) : (
                <button className="secondary" onClick={() => feedback.session_completed ? router.replace(feedback.next_url || nextHref) : continueLearning()} disabled={submitting}>
                  {feedback.session_completed ? "次へ" : submitting ? "次の確認を準備中..." : "次の確認へ"}
                </button>
              )}
            </div>
            {!feedback?.session_completed ? (
              <div className="give-up-footer">
                <GiveUpButton mode="learning" disabled={submitting} />
              </div>
            ) : null}
          </>
        ) : error ? null : <SessionLoadProgress />}
      </section>
    </AppShell>
  );
}
