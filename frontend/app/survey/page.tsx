"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { api, postIdempotent, requireParticipant } from "@/lib/api";

const SURVEY_STEPS = ["survey"] as const;
const GENERAL = [
  ["system_usability", "必要な操作をスムーズに行えた"],
  ["system_clarity", "画面を見て、次に何をすればよいか分かった"],
] as const;
const MATERIAL = [
  ["clarity", "教材で説明された内容を理解できた", "agreement"],
  ["readability", "教材は読みやすかった", "agreement"],
  ["japanese_clarity", "教材の日本語表現は分かりやすかった", "agreement"],
  ["difficulty_appropriateness", "教材の難易度はどの程度でしたか", "difficulty"],
  ["learning_usefulness", "教材は、用語や仕組みを正しく理解するために役立った", "agreement"],
  ["amount_appropriateness", "今回の教材の量はどの程度でしたか", "amount"],
] as const;
const AGREEMENT_OPTIONS = [
  ["1", "全くそう思わない"],
  ["2", "あまりそう思わない"],
  ["3", "どちらともいえない"],
  ["4", "ややそう思う"],
  ["5", "非常にそう思う"],
] as const;
const DIFFICULTY_OPTIONS = [
  ["1", "簡単すぎた"],
  ["2", "やや簡単"],
  ["3", "ちょうどよい"],
  ["4", "やや難しい"],
  ["5", "難しすぎた"],
] as const;
const AMOUNT_OPTIONS = [
  ["1", "少なすぎた"],
  ["2", "やや少ない"],
  ["3", "ちょうどよい"],
  ["4", "やや多い"],
  ["5", "多すぎた"],
] as const;
const NOT_APPLICABLE_OPTION = ["not_applicable", "評価できない"] as const;
type Context = { survey_version: "posttest-5point-v2"; has_viewed_material: boolean; material_ratings_required: boolean };

export default function SurveyPage() {
  const router = useRouter();
  const [context, setContext] = useState<Context | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function loadContext() {
    setError("");
    try { setContext(await api<Context>(`/api/participants/${requireParticipant()}/survey`)); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }
  useEffect(() => { void loadContext(); }, []);
  const update = (key: string, value: string) => setValues((previous) => ({ ...previous, [key]: value }));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!context || submitting) return;
    const requiredKeys = [
      ...GENERAL.map(([key]) => key),
      ...(context.material_ratings_required ? MATERIAL.map(([key]) => key) : []),
    ];
    if (requiredKeys.some((key) => !values[key])) {
      setError("未選択の項目があります。各項目を選択してください。");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const participantId = requireParticipant();
      const ratingValue = (value: string) => value === "not_applicable" ? value : Number(value);
      await postIdempotent(`/api/participants/${participantId}/survey`, {
        survey_version: context.survey_version,
        general_ratings: Object.fromEntries(GENERAL.map(([key]) => [key, ratingValue(values[key])])),
        material_ratings: context.material_ratings_required ? Object.fromEntries(MATERIAL.map(([key]) => [key, ratingValue(values[key])])) : null,
        free_comment: comment.trim(),
      }, `survey:${participantId}`);
      router.replace("/finish");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); setSubmitting(false); }
  }

  return <ParticipantFlowGuard allowedSteps={SURVEY_STEPS}>
    <AppShell step="アンケート">
      <form className="panel stack" onSubmit={submit}>
        <h1>実験後アンケート</h1>
        <p>自由記述以外の表示される項目はすべて必須です。各質問について回答してください。</p>
        {!context ? <p>回答項目を確認しています。</p> : <>
          <h2>システムについて</h2>
          {GENERAL.map(([key, label]) => <RatingButtons key={key} label={label} options={AGREEMENT_OPTIONS} value={values[key] || ""} disabled={submitting} onChange={(value) => update(key, value)} />)}
          <h2>教材について</h2>
          {context.material_ratings_required
            ? MATERIAL.map(([key, label, scale]) => <RatingButtons key={key} label={label} options={scale === "difficulty" ? DIFFICULTY_OPTIONS : scale === "amount" ? AMOUNT_OPTIONS : AGREEMENT_OPTIONS} value={values[key] || ""} disabled={submitting} onChange={(value) => update(key, value)} />)
            : <p>教材の表示記録がないため、教材評価6項目は対象外です。</p>}
          <label>自由記述（任意）
            <textarea value={comment} disabled={submitting} onChange={(event) => setComment(event.target.value)} rows={5} />
            <span className="muted">操作で迷った点、教材で分かりにくかった点、改善してほしい点などがあれば記入してください。空欄のまま送信できます。</span>
          </label>
        </>}
        {error ? <div className="danger" role="alert">{error}</div> : null}
        {!context && error ? <button type="button" onClick={() => void loadContext()}>再読み込み</button> : null}
        <button type="submit" disabled={submitting || !context}>{submitting ? "保存しています..." : "回答を保存して終了"}</button>
      </form>
    </AppShell>
  </ParticipantFlowGuard>;
}

function ChoiceButtons({ label, value, disabled, onChange }: { label: string; value: string; disabled: boolean; onChange: (value: string) => void }) {
  return <div className="survey-choice-question">
    <div className="survey-rating-label"><span className="survey-question-label">{label}</span><span className="required-indicator">必須</span></div>
    <div className="survey-choice-options" role="group" aria-label={label}>
      {[["yes", "知っていた"], ["no", "知らない"]].map(([optionValue, optionLabel]) => <button
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

function RatingButtons({ label, options, value, disabled, onChange }: { label: string; options: readonly (readonly [string, string])[]; value: string; disabled: boolean; onChange: (value: string) => void }) {
  const choices = [...options, NOT_APPLICABLE_OPTION];
  return <div className="survey-rating">
    <div className="survey-rating-label"><span>{label}</span><span className="required-indicator">必須</span></div>
    <div className="survey-rating-options" role="group" aria-label={label}>
      {choices.map(([rating, optionLabel]) => <button
        key={rating}
        type="button"
        className={`survey-rating-button${value === rating ? " selected" : ""}`}
        data-rating-value={rating}
        aria-label={optionLabel}
        aria-pressed={value === rating}
        disabled={disabled}
        onClick={() => onChange(rating)}
      ><span className="survey-rating-value">{rating === "not_applicable" ? "評価不能" : rating}</span><span>{optionLabel}</span></button>)}
    </div>
  </div>;
}
