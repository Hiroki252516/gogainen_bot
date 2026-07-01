"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { MarkdownText } from "@/components/MarkdownText";
import { api, requireParticipant } from "@/lib/api";

type Option = {
  option_id: string;
  label: string;
  body: string;
};

type PrerequisiteProgress = {
  key: string;
  label: string;
  display_order: number;
  status: string;
  completed_slot_count: number;
  forced_slot_count: number;
  review_count: number;
};

type LearningSession = {
  learning_session_id: string;
  group_condition: "control" | "proposed";
  status: string;
  stage: string;
  term_slug: string;
  term_label: string;
  term_description?: string | null;
  content_version: string;
  progress: {
    prerequisite_index?: number | null;
    prerequisite_total: number;
    required_question_index?: number | null;
    required_question_total: number;
    attempt_index: number;
    max_attempts: number;
    cycle_index: number;
  };
  current_prerequisite?: { key: string; label: string } | null;
  prerequisites: PrerequisiteProgress[];
  material?: { material_id: string; body: string } | null;
  question?: { question_id: string; body: string; options: Option[] } | null;
  last_feedback?: string | null;
  technical_block_reason?: string | null;
};

type AnswerResult = {
  attempt_id: string;
  is_correct: boolean;
  result_status: string;
  feedback: string;
  forced_answer_shown: boolean;
  correct_answer?: { body: string; summary: string } | null;
  session: LearningSession;
};

export default function LearningPage() {
  const router = useRouter();
  const params = useParams<{ termSlug: string }>();
  const termSlug = params.termSlug;
  const [session, setSession] = useState<LearningSession | null>(null);
  const [selected, setSelected] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const startedAt = useRef(Date.now());

  const nextHref = useMemo(() => {
    if (typeof window === "undefined") return "/retest";
    const targets = JSON.parse(localStorage.getItem("learning_targets") || "[]") as string[];
    const index = targets.indexOf(termSlug);
    return index >= 0 && index + 1 < targets.length ? `/learning/${targets[index + 1]}` : "/retest";
  }, [termSlug]);

  useEffect(() => {
    api<LearningSession>("/api/learning-sessions", {
      method: "POST",
      body: JSON.stringify({ participant_id: requireParticipant(), term_slug: termSlug })
    })
      .then((data) => {
        setSession(data);
        startedAt.current = Date.now();
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [termSlug]);

  async function submit() {
    if (!session?.question || !selected) {
      setError("選択肢を選んでください。");
      return;
    }
    setSaving(true);
    setError("");
    const endpoint =
      session.stage === "concept_phase1"
        ? "concept-phase1-attempts"
        : "prerequisite-attempts";
    try {
      const data = await api<AnswerResult>(`/api/learning-sessions/${session.learning_session_id}/${endpoint}`, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({
          question_id: session.question.question_id,
          selected_option_id: selected,
          response_time_sec: (Date.now() - startedAt.current) / 1000
        })
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  function continueFlow() {
    if (!result) return;
    if (result.session.status === "completed") {
      router.push(nextHref);
      return;
    }
    setSession(result.session);
    setResult(null);
    setSelected("");
    startedAt.current = Date.now();
  }

  async function retryMaterial() {
    if (!session) return;
    setSaving(true);
    setError("");
    try {
      const data = await api<LearningSession>(`/api/learning-sessions/${session.learning_session_id}/retry-material`, { method: "POST" });
      setSession(data);
      startedAt.current = Date.now();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell step="学習セッション">
      <section className="panel stack">
        <div className="topbar">
          <div>
            <h1>{session?.term_label || "学習セッション"}</h1>
            {session ? <p className="muted">{stageTitle(session)}</p> : null}
          </div>
          {session ? <span className="muted">{session.content_version}</span> : null}
        </div>
        {error ? <div className="danger">{error}</div> : null}
        {!session && !error ? <p>読み込み中...</p> : null}
        {!session && error ? <button onClick={() => window.location.reload()}>再読み込み</button> : null}
        {session?.status === "technical_blocked" ? (
          <div className="stack">
            <div className="danger">{session.technical_block_reason || "教材生成を再試行してください。"}</div>
            <button onClick={retryMaterial} disabled={saving}>教材生成を再試行</button>
          </div>
        ) : null}
        {session && session.status !== "technical_blocked" ? (
          <LearningPanel
            session={session}
            selected={selected}
            setSelected={setSelected}
            result={result}
            saving={saving}
            onSubmit={submit}
            onContinue={continueFlow}
            onNext={() => router.push(nextHref)}
          />
        ) : null}
      </section>
    </AppShell>
  );
}

function LearningPanel({
  session,
  selected,
  setSelected,
  result,
  saving,
  onSubmit,
  onContinue,
  onNext
}: {
  session: LearningSession;
  selected: string;
  setSelected: (value: string) => void;
  result: AnswerResult | null;
  saving: boolean;
  onSubmit: () => void;
  onContinue: () => void;
  onNext: () => void;
}) {
  if (session.status === "completed") {
    return (
      <div className="stack">
        <Progress session={session} />
        <div className="notice">この概念の学習を完了しました。</div>
        <button onClick={onNext}>次へ</button>
      </div>
    );
  }
  if (!session.question) return <p>問題を準備しています...</p>;
  return (
    <div className="stack">
      <Progress session={session} />
      {session.material ? (
        <div className="notice learning-material">
          <strong className="card-eyebrow">{session.current_prerequisite?.label || "概念教材"}</strong>
          <MarkdownText content={session.material.body} />
        </div>
      ) : null}
      <div className="notice">
        <strong>{session.question.body}</strong>
      </div>
      <div className="options">
        {session.question.options.map((option) => (
          <label className="option" key={option.option_id}>
            <input
              type="radio"
              name="learning-option"
              value={option.option_id}
              checked={selected === option.option_id}
              disabled={Boolean(result) || saving}
              onChange={() => setSelected(option.option_id)}
            />
            <span><strong>{option.label}.</strong> {option.body}</span>
          </label>
        ))}
      </div>
      {!result ? (
        <>
          {saving ? <SubmitProgress /> : null}
          <button onClick={onSubmit} disabled={saving || !selected}>
            {saving ? "分析中..." : "回答する"}
          </button>
        </>
      ) : (
        <div className="stack">
          <div className={result.is_correct ? "feedback-card feedback-card-ok" : "feedback-card feedback-card-error"}>
            <strong>{result.is_correct ? "正解です。" : "不正解です。"}</strong>
            <MarkdownText content={result.feedback} />
            {result.correct_answer ? (
              <div className="correct-answer-summary">
                <strong>正しい説明</strong>
                <p className="answer-body">{result.correct_answer.body}</p>
                <MarkdownText content={result.correct_answer.summary} />
              </div>
            ) : null}
          </div>
          <button onClick={onContinue}>
            {result.session.status === "completed" ? "次の概念へ" : "次の問題へ"}
          </button>
        </div>
      )}
    </div>
  );
}

function Progress({ session }: { session: LearningSession }) {
  const progress = session.progress;
  const requiredIndex = progress.required_question_index || 1;
  const requiredTotal = progress.required_question_total || 1;
  const isPrerequisite = session.stage === "prerequisite" || session.stage === "prerequisite_review";
  const isConceptPhase1 = session.stage === "concept_phase1";
  const isCompleted = session.status === "completed";
  const stepItems = [
    {
      key: "prerequisite",
      label: "前提用語",
      detail: `${Math.min(progress.prerequisite_index || 1, progress.prerequisite_total)} / ${progress.prerequisite_total}`,
      state: isPrerequisite ? "active" : isConceptPhase1 || isCompleted ? "done" : "upcoming"
    },
    {
      key: "concept_phase1",
      label: "概念フェーズ1",
      detail: isConceptPhase1 ? `小問 ${requiredIndex} / ${requiredTotal}` : "教材あり",
      state: isConceptPhase1 ? "active" : isCompleted ? "done" : "upcoming"
    },
    {
      key: "retest",
      label: "再テスト",
      detail: isCompleted ? "次へ" : "待機中",
      state: isCompleted ? "active" : "upcoming"
    }
  ];

  return (
    <div className="learning-progress">
      <ol className="stepper" aria-label="学習セッションの進行状況">
        {stepItems.map((item) => (
          <li className={`stepper-item ${item.state}`} key={item.key}>
            <span className="stepper-dot" aria-hidden="true" />
            <span className="stepper-text">
              <strong>{item.label}</strong>
              <span>{item.detail}</span>
            </span>
          </li>
        ))}
      </ol>
      <div className="current-summary" aria-label="現在の学習対象">
        <div>
          <span>対象概念</span>
          <strong>{session.term_label}</strong>
        </div>
        <div>
          <span>現在フェーズ</span>
          <strong>{stageTitle(session)}</strong>
        </div>
        <div>
          <span>{isPrerequisite ? "現在の前提用語" : "現在の確認"}</span>
          <strong>{session.current_prerequisite?.label || `概念小問 ${requiredIndex} / ${requiredTotal}`}</strong>
        </div>
        <div>
          <span>小問</span>
          <strong>{requiredIndex} / {requiredTotal}</strong>
        </div>
        <div>
          <span>試行</span>
          <strong>{progress.attempt_index} / {progress.max_attempts}</strong>
        </div>
        <div>
          <span>サイクル</span>
          <strong>{isConceptPhase1 ? progress.cycle_index : "-"}</strong>
        </div>
      </div>
    </div>
  );
}

function stageTitle(session: LearningSession) {
  if (session.stage === "prerequisite_review") return `前提用語レビュー: ${session.current_prerequisite?.label || ""}`;
  if (session.stage === "prerequisite") {
    return `前提用語 ${session.progress.prerequisite_index || 1} / ${session.progress.prerequisite_total}: ${session.current_prerequisite?.label || ""}`;
  }
  if (session.stage === "concept_phase1") {
    return `概念フェーズ1 教材あり・確認 ${session.progress.required_question_index || 1} / ${session.progress.required_question_total || 2}`;
  }
  return "完了";
}

function SubmitProgress() {
  const [elapsedSec, setElapsedSec] = useState(0);
  const steps = ["回答を記録しています", "選択内容を確認しています", "解説を生成しています", "次の教材を準備しています"];
  const activeIndex = Math.min(steps.length - 1, Math.floor(elapsedSec / 8));

  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="analysis-progress" role="status" aria-live="polite">
      <div className="analysis-heading">
        <span className="spinner" aria-hidden="true" />
        <div>
          <strong>分析中です</strong>
          <span>{elapsedSec}秒経過</span>
        </div>
      </div>
      <ol>
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
