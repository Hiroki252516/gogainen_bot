"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { api, postIdempotent, requireParticipant } from "@/lib/api";

const PRESURVEY_STEPS = ["presurvey"] as const;
const PRIOR_TERM_KNOWLEDGE = [
  ["pretraining", "事前学習"],
  ["fine_tuning", "ファインチューニング"],
  ["rag", "RAG"],
  ["prompt_engineering", "プロンプトエンジニアリング"],
  ["multi_agent", "マルチエージェント"],
  ["memory_process", "記憶プロセス（AIが以前の会話で伝えた利用者の希望を記憶し、次回以降の回答に利用する仕組み）"],
] as const;
const BASELINE_RATINGS = [
  ["ai_usage_frequency", "普段のAI利用頻度", "1：使用しない ／ 10：非常に頻繁に使用する"],
  ["self_rated_ai_proficiency", "AIを使いこなせているかの自己評価", "1：全く使いこなせていない ／ 10：非常によく使いこなせている"],
] as const;
const RATING_VALUES = Array.from({ length: 10 }, (_, index) => String(index + 1));
type Context = { survey_version: string };

export default function PresurveyPage() {
  const router = useRouter();
  const [context, setContext] = useState<Context | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function loadContext() {
    setError("");
    try { setContext(await api<Context>(`/api/participants/${requireParticipant()}/presurvey`)); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  useEffect(() => { void loadContext(); }, []);
  const update = (key: string, value: string) => setValues((previous) => ({ ...previous, [key]: value }));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!context || submitting) return;
    const requiredKeys = [...PRIOR_TERM_KNOWLEDGE.map(([key]) => key), ...BASELINE_RATINGS.map(([key]) => key)];
    if (requiredKeys.some((key) => !values[key])) {
      setError("未選択の項目があります。各項目を選択してください。");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const participantId = requireParticipant();
      await postIdempotent(`/api/participants/${participantId}/presurvey`, {
        survey_version: context.survey_version,
        prior_term_knowledge: Object.fromEntries(PRIOR_TERM_KNOWLEDGE.map(([key]) => [key, values[key]])),
        general_ratings: Object.fromEntries(BASELINE_RATINGS.map(([key]) => [key, Number(values[key])])),
      }, `presurvey:${participantId}`);
      router.replace("/pretest");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); setSubmitting(false); }
  }

  return <ParticipantFlowGuard allowedSteps={PRESURVEY_STEPS}>
    <AppShell step="事前アンケート">
      <form className="panel stack" onSubmit={submit}>
        <h1>実験前アンケート</h1>
        <p>今回の実験を始める前の状態について回答してください。表示される項目はすべて必須です。</p>
        {!context ? <p>回答項目を確認しています。</p> : <>
          <h2>実験前に用語の意味を知っていたか</h2>
          {PRIOR_TERM_KNOWLEDGE.map(([key, label]) => <ChoiceButtons key={key} label={label} value={values[key] || ""} disabled={submitting} onChange={(value) => update(key, value)} />)}
          <h2>普段のAI利用について</h2>
          {BASELINE_RATINGS.map(([key, label, anchors]) => <RatingButtons key={key} label={label} anchors={anchors} value={values[key] || ""} disabled={submitting} onChange={(value) => update(key, value)} />)}
        </>}
        {error ? <div className="danger" role="alert">{error}</div> : null}
        {!context && error ? <button type="button" onClick={() => void loadContext()}>再読み込み</button> : null}
        <button type="submit" disabled={submitting || !context}>{submitting ? "保存しています..." : "回答を保存して事前テストへ"}</button>
      </form>
    </AppShell>
  </ParticipantFlowGuard>;
}

function ChoiceButtons({ label, value, disabled, onChange }: { label: string; value: string; disabled: boolean; onChange: (value: string) => void }) {
  return <div className="survey-choice-question">
    <div className="survey-rating-label"><span className="survey-question-label">{label}</span><span className="required-indicator">必須</span></div>
    <div className="survey-choice-options" role="group" aria-label={label}>
      {[
        ["unknown", "知らない"],
        ["heard_of", "聞いたことがある"],
        ["knows_meaning", "意味を知っている"],
        ["can_explain", "説明できる"],
      ].map(([optionValue, optionLabel]) => <button
        key={optionValue}
        type="button"
        className={`survey-choice-button${value === optionValue ? " selected" : ""}`}
        aria-pressed={value === optionValue}
        disabled={disabled}
        onClick={() => onChange(optionValue)}
      >{optionLabel}</button>)}
    </div>
  </div>;
}

function RatingButtons({ label, anchors, value, disabled, onChange }: { label: string; anchors: string; value: string; disabled: boolean; onChange: (value: string) => void }) {
  return <div className="survey-rating">
    <div className="survey-rating-label"><span>{label}</span><span className="required-indicator">必須</span></div>
    <span className="muted">{anchors}</span>
    <div className="survey-rating-options" role="group" aria-label={label}>
      {RATING_VALUES.map((rating) => <button
        key={rating}
        type="button"
        className={`survey-rating-button${value === rating ? " selected" : ""}`}
        aria-pressed={value === rating}
        disabled={disabled}
        onClick={() => onChange(rating)}
      >{rating}</button>)}
    </div>
  </div>;
}
