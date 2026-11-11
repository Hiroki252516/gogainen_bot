"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { api, postIdempotent, requireParticipant } from "@/lib/api";

const PRESURVEY_STEPS = ["presurvey"] as const;
const EXPOSURE_OPTIONS = [
  ["experienced", "ある"],
  ["not_experienced", "ない"],
  ["cannot_recall", "覚えていない"],
] as const;
const UNDERSTANDING_OPTIONS = [
  ["not_at_all", "全く理解していない"],
  ["slightly", "少し理解している"],
  ["moderately", "ある程度理解している"],
  ["well", "よく理解している"],
] as const;
const FREQUENCY_OPTIONS = [
  ["0_days", "0日"],
  ["1_3_days", "1〜3日"],
  ["4_8_days", "4〜8日"],
  ["9_20_days", "9〜20日"],
  ["21_30_days", "21〜30日"],
] as const;
const PROFICIENCY_OPTIONS = [
  ["1", "1"],
  ["2", "2"],
  ["3", "3"],
  ["4", "4"],
  ["5", "5"],
  ["not_applicable", "評価できない"],
] as const;
const PROFICIENCY_ITEMS = [
  ["goal_aligned_output", "目的を伝えて、目的に合った回答を得る"],
  ["revise_instructions", "期待と違う回答のとき、指示や条件を修正する"],
  ["verify_with_sources", "AIの回答を他の資料・情報源で確認する"],
] as const;
const PROFICIENCY_ANCHORS = "1：全くできない ／ 2：あまりできない ／ 3：少しできる ／ 4：ある程度できる ／ 5：よくできる";

type TermItem = { key: string; label: string };
type Context = { survey_version: string; term_items: TermItem[] };

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
  const updateExposure = (termKey: string, value: string) => setValues((previous) => ({
    ...previous,
    [`exposure:${termKey}`]: value,
    [`understanding:${termKey}`]: value === "experienced" ? previous[`understanding:${termKey}`] || "" : "",
  }));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!context || submitting) return;
    const requiredKeys = [
      ...context.term_items.flatMap(({ key }) => [
        `exposure:${key}`,
        ...(values[`exposure:${key}`] === "experienced" ? [`understanding:${key}`] : []),
      ]),
      "ai_usage_frequency_30d",
      ...PROFICIENCY_ITEMS.map(([key]) => `proficiency:${key}`),
    ];
    if (requiredKeys.some((key) => !values[key])) {
      setError("未選択の項目があります。必須の各項目を選択してください。");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const participantId = requireParticipant();
      const priorTermExposure = Object.fromEntries(context.term_items.map(({ key }) => [key, values[`exposure:${key}`]]));
      const priorTermUnderstanding = Object.fromEntries(context.term_items.map(({ key }) => [
        key,
        values[`exposure:${key}`] === "experienced" ? values[`understanding:${key}`] : null,
      ]));
      const aiProficiency = Object.fromEntries(PROFICIENCY_ITEMS.map(([key]) => {
        const value = values[`proficiency:${key}`];
        return [key, value === "not_applicable" ? value : Number(value)];
      }));

      await postIdempotent(`/api/participants/${participantId}/presurvey`, {
        survey_version: context.survey_version,
        prior_term_exposure: priorTermExposure,
        prior_term_understanding: priorTermUnderstanding,
        general_ratings: {
          ai_usage_frequency_30d: values.ai_usage_frequency_30d,
          ai_proficiency: aiProficiency,
        },
      }, `presurvey:${participantId}`);
      router.replace("/pretest");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); setSubmitting(false); }
  }

  return <ParticipantFlowGuard allowedSteps={PRESURVEY_STEPS}>
    <AppShell step="事前アンケート">
      <form className="panel stack presurvey-form" onSubmit={submit}>
        <h1>実験前アンケート</h1>
        <p>今回の実験を始める前の状態について回答してください。表示される項目はすべて必須です。</p>
        {!context ? <p>回答項目を確認しています。</p> : <>
          <h2>用語について</h2>
          <p className="muted">まず見聞きした経験を回答してください。「ある」の場合に、理解度の項目が表示されます。</p>
          {context.term_items.map(({ key, label }) => {
            const exposure = values[`exposure:${key}`] || "";
            const experienceQuestion = `${label}という用語を、実験の説明を受ける前に見たり聞いたりしたことがありますか。`;
            const understandingQuestion = `${label}の基本的な意味や働きをどの程度理解していますか。`;
            return <section className="stack" key={key} aria-label={label}>
              <ChoiceButtons
                label={experienceQuestion}
                value={exposure}
                options={EXPOSURE_OPTIONS}
                disabled={submitting}
                onChange={(value) => updateExposure(key, value)}
              />
              {exposure === "experienced" ? <ChoiceButtons
                label={understandingQuestion}
                value={values[`understanding:${key}`] || ""}
                options={UNDERSTANDING_OPTIONS}
                disabled={submitting}
                onChange={(value) => update(`understanding:${key}`, value)}
              /> : null}
            </section>;
          })}
          <h2>普段のAI利用について</h2>
          <ChoiceButtons
            label="直近30日間のうち、AIを利用した日数"
            value={values.ai_usage_frequency_30d || ""}
            options={FREQUENCY_OPTIONS}
            disabled={submitting}
            onChange={(value) => update("ai_usage_frequency_30d", value)}
          />
          <p className="muted">次の各行動をどの程度できるか回答してください。評価する機会がなかった場合は「評価できない」を選んでください。</p>
          {PROFICIENCY_ITEMS.map(([key, label]) => <ChoiceButtons
            key={key}
            label={label}
            value={values[`proficiency:${key}`] || ""}
            anchors={PROFICIENCY_ANCHORS}
            options={PROFICIENCY_OPTIONS}
            disabled={submitting}
            onChange={(value) => update(`proficiency:${key}`, value)}
          />)}
        </>}
        {error ? <div className="danger" role="alert">{error}</div> : null}
        {!context && error ? <button type="button" onClick={() => void loadContext()}>再読み込み</button> : null}
        <button type="submit" disabled={submitting || !context}>{submitting ? "保存しています..." : "回答を保存して事前テストへ"}</button>
      </form>
    </AppShell>
  </ParticipantFlowGuard>;
}

function ChoiceButtons({
  label,
  value,
  options,
  disabled,
  onChange,
  anchors,
}: {
  label: string;
  value: string;
  options: readonly (readonly [string, string])[];
  disabled: boolean;
  onChange: (value: string) => void;
  anchors?: string;
}) {
  return <div className="survey-choice-question">
    <div className="survey-rating-label"><span className="survey-question-label">{label}</span><span className="required-indicator">必須</span></div>
    {anchors ? <span className="muted">{anchors}</span> : null}
    <div className="survey-choice-options" role="group" aria-label={label}>
      {options.map(([optionValue, optionLabel]) => <button
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
