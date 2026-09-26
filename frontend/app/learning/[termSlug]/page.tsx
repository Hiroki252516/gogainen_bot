"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { GiveUpButton } from "@/components/GiveUpButton";
import { MarkdownText } from "@/components/MarkdownText";
import { CheckingFlow, useLearningTargetFlowGuard } from "@/components/ParticipantFlowGuard";
import { postIdempotent, requireParticipant } from "@/lib/api";

type Option = { option_id: string; label: string; body: string };
type PracticeItem = {
  component_term: string;
  material?: string;
  body: string;
  expected_answer?: string;
  question_type?: string;
  options?: Option[];
};

type Turn = {
  turn_id: string;
  term_slug?: string;
  term_label?: string;
  tutor_message: string;
  learner_prompt: string;
  practice_question: { body: string; options?: Option[]; items?: PracticeItem[]; selection_mode?: "single" | "multiple"; min_selections?: number; max_selections?: number; learning_variant_index?: number };
  turn_index: number;
  max_turns: number;
  learning_stage?: string;
  learning_stage_label?: string;
  component_term?: string | null;
  component_index?: number;
  component_total?: number;
  scaffolding_level?: string;
};

type ItemResult = {
  component_term: string;
  question_body: string;
  selected_option_body?: string | null;
  correct_answer?: string | null;
  is_correct: boolean;
  is_sufficient: boolean;
  feedback: string;
};

type Feedback = {
  feedback: string;
  next_action: string;
  is_sufficient: boolean;
  session_completed: boolean;
  learning_stage?: string;
  stage_completed?: boolean;
  next_learning_stage?: string;
  component_term?: string | null;
  component_index?: number;
  component_total?: number;
  next_component_index?: number;
  learning_misconception_type?: string | null;
  learning_misconception_confidence?: number | null;
  learning_misconception_reason?: string | null;
  next_scaffolding_level: string;
  turn_index: number;
  max_turns: number;
  attempts_used?: number;
  remaining_attempts?: number;
  session_ended_by_attempt_limit?: boolean;
  item_results?: ItemResult[];
  next_url?: string;
};

type QuestionProgress = { current: number; total: number; remainingAttempts: number };

const ATTEMPTS_PER_PROBLEM = 3;

function progressForNewQuestion(termSlug: string, turn: Pick<Turn, "turn_index" | "max_turns">): QuestionProgress {
  let targets: string[] = [];
  if (typeof window !== "undefined") {
    try {
      const storedTargets = JSON.parse(localStorage.getItem("learning_targets") || "[]");
      targets = Array.isArray(storedTargets) ? storedTargets.filter((target): target is string => typeof target === "string") : [];
    } catch {
      targets = [];
    }
  }
  const turnIndex = Math.max(turn.turn_index, 1);
  const targetIndex = targets.indexOf(termSlug);
  return {
    current: targetIndex >= 0 ? targetIndex + 1 : 1,
    total: targets.length || turn.max_turns,
    remainingAttempts: Math.max(ATTEMPTS_PER_PROBLEM - turnIndex, 0),
  };
}

function componentDisplay(turn: Turn) {
  const items = turn.practice_question?.items || [];
  if (items.length) {
    return `用語: ${items.map((item) => item.component_term).join("、")} (${items.length}件)`;
  }
  if (typeof turn.component_index === "number" && typeof turn.component_total === "number") {
    return `用語: ${turn.component_term} ${turn.component_index + 1} / ${turn.component_total}`;
  }
  return `用語: ${turn.component_term || "構成用語"}`;
}

function multipleSelectionState(options: Option[], selectedIds: string[], requiredSelections = 3) {
  const selectedOptions = options.filter((option) => selectedIds.includes(option.option_id));
  const hasUnknown = selectedOptions.some((option) => option.label === "J");
  const normalSelectedCount = selectedOptions.filter((option) => option.label !== "J").length;
  const isComplete = (hasUnknown && selectedOptions.length === 1) || (!hasUnknown && normalSelectedCount === requiredSelections);
  return { selectedOptions, hasUnknown, normalSelectedCount, reachedLimit: !hasUnknown && normalSelectedCount >= requiredSelections, isComplete };
}

function nextMultipleSelection(options: Option[], selectedIds: string[], option: Option, requiredSelections = 3) {
  const isSelected = selectedIds.includes(option.option_id);
  if (isSelected) return selectedIds.filter((id) => id !== option.option_id);
  if (option.label === "J") return [option.option_id];
  const withoutUnknown = selectedIds.filter((id) => options.find((item) => item.option_id === id)?.label !== "J");
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
  const [response, setResponse] = useState("");
  const [selectedOptionId, setSelectedOptionId] = useState("");
  const [selectedOptionIds, setSelectedOptionIds] = useState<string[]>([]);
  const [selectedItemOptionIds, setSelectedItemOptionIds] = useState<Record<string, string>>({});
  const [turnStartedAt, setTurnStartedAt] = useState(() => Date.now());
  const [turnShownAt, setTurnShownAt] = useState(() => new Date().toISOString());
  const [questionProgress, setQuestionProgress] = useState<QuestionProgress | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const bootedTermRef = useRef<string | null>(null);
  const actionInFlightRef = useRef(false);
  const flow = useLearningTargetFlowGuard(termSlug);
  const flowReady = flow.ready;

  const nextHref = useMemo(() => {
    if (typeof window === "undefined") return "/retest";
    const targets = JSON.parse(localStorage.getItem("learning_targets") || "[]") as string[];
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
      setResponse("");
      setSelectedOptionId("");
      setSelectedOptionIds([]);
      setSelectedItemOptionIds({});
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
    const items = turn.practice_question?.items || [];
    const isMultiple = turn.practice_question?.selection_mode === "multiple";
    const requiredSelections = turn.practice_question?.min_selections ?? 3;
    const selectionState = multipleSelectionState(options, selectedOptionIds, requiredSelections);
    if (isMultiple && !selectionState.isComplete) {
      setError(`A〜Iから${requiredSelections}つ選ぶか、「わからない」だけを選んでください。`);
      return;
    }
    if (!isMultiple && options.length && !selectedOptionId) {
      setError("選択肢を選んでください。");
      return;
    }
    if (items.length && items.some((item) => !selectedItemOptionIds[item.component_term])) {
      setError("すべての確認問題で選択肢を選んでください。");
      return;
    }
    actionInFlightRef.current = true;
    setSubmitting(true);
    setError("");
    try {
      const selectedOption = options.find((option) => option.option_id === selectedOptionId);
      const selectedOptions = options.filter((option) => selectedOptionIds.includes(option.option_id));
      const answeredAt = new Date().toISOString();
      const responseTimeSec = Math.max(0.001, (Date.now() - turnStartedAt) / 1000);
      const responseBody = {
        selected_option_id: isMultiple ? (selectedOptionIds[0] || null) : (selectedOptionId || null),
        selected_option_ids: isMultiple ? selectedOptionIds : null,
        selected_item_option_ids: items.length ? selectedItemOptionIds : null,
        learner_response: isMultiple ? selectedOptions.map((option) => option.label).join(" / ") : (selectedOption?.body || response),
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
        scaffolding_level: data.next_scaffolding_level,
        learning_stage: data.next_learning_stage || turn.learning_stage,
        component_index: data.next_component_index ?? turn.component_index,
      };
      // Grading feedback belongs to the current problem.  Keep its position
      // unchanged while the next retry is still part of the same problem.
      setQuestionProgress((previous) => previous ? {
        ...previous,
        remainingAttempts: data.remaining_attempts ?? (data.is_sufficient ? 0 : Math.max(previous.remainingAttempts - 1, 0)),
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
      setResponse("");
      setSelectedOptionId("");
      setSelectedOptionIds([]);
      setSelectedItemOptionIds({});
      setFeedback(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      actionInFlightRef.current = false;
      setSubmitting(false);
    }
  }

  if (!flowReady) return <CheckingFlow error={flow.error} onRetry={flow.retry} />;

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
        {turn ? (
          <>
            <div className="notice">
              <strong>学習内容：{turn.term_label || termSlug}</strong>
            </div>
            <div className="learning-layout">
              <section className="learning-block material-block" aria-labelledby="material-title">
                <h2 id="material-title">教材</h2>
                <MarkdownText>{turn.tutor_message}</MarkdownText>
              </section>
              <section className="learning-block problem-block" aria-labelledby="problem-title">
                <h2 id="problem-title">問題</h2>
                <p>{turn.practice_question?.body || turn.learner_prompt}</p>
                {turn.practice_question?.items?.length ? (
                  <div className="stack">
                    {turn.practice_question.items.map((item) => (
                      <article className="component-question" key={item.component_term}>
                        <h3>{item.component_term}</h3>
                        {item.material ? <MarkdownText className="markdown-compact">{item.material}</MarkdownText> : null}
                        <p>{item.body}</p>
                        <div className="options">
                          {(item.options || []).map((option) => (
                            <label className="option" key={option.option_id}>
                              <input
                                type="radio"
                                name={`learning-option-${item.component_term}`}
                                value={option.option_id}
                                checked={selectedItemOptionIds[item.component_term] === option.option_id}
                                disabled={submitting || Boolean(feedback)}
                                onChange={() => setSelectedItemOptionIds((current) => ({ ...current, [item.component_term]: option.option_id }))}
                              />
                              <span>
                                <strong>{option.label}.</strong> {option.body}
                              </span>
                            </label>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : turn.practice_question?.options?.length ? (
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
                                : `A〜Iから${requiredSelections}つ選ぶか、J「わからない」だけを選んでください。`}
                          </span>
                        </div>
                      );
                    })() : null}
                    <div className="options">
                      {turn.practice_question.options.map((option) => {
                        const isMultiple = turn.practice_question?.selection_mode === "multiple";
                        const requiredSelections = turn.practice_question?.min_selections ?? 3;
                        const selectionState = multipleSelectionState(turn.practice_question?.options || [], selectedOptionIds, requiredSelections);
                        const isSelected = isMultiple ? selectedOptionIds.includes(option.option_id) : selectedOptionId === option.option_id;
                        const isUnknown = option.label === "J";
                        const isDisabled =
                          isMultiple &&
                          !isSelected &&
                          ((selectionState.hasUnknown && !isUnknown) ||
                            (!isUnknown && selectionState.reachedLimit) ||
                            (isUnknown && selectionState.normalSelectedCount > 0));
                        return (
                          <label className={`option ${isDisabled ? "option-disabled" : ""} ${isUnknown ? "option-unknown" : ""}`} key={option.option_id}>
                            <input
                              type={isMultiple ? "checkbox" : "radio"}
                              name="learning-option"
                              value={option.option_id}
                              checked={isSelected}
                              disabled={submitting || Boolean(feedback) || isDisabled}
                              onChange={() => {
                                if (!isMultiple) {
                                  setSelectedOptionId(option.option_id);
                                  return;
                                }
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
                ) : (
                  <label>
                    あなたの回答・自己説明
                    <textarea disabled={submitting || Boolean(feedback)} value={response} onChange={(event) => setResponse(event.target.value)} />
                  </label>
                )}
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
                {feedback.item_results?.length ? (
                  <div className="stack">
                    {feedback.item_results.map((item) => (
                      <article className={`result-card ${item.is_correct ? "correct" : "incorrect"}`} key={item.component_term}>
                        <h3>{item.component_term}: {item.is_correct ? "正解" : "不正解"}</h3>
                        <p>あなたの回答: {item.selected_option_body || "未選択"}</p>
                        <p>正解: {item.correct_answer}</p>
                        <MarkdownText className="markdown-compact">{item.feedback}</MarkdownText>
                      </article>
                    ))}
                  </div>
                ) : null}
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
