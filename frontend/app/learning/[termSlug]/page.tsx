"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, requireParticipant } from "@/lib/api";

type SessionMisconception = {
  label: string;
  misconception_type?: string | null;
  reason?: string | null;
};

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
  practice_question: { body: string; options?: Option[]; items?: PracticeItem[] };
  turn_index: number;
  max_turns: number;
  learning_stage?: string;
  learning_stage_label?: string;
  component_term?: string | null;
  component_index?: number;
  component_total?: number;
  scaffolding_level?: string;
  initial_misconception_type?: string | null;
  misconception_type?: string | null;
  latest_learning_misconception_type?: string | null;
  latest_learning_misconception_reason?: string | null;
  session_misconception_history?: SessionMisconception[];
  teaching_strategy?: string;
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

function judgementLabel(feedback: Feedback | null) {
  if (!feedback) return "未判定";
  return feedback.is_sufficient ? "十分" : "不十分";
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

export default function LearningPage() {
  const router = useRouter();
  const params = useParams<{ termSlug: string }>();
  const termSlug = params.termSlug;
  const [sessionId, setSessionId] = useState("");
  const [turn, setTurn] = useState<Turn | null>(null);
  const [response, setResponse] = useState("");
  const [selectedOptionId, setSelectedOptionId] = useState("");
  const [selectedItemOptionIds, setSelectedItemOptionIds] = useState<Record<string, string>>({});
  const [turnStartedAt, setTurnStartedAt] = useState(() => Date.now());
  const [turnShownAt, setTurnShownAt] = useState(() => new Date().toISOString());
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const nextHref = useMemo(() => {
    if (typeof window === "undefined") return "/retest";
    const targets = JSON.parse(localStorage.getItem("learning_targets") || "[]") as string[];
    const idx = targets.indexOf(termSlug);
    return idx >= 0 && idx + 1 < targets.length ? `/learning/${targets[idx + 1]}` : "/retest";
  }, [termSlug]);

  useEffect(() => {
    async function boot() {
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
        setError(err instanceof Error ? err.message : String(err));
      }
    }
    boot();
  }, [termSlug]);

  async function submit() {
    if (!turn || submitting) return;
    const options = turn.practice_question?.options || [];
    const items = turn.practice_question?.items || [];
    if (options.length && !selectedOptionId) {
      setError("選択肢を選んでください。");
      return;
    }
    if (items.length && items.some((item) => !selectedItemOptionIds[item.component_term])) {
      setError("すべての確認問題で選択肢を選んでください。");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const selectedOption = options.find((option) => option.option_id === selectedOptionId);
      const answeredAt = new Date().toISOString();
      const responseTimeSec = Math.max(0.001, (Date.now() - turnStartedAt) / 1000);
      const data = await api<Feedback>(`/api/tutor-turns/${turn.turn_id}/respond`, {
        method: "POST",
        body: JSON.stringify({
          selected_option_id: selectedOptionId || null,
          selected_item_option_ids: items.length ? selectedItemOptionIds : null,
          learner_response: selectedOption?.body || response,
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
        latest_learning_misconception_type: data.learning_misconception_type ?? turn.latest_learning_misconception_type,
        latest_learning_misconception_reason: data.learning_misconception_reason ?? turn.latest_learning_misconception_reason
      };
      setTurn(updatedTurn);
      setFeedback(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function continueLearning() {
    if (!sessionId || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const next = await api<Turn>(`/api/tutor-sessions/${sessionId}/turns`, { method: "POST", body: JSON.stringify({}) });
      setTurn(next);
      setTurnStartedAt(Date.now());
      setTurnShownAt(new Date().toISOString());
      setResponse("");
      setSelectedOptionId("");
      setSelectedItemOptionIds({});
      setFeedback(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
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
              <p>段階: {turn.learning_stage_label || "用語理解"}</p>
              {turn.learning_stage === "term_understanding" ? (
                <p>{componentDisplay(turn)}</p>
              ) : (
                <p>対象概念全体を説明します</p>
              )}
            </div>
            <div className="notice">
              <strong>デバッグ</strong>
              <p>事前テスト由来の誤概念: {turn.initial_misconception_type || turn.misconception_type || "none"}</p>
              <p>学習内の現在判定: {feedback?.learning_misconception_type || turn.latest_learning_misconception_type || "未判定"}</p>
              <p>learning_stage: {feedback?.next_learning_stage || turn.learning_stage || "none"}</p>
              <p>回答判定: {judgementLabel(feedback)}</p>
              <p className="muted">teaching_strategy: {turn.teaching_strategy || "none"}</p>
              {turn.session_misconception_history?.length ? (
                <p className="muted">
                  学習内判定履歴: {turn.session_misconception_history.map((item) => `${item.label} ${item.misconception_type || "none"}`).join(" / ")}
                </p>
              ) : null}
              {feedback?.learning_misconception_reason ? <p className="muted">学習内判定理由: {feedback.learning_misconception_reason}</p> : null}
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
                      <div className="options">
                        {turn.practice_question.options.map((option) => (
                          <label className="option" key={option.option_id}>
                            <input
                              type="radio"
                              name="learning-option"
                              value={option.option_id}
                              checked={selectedOptionId === option.option_id}
                              onChange={() => setSelectedOptionId(option.option_id)}
                            />
                            <span>
                              <strong>{option.label}.</strong> {option.body}
                            </span>
                          </label>
                        ))}
                      </div>
                    ) : (
                      <label>
                        あなたの回答・自己説明
                        <textarea value={response} onChange={(event) => setResponse(event.target.value)} />
                      </label>
                    )}
                  </section>
                </div>
                <div className="actions">
                  <button onClick={submit} disabled={submitting}>
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
