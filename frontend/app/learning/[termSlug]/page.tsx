"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, requireParticipant } from "@/lib/api";

type Prerequisite = {
  prerequisite_id: string;
  term_label: string;
  material: string;
  check_question: string;
  display_order: number;
  status: string;
  attempt_count: number;
  max_attempts: number;
  last_feedback?: string | null;
  remediation_material?: string | null;
};

type LearningSession = {
  learning_session_id: string;
  group_condition: "control" | "proposed";
  status: string;
  term_slug: string;
  term_label: string;
  term_description?: string | null;
  prerequisites: Prerequisite[];
  current_prerequisite_id?: string | null;
  concept?: { material?: string | null; prompt?: string | null; attempt_count: number; max_attempts: number } | null;
  last_feedback?: string | null;
  blocked_reason?: string | null;
};

type ControlTurn = {
  turn_id: string;
  tutor_message: string;
  learner_prompt: string;
  practice_question?: { body: string };
};

export default function LearningPage() {
  const router = useRouter();
  const params = useParams<{ termSlug: string }>();
  const termSlug = params.termSlug;
  const [session, setSession] = useState<LearningSession | null>(null);
  const [controlTurn, setControlTurn] = useState<ControlTurn | null>(null);
  const [response, setResponse] = useState("");
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const nextHref = useMemo(() => {
    if (typeof window === "undefined") return "/retest";
    const targets = JSON.parse(localStorage.getItem("learning_targets") || "[]") as string[];
    const idx = targets.indexOf(termSlug);
    return idx >= 0 && idx + 1 < targets.length ? `/learning/${targets[idx + 1]}` : "/retest";
  }, [termSlug]);

  const currentPrerequisite = session?.prerequisites.find((item) => item.prerequisite_id === session.current_prerequisite_id);
  const isTerminal = session ? ["completed", "blocked", "failed"].includes(session.status) : false;

  useEffect(() => {
    async function boot() {
      try {
        const data = await api<LearningSession>("/api/learning-sessions", {
          method: "POST",
          body: JSON.stringify({ participant_id: requireParticipant(), term_slug: termSlug })
        });
        setSession(data);
        if (data.group_condition === "control" && data.status !== "completed") {
          const turn = await api<ControlTurn>(`/api/learning-sessions/${data.learning_session_id}/control-turn`, {
            method: "POST",
            body: JSON.stringify({})
          });
          setControlTurn(turn);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
    boot();
  }, [termSlug]);

  async function submit() {
    if (!session) return;
    if (!response.trim()) {
      setError("回答を入力してください。");
      return;
    }
    setSaving(true);
    setError("");
    try {
      if (session.group_condition === "control") {
        if (!controlTurn) return;
        const data = await api<{ feedback: string; session: LearningSession }>(`/api/learning-sessions/${session.learning_session_id}/control-answer`, {
          method: "POST",
          body: JSON.stringify({ turn_id: controlTurn.turn_id, learner_response: response })
        });
        setFeedback(data.feedback);
        setSession(data.session);
        setResponse("");
        return;
      }
      if (session.status === "concept_understanding") {
        const data = await api<{ feedback: string; session: LearningSession }>(`/api/learning-sessions/${session.learning_session_id}/concept-attempts`, {
          method: "POST",
          body: JSON.stringify({ learner_answer: response })
        });
        setFeedback(data.feedback);
        setSession(data.session);
        setResponse("");
        return;
      }
      if (currentPrerequisite) {
        const data = await api<{ feedback: string; session: LearningSession }>(
          `/api/learning-sessions/${session.learning_session_id}/prerequisites/${currentPrerequisite.prerequisite_id}/attempts`,
          {
            method: "POST",
            body: JSON.stringify({ learner_answer: response })
          }
        );
        setFeedback(data.feedback);
        setSession(data.session);
        setResponse("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  function goNext() {
    router.push(nextHref);
  }

  return (
    <AppShell step="学習セッション">
      <section className="panel stack">
        <h1>{session?.term_label || "学習セッション"}</h1>
        {error ? <div className="danger">{error}</div> : null}
        {!session ? <p>読み込み中...</p> : null}
        {session?.group_condition === "control" ? (
          <ControlLearningView
            session={session}
            turn={controlTurn}
            response={response}
            setResponse={setResponse}
            feedback={feedback}
            saving={saving}
            onSubmit={submit}
            onNext={goNext}
          />
        ) : null}
        {session?.group_condition === "proposed" ? (
          <ProposedLearningView
            session={session}
            currentPrerequisite={currentPrerequisite}
            response={response}
            setResponse={setResponse}
            feedback={feedback}
            saving={saving}
            terminal={isTerminal}
            onSubmit={submit}
            onNext={goNext}
          />
        ) : null}
      </section>
    </AppShell>
  );
}

function ControlLearningView({
  session,
  turn,
  response,
  setResponse,
  feedback,
  saving,
  onSubmit,
  onNext
}: {
  session: LearningSession;
  turn: ControlTurn | null;
  response: string;
  setResponse: (value: string) => void;
  feedback: string;
  saving: boolean;
  onSubmit: () => void;
  onNext: () => void;
}) {
  if (session.status === "completed") {
    return (
      <div className="stack">
        <div className="notice">{session.last_feedback || feedback || "学習を記録しました。"}</div>
        <button onClick={onNext}>次へ</button>
      </div>
    );
  }
  if (!turn) return <p>教材を準備しています...</p>;
  return (
    <div className="stack">
      <div className="notice">
        <p>{turn.tutor_message}</p>
        <strong>{turn.learner_prompt}</strong>
      </div>
      {turn.practice_question?.body ? <p className="muted">{turn.practice_question.body}</p> : null}
      <label>
        あなたの説明
        <textarea value={response} onChange={(event) => setResponse(event.target.value)} />
      </label>
      <div className="actions">
        <button onClick={onSubmit} disabled={saving}>
          回答を確認
        </button>
      </div>
      {feedback ? <div className="notice">{feedback}</div> : null}
    </div>
  );
}

function ProposedLearningView({
  session,
  currentPrerequisite,
  response,
  setResponse,
  feedback,
  saving,
  terminal,
  onSubmit,
  onNext
}: {
  session: LearningSession;
  currentPrerequisite?: Prerequisite;
  response: string;
  setResponse: (value: string) => void;
  feedback: string;
  saving: boolean;
  terminal: boolean;
  onSubmit: () => void;
  onNext: () => void;
}) {
  if (terminal) {
    return (
      <div className="stack">
        <div className={session.status === "completed" ? "notice" : "danger"}>
          {session.status === "completed" ? "この概念の学習を完了しました。" : session.blocked_reason || "この概念の学習をここで終了します。"}
        </div>
        {session.last_feedback ? <div className="notice">{session.last_feedback}</div> : null}
        <button onClick={onNext}>次へ</button>
      </div>
    );
  }
  if (session.status === "concept_understanding" && session.concept) {
    return (
      <div className="stack">
        <StageList prerequisites={session.prerequisites} />
        <div className="notice">
          <strong>概念理解</strong>
          <p>{session.concept.material}</p>
          <strong>{session.concept.prompt}</strong>
        </div>
        <p className="muted">
          試行 {session.concept.attempt_count} / {session.concept.max_attempts}
        </p>
        <label>
          前提用語を使った説明
          <textarea value={response} onChange={(event) => setResponse(event.target.value)} />
        </label>
        <button onClick={onSubmit} disabled={saving}>
          回答を確認
        </button>
        {feedback ? <div className="notice">{feedback}</div> : null}
      </div>
    );
  }
  if (!currentPrerequisite) return <p>前提用語を準備しています...</p>;
  return (
    <div className="stack">
      <StageList prerequisites={session.prerequisites} />
      <div className="notice">
        <strong>
          前提用語 {currentPrerequisite.display_order}. {currentPrerequisite.term_label}
        </strong>
        <p>{currentPrerequisite.remediation_material || currentPrerequisite.material}</p>
        <strong>{currentPrerequisite.check_question}</strong>
      </div>
      <p className="muted">
        試行 {currentPrerequisite.attempt_count} / {currentPrerequisite.max_attempts}
      </p>
      <label>
        あなたの説明
        <textarea value={response} onChange={(event) => setResponse(event.target.value)} />
      </label>
      <button onClick={onSubmit} disabled={saving}>
        回答を確認
      </button>
      {feedback || currentPrerequisite.last_feedback ? <div className="notice">{feedback || currentPrerequisite.last_feedback}</div> : null}
    </div>
  );
}

function StageList({ prerequisites }: { prerequisites: Prerequisite[] }) {
  return (
    <div className="grid">
      {prerequisites.map((item) => (
        <div className="notice" key={item.prerequisite_id}>
          <strong>{item.term_label}</strong>
          <p className="muted">{statusLabel(item.status)}</p>
        </div>
      ))}
    </div>
  );
}

function statusLabel(status: string) {
  if (status === "passed") return "通過済み";
  if (status === "review") return "再確認";
  if (status === "failed") return "未通過";
  return "確認待ち";
}
