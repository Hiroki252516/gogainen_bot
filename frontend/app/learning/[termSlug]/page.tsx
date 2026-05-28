"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, requireParticipant } from "@/lib/api";

type Turn = { turn_id: string; tutor_message: string; learner_prompt: string; practice_question: { body: string } };

export default function LearningPage() {
  const router = useRouter();
  const params = useParams<{ termSlug: string }>();
  const termSlug = params.termSlug;
  const [turn, setTurn] = useState<Turn | null>(null);
  const [response, setResponse] = useState("");
  const [feedback, setFeedback] = useState("");
  const [confidence, setConfidence] = useState("3");
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
        const data = await api<Turn>(`/api/tutor-sessions/${session.tutor_session_id}/turns`, { method: "POST", body: JSON.stringify({}) });
        setTurn(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
    boot();
  }, [termSlug]);

  async function submit() {
    if (!turn) return;
    const data = await api<{ feedback: string }>(`/api/tutor-turns/${turn.turn_id}/respond`, {
      method: "POST",
      body: JSON.stringify({ learner_response: response, confidence: Number(confidence) })
    });
    setFeedback(data.feedback);
  }

  return (
    <AppShell step="学習セッション">
      <section className="panel stack">
        <h1>学習セッション</h1>
        {error ? <div className="danger">{error}</div> : null}
        {turn ? (
          <>
            <div className="notice">
              <p>{turn.tutor_message}</p>
              <strong>{turn.learner_prompt}</strong>
            </div>
            <p className="muted">{turn.practice_question?.body}</p>
            <label>
              あなたの回答・自己説明
              <textarea value={response} onChange={(event) => setResponse(event.target.value)} />
            </label>
            <label>
              自信度
              <select value={confidence} onChange={(event) => setConfidence(event.target.value)}>
                {[1, 2, 3, 4, 5].map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <div className="actions">
              <button onClick={submit}>回答を確認</button>
              {feedback ? (
                <button className="secondary" onClick={() => router.push(nextHref)}>
                  次へ
                </button>
              ) : null}
            </div>
            {feedback ? <div className="notice">{feedback}</div> : null}
          </>
        ) : (
          <p>読み込み中...</p>
        )}
      </section>
    </AppShell>
  );
}
