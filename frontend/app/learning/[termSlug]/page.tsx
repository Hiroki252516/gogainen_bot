"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, requireParticipant } from "@/lib/api";

type Turn = {
  turn_id: string;
  tutor_message: string;
  learner_prompt: string;
  practice_question: { body: string };
  turn_index: number;
  max_turns: number;
  scaffolding_level: string;
  misconception_type: string | null;
  teaching_strategy: string;
};

type Feedback = { feedback: string; next_action: string; session_completed: boolean; next_scaffolding_level: string; turn_index: number; max_turns: number };

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
      setFeedback(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }


  async function nextTurn() {
    if (!sessionId || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const data = await api<Turn>(`/api/tutor-sessions/${sessionId}/turns`, { method: "POST", body: JSON.stringify({}) });
      setTurn(data);
      setResponse("");
      setFeedback(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  const canContinueTurn = feedback && !feedback.session_completed && turn && turn.turn_index < turn.max_turns;

  return (
    <AppShell step="学習セッション">
      <section className="panel stack">
        <h1>学習セッション</h1>
        {error ? <div className="danger">{error}</div> : null}
        {turn ? (
          <>
            <div className="notice">
              <strong>デバッグ</strong>
              <p>誤概念タイプ: {turn.misconception_type || "none"} / 足場掛けレベル: {turn.scaffolding_level} / ターン: {turn.turn_index} / {turn.max_turns}</p>
              <p className="muted">teaching_strategy: {turn.teaching_strategy}</p>
            </div>
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
              <button onClick={submit} disabled={submitting || Boolean(feedback)}>
                {submitting ? "回答を確認中..." : "回答を確認"}
              </button>
              {canContinueTurn ? (
                <button className="secondary" onClick={nextTurn} disabled={submitting}>
                  {submitting ? "次のターンを準備中..." : "次のターン"}
                </button>
              ) : feedback ? (
                <button className="secondary" onClick={() => router.push(nextHref)}>
                  次へ
                </button>
              ) : null}
            </div>
            {feedback ? <div className="notice">{feedback.feedback}</div> : null}
          </>
        ) : (
          <p>読み込み中...</p>
        )}
      </section>
    </AppShell>
  );
}
