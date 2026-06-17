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
  generation_reason?: string | null;
  display_order: number;
  status: string;
  attempt_count: number;
  max_attempts: number;
  last_feedback?: string | null;
  remediation_material?: string | null;
};

type ConceptPhase = {
  material?: string | null;
  prompt?: string | null;
  expected_answer?: string | null;
  light_conditions?: string | null;
  attempt_count: number;
  retry_count?: number;
  max_attempts: number;
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
  concept?: {
    material?: string | null;
    prompt?: string | null;
    attempt_count: number;
    max_attempts: number;
    phase1?: ConceptPhase;
    phase2?: ConceptPhase;
  } | null;
  last_feedback?: string | null;
  blocked_reason?: string | null;
};

const TERMINAL_STATUSES = new Set(["completed", "blocked", "failed", "failed_phase1", "failed_phase2"]);

export default function LearningPage() {
  const router = useRouter();
  const params = useParams<{ termSlug: string }>();
  const termSlug = params.termSlug;
  const [session, setSession] = useState<LearningSession | null>(null);
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
  const isTerminal = session ? TERMINAL_STATUSES.has(session.status) : false;

  useEffect(() => {
    async function boot() {
      try {
        const data = await api<LearningSession>("/api/learning-sessions", {
          method: "POST",
          body: JSON.stringify({ participant_id: requireParticipant(), term_slug: termSlug })
        });
        setSession(data);
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
      let data: { feedback: string; session: LearningSession };
      if (session.status === "prerequisite") {
        if (!currentPrerequisite) return;
        data = await api<{ feedback: string; session: LearningSession }>(
          `/api/learning-sessions/${session.learning_session_id}/prerequisites/${currentPrerequisite.prerequisite_id}/attempts`,
          {
            method: "POST",
            body: JSON.stringify({ learner_answer: response })
          }
        );
      } else if (session.status === "concept_phase1") {
        data = await api<{ feedback: string; session: LearningSession }>(`/api/learning-sessions/${session.learning_session_id}/concept-phase1-attempts`, {
          method: "POST",
          body: JSON.stringify({ learner_answer: response })
        });
      } else if (session.status === "concept_phase2") {
        data = await api<{ feedback: string; session: LearningSession }>(`/api/learning-sessions/${session.learning_session_id}/concept-phase2-attempts`, {
          method: "POST",
          body: JSON.stringify({ learner_answer: response })
        });
      } else {
        return;
      }
      setFeedback(data.feedback);
      setSession(data.session);
      setResponse("");
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
        {session ? (
          <LearningView
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

function LearningView({
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
        <StageList session={session} />
        <div className={session.status === "completed" ? "notice" : "danger"}>{terminalMessage(session)}</div>
        {session.last_feedback ? <div className="notice">{session.last_feedback}</div> : null}
        <button onClick={onNext}>次へ</button>
      </div>
    );
  }

  if (session.status === "concept_phase1") {
    return <Phase1Panel session={session} response={response} setResponse={setResponse} feedback={feedback} saving={saving} onSubmit={onSubmit} />;
  }

  if (session.status === "concept_phase2") {
    return <Phase2Panel session={session} response={response} setResponse={setResponse} feedback={feedback} saving={saving} onSubmit={onSubmit} />;
  }

  if (!currentPrerequisite) return <p>教材を準備しています...</p>;
  return (
    <PrerequisitePanel
      session={session}
      currentPrerequisite={currentPrerequisite}
      response={response}
      setResponse={setResponse}
      feedback={feedback}
      saving={saving}
      onSubmit={onSubmit}
    />
  );
}

function PrerequisitePanel({
  session,
  currentPrerequisite,
  response,
  setResponse,
  feedback,
  saving,
  onSubmit
}: {
  session: LearningSession;
  currentPrerequisite: Prerequisite;
  response: string;
  setResponse: (value: string) => void;
  feedback: string;
  saving: boolean;
  onSubmit: () => void;
}) {
  const label = session.group_condition === "proposed" ? "前提用語" : "確認小問";
  return (
    <div className="stack">
      <StageList session={session} />
      <div className="notice">
        <strong>
          {label} {currentPrerequisite.display_order}. {currentPrerequisite.term_label}
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

function Phase1Panel({
  session,
  response,
  setResponse,
  feedback,
  saving,
  onSubmit
}: {
  session: LearningSession;
  response: string;
  setResponse: (value: string) => void;
  feedback: string;
  saving: boolean;
  onSubmit: () => void;
}) {
  const phase = session.concept?.phase1;
  if (!phase) return <p>概念教材を準備しています...</p>;
  return (
    <div className="stack">
      <StageList session={session} />
      <div className="notice">
        <strong>概念フェーズ1</strong>
        <p>{phase.material}</p>
        <strong>{phase.prompt}</strong>
      </div>
      <p className="muted">
        試行 {phase.attempt_count} / {phase.max_attempts}
      </p>
      <label>
        教材を踏まえた説明
        <textarea value={response} onChange={(event) => setResponse(event.target.value)} />
      </label>
      <button onClick={onSubmit} disabled={saving}>
        回答を確認
      </button>
      {feedback ? <div className="notice">{feedback}</div> : null}
    </div>
  );
}

function Phase2Panel({
  session,
  response,
  setResponse,
  feedback,
  saving,
  onSubmit
}: {
  session: LearningSession;
  response: string;
  setResponse: (value: string) => void;
  feedback: string;
  saving: boolean;
  onSubmit: () => void;
}) {
  const phase = session.concept?.phase2;
  if (!phase) return <p>確認問題を準備しています...</p>;
  return (
    <div className="stack">
      <StageList session={session} />
      <div className="notice">
        <strong>概念フェーズ2</strong>
        <p className="muted">ここでは教材本文を表示しません。</p>
        {phase.light_conditions ? <p>{phase.light_conditions}</p> : null}
        <strong>{phase.prompt}</strong>
      </div>
      <p className="muted">
        試行 {phase.attempt_count} / {phase.max_attempts}
        {session.group_condition === "proposed" && typeof phase.retry_count === "number" ? ` ・再支援 ${phase.retry_count}回` : ""}
      </p>
      <label>
        教材を見ない説明
        <textarea value={response} onChange={(event) => setResponse(event.target.value)} />
      </label>
      <button onClick={onSubmit} disabled={saving}>
        回答を確認
      </button>
      {feedback ? <div className="notice">{feedback}</div> : null}
    </div>
  );
}

function StageList({ session }: { session: LearningSession }) {
  const prerequisiteTitle = session.group_condition === "proposed" ? "前提用語" : "確認小問";
  return (
    <div className="grid">
      <div className="notice">
        <strong>{prerequisiteTitle}</strong>
        <p className="muted">{session.prerequisites.filter((item) => item.status === "passed").length} / {session.prerequisites.length} 通過</p>
      </div>
      <div className="notice">
        <strong>概念フェーズ1</strong>
        <p className="muted">{phaseLabel(session, "concept_phase1")}</p>
      </div>
      <div className="notice">
        <strong>概念フェーズ2</strong>
        <p className="muted">{phaseLabel(session, "concept_phase2")}</p>
      </div>
    </div>
  );
}

function phaseLabel(session: LearningSession, phase: "concept_phase1" | "concept_phase2") {
  if (session.status === phase) return "実施中";
  if (session.status === "completed") return "完了";
  if (phase === "concept_phase1" && ["concept_phase2", "failed_phase2"].includes(session.status)) return "通過済み";
  if (phase === "concept_phase1" && session.status === "failed_phase1") return "未通過";
  if (phase === "concept_phase2" && session.status === "failed_phase2") return "未通過";
  return "待機中";
}

function terminalMessage(session: LearningSession) {
  if (session.status === "completed") return "この概念の学習を完了しました。";
  if (session.status === "failed_phase1") return session.blocked_reason || "概念フェーズ1をここで終了します。";
  if (session.status === "failed_phase2") return session.blocked_reason || "概念フェーズ2をここで終了します。";
  return session.blocked_reason || "この概念の学習をここで終了します。";
}
