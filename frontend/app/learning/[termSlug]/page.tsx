"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, requireParticipant } from "@/lib/api";

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
  practice_question: { body: string; options?: Option[]; items?: PracticeItem[]; selection_mode?: "single" | "multiple"; min_selections?: number; max_selections?: number };
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
  item_results?: ItemResult[];
};

function learningStageLabel(stage?: string, backendLabel?: string) {
  if (backendLabel) return backendLabel;
  if (stage === "enrichment") return "豊富化";
  if (stage === "conceptual_change") return "概念変化";
  if (stage === "final_feedback") return "教材フィードバック";
  return "概念変化";
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
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const bootedTermRef = useRef<string | null>(null);
  const actionInFlightRef = useRef(false);

  const nextHref = useMemo(() => {
    if (typeof window === "undefined") return "/retest";
    const targets = JSON.parse(localStorage.getItem("learning_targets") || "[]") as string[];
    const idx = targets.indexOf(termSlug);
    return idx >= 0 && idx + 1 < targets.length ? `/learning/${targets[idx + 1]}` : "/retest";
  }, [termSlug]);

  useEffect(() => {
    async function boot() {
      if (bootedTermRef.current === termSlug) return;
      bootedTermRef.current = termSlug;
      setSessionId("");
      setTurn(null);
      setFeedback(null);
      setResponse("");
      setSelectedOptionId("");
      setSelectedOptionIds([]);
      setSelectedItemOptionIds({});
      setError("");
      try {
        const session = await api<{ tutor_session_id: string }>("/api/tutor-sessions", {
          method: "POST",
          body: JSON.stringify({ participant_id: requireParticipant(), term_slug: termSlug })
        });
        setSessionId(session.tutor_session_id);
        const data = await api<Turn>(`/api/tutor-sessions/${session.tutor_session_id}/turns`, { method: "POST", body: JSON.stringify({}) });
        setTurn(data);
        setTurnStartedAt(Date.now());
        setTurnShownAt(new Date().toISOString());
      } catch (err) {
        bootedTermRef.current = null;
        setError(err instanceof Error ? err.message : String(err));
      }
    }
    boot();
  }, [termSlug]);

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
      const data = await api<Feedback>(`/api/tutor-turns/${turn.turn_id}/respond`, {
        method: "POST",
        body: JSON.stringify({
          selected_option_id: isMultiple ? (selectedOptionIds[0] || null) : (selectedOptionId || null),
          selected_option_ids: isMultiple ? selectedOptionIds : null,
          selected_item_option_ids: items.length ? selectedItemOptionIds : null,
          learner_response: isMultiple ? selectedOptions.map((option) => option.label).join(" / ") : (selectedOption?.body || response),
          response_time_sec: responseTimeSec,
          question_shown_at: turnShownAt,
          answered_at: answeredAt
        })
      });
      const updatedTurn = {
        ...turn,
        scaffolding_level: data.next_scaffolding_level,
        learning_stage: data.next_learning_stage || turn.learning_stage,
        component_index: data.next_component_index ?? turn.component_index,
      };
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
    actionInFlightRef.current = true;
    setSubmitting(true);
    setError("");
    try {
      const next = await api<Turn>(`/api/tutor-sessions/${sessionId}/turns`, { method: "POST", body: JSON.stringify({}) });
      setTurn(next);
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

  return (
    <AppShell step="学習セッション">
      <section className="panel stack">
        <h1>学習セッション</h1>
        {error ? <div className="danger">{error}</div> : null}
        {turn ? (
          <>
            <div className="notice">
              <strong>今回の学習</strong>
              <p>対象概念: {turn.term_label || termSlug}</p>
              <p>段階: {learningStageLabel(turn.learning_stage, turn.learning_stage_label)}</p>
              <p>{turn.learning_stage === "enrichment" ? "不足知識を補います" : "誤った捉え方を見直します"}</p>
            </div>
            {feedback ? (
              <>
                <section className="learning-block material-block" aria-labelledby="feedback-title">
                  <h2 id="feedback-title">教材フィードバック</h2>
                  <p className="preserve-lines">{feedback.feedback}</p>
                  {feedback.item_results?.length ? (
                    <div className="stack">
                      {feedback.item_results.map((item) => (
                        <article className={`result-card ${item.is_correct ? "correct" : "incorrect"}`} key={item.component_term}>
                          <h3>{item.component_term}: {item.is_correct ? "正解" : "不正解"}</h3>
                          <p>あなたの回答: {item.selected_option_body || "未選択"}</p>
                          <p>正解: {item.correct_answer}</p>
                          <p>{item.feedback}</p>
                        </article>
                      ))}
                    </div>
                  ) : null}
                </section>
                <div className="actions">
                  <button className="secondary" onClick={() => feedback.session_completed ? router.push(nextHref) : continueLearning()} disabled={submitting}>
                    {feedback.session_completed ? "次へ" : "次の確認へ"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="learning-layout">
                  <section className="learning-block material-block" aria-labelledby="material-title">
                    <h2 id="material-title">教材</h2>
                    <p className="preserve-lines">{turn.tutor_message}</p>
                  </section>
                  <section className="learning-block problem-block" aria-labelledby="problem-title">
                    <h2 id="problem-title">問題</h2>
                    <p>{turn.practice_question?.body || turn.learner_prompt}</p>
                    {turn.practice_question?.items?.length ? (
                      <div className="stack">
                        {turn.practice_question.items.map((item) => (
                          <article className="component-question" key={item.component_term}>
                            <h3>{item.component_term}</h3>
                            {item.material ? <p className="preserve-lines">{item.material}</p> : null}
                            <p>{item.body}</p>
                            <div className="options">
                              {(item.options || []).map((option) => (
                                <label className="option" key={option.option_id}>
                                  <input
                                    type="radio"
                                    name={`learning-option-${item.component_term}`}
                                    value={option.option_id}
                                    checked={selectedItemOptionIds[item.component_term] === option.option_id}
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
                                  disabled={isDisabled}
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
                        <textarea value={response} onChange={(event) => setResponse(event.target.value)} />
                      </label>
                    )}
                  </section>
                </div>
                <div className="actions">
                  <button
                    onClick={submit}
                    disabled={
                      submitting ||
                      (turn.practice_question?.selection_mode === "multiple" &&
                        !multipleSelectionState(turn.practice_question.options || [], selectedOptionIds, turn.practice_question.min_selections ?? 3).isComplete)
                    }
                  >
                    {submitting ? "回答を確認中..." : "回答を確認"}
                  </button>
                </div>
              </>
            )}
          </>
        ) : (
          <p>読み込み中...</p>
        )}
      </section>
    </AppShell>
  );
}
