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

type Turn = {
  turn_id: string;
  term_slug?: string;
  term_label?: string;
  tutor_message: string;
  learner_prompt: string;
  practice_question: { body: string };
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
};

function judgementLabel(feedback: Feedback | null) {
  if (!feedback) return "未判定";
  return feedback.is_sufficient ? "十分" : "不十分";
}

export default function LearningPage() {
  const router = useRouter();
  const params = useParams<{ termSlug: string }>();
  const termSlug = params.termSlug;
  const [sessionId, setSessionId] = useState("");
  const [turn, setTurn] = useState<Turn | null>(null);
  const [response, setResponse] = useState("");
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
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
    boot();
  }, [termSlug]);

  async function submit() {
    if (!turn || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const data = await api<Feedback>(`/api/tutor-turns/${turn.turn_id}/respond`, {
        method: "POST",
        body: JSON.stringify({ learner_response: response })
      });
      const updatedTurn = {
        ...turn,
        scaffolding_level: data.next_scaffolding_level,
        learning_stage: data.next_learning_stage || turn.learning_stage,
        component_index: data.next_component_index ?? turn.component_index,
        latest_learning_misconception_type: data.learning_misconception_type ?? turn.latest_learning_misconception_type,
        latest_learning_misconception_reason: data.learning_misconception_reason ?? turn.latest_learning_misconception_reason
      };
      if (!data.session_completed && sessionId) {
        const next = await api<Turn>(`/api/tutor-sessions/${sessionId}/turns`, { method: "POST", body: JSON.stringify({}) });
        setTurn(next);
        setResponse("");
        setFeedback(null);
      } else {
        setTurn(updatedTurn);
        setFeedback(data);
      }
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
                <p>用語: {turn.component_term} {typeof turn.component_index === "number" && typeof turn.component_total === "number" ? `${turn.component_index + 1} / ${turn.component_total}` : ""}</p>
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
                  <p>{feedback.feedback}</p>
                </section>
                <div className="actions">
                  <button className="secondary" onClick={() => router.push(nextHref)}>
                    次へ
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="learning-layout">
                  <section className="learning-block material-block" aria-labelledby="material-title">
                    <h2 id="material-title">教材</h2>
                    <p>{turn.tutor_message}</p>
                  </section>
                  <section className="learning-block problem-block" aria-labelledby="problem-title">
                    <h2 id="problem-title">問題</h2>
                    <p>{turn.practice_question?.body || turn.learner_prompt}</p>
                    <label>
                      あなたの回答・自己説明
                      <textarea value={response} onChange={(event) => setResponse(event.target.value)} />
                    </label>
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
