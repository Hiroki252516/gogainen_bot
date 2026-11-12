"use client";

import { useState, type CSSProperties, type FormEvent } from "react";

export type SurveyTermItem = { key: string; label: string };

export const FOUR_TOPIC_PRESURVEY_TERM_ITEMS: readonly SurveyTermItem[] = [
  { key: "transformer", label: "Transformer" },
  { key: "pretraining", label: "事前学習" },
  { key: "fine_tuning", label: "ファインチューニング" },
  { key: "human_feedback_post_training", label: "人の評価・好みを用いる事後学習" },
  { key: "multi_agent", label: "マルチエージェント" },
  { key: "memory_process", label: "記憶プロセス" },
];

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
  ["amount_appropriateness", "教材の量はどの程度でしたか", "amount"],
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

type ExposureValue = (typeof EXPOSURE_OPTIONS)[number][0];
type UnderstandingValue = (typeof UNDERSTANDING_OPTIONS)[number][0];
type RatingValue = number | "not_applicable";

export type PresurveySubmission = {
  survey_version: string;
  prior_term_exposure: Record<string, ExposureValue>;
  prior_term_understanding: Record<string, UnderstandingValue | null>;
  general_ratings: {
    ai_usage_frequency_30d: (typeof FREQUENCY_OPTIONS)[number][0];
    ai_proficiency: Record<string, RatingValue>;
  };
};

export type PosttestSubmission = {
  survey_version: "posttest-5point-v3";
  general_ratings: Record<string, RatingValue>;
  material_ratings: Record<string, RatingValue> | null;
  free_comment: string;
};

export function PresurveyQuestionnaire({
  surveyVersion,
  termItems,
  preview = false,
  onSubmit,
}: {
  surveyVersion: string;
  termItems: readonly SurveyTermItem[];
  preview?: boolean;
  onSubmit: (payload: PresurveySubmission) => Promise<void>;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [completed, setCompleted] = useState(false);
  const [exposureAnnouncement, setExposureAnnouncement] = useState("");
  const update = (key: string, value: string) => setValues((previous) => ({ ...previous, [key]: value }));
  const updateExposure = (termKey: string, value: string) => {
    const wasExperienced = values[`exposure:${termKey}`] === "experienced";
    const isExperienced = value === "experienced";
    setValues((previous) => ({
      ...previous,
      [`exposure:${termKey}`]: value,
      [`understanding:${termKey}`]: isExperienced ? previous[`understanding:${termKey}`] || "" : "",
    }));
    if (wasExperienced !== isExperienced) {
      const label = termItems.find((item) => item.key === termKey)?.label || termKey;
      setExposureAnnouncement(`${label}の理解度に関する追加質問を${isExperienced ? "表示" : "非表示"}にしました。`);
    }
  };

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const requiredKeys = [
      ...termItems.flatMap(({ key }) => [
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
      const payload: PresurveySubmission = {
        survey_version: surveyVersion,
        prior_term_exposure: Object.fromEntries(termItems.map(({ key }) => [key, values[`exposure:${key}`]])) as Record<string, ExposureValue>,
        prior_term_understanding: Object.fromEntries(termItems.map(({ key }) => [
          key,
          values[`exposure:${key}`] === "experienced" ? values[`understanding:${key}`] : null,
        ])) as Record<string, UnderstandingValue | null>,
        general_ratings: {
          ai_usage_frequency_30d: values.ai_usage_frequency_30d as PresurveySubmission["general_ratings"]["ai_usage_frequency_30d"],
          ai_proficiency: Object.fromEntries(PROFICIENCY_ITEMS.map(([key]) => {
            const value = values[`proficiency:${key}`];
            return [key, value === "not_applicable" ? value : Number(value)];
          })) as Record<string, RatingValue>,
        },
      };
      if (preview) {
        setCompleted(true);
        return;
      }
      await onSubmit(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (completed) return <section className="panel stack">
    <h1>事前アンケートの入力確認</h1>
    <p role="status">入力を確認しました。デバッグプレビューのため、回答は保存されていません。</p>
    <button type="button" onClick={() => { setValues({}); setError(""); setCompleted(false); }}>もう一度入力する</button>
  </section>;

  return <form className="panel stack presurvey-form" onSubmit={submit}>
    <h1>実験前アンケート</h1>
    <p>今回の実験を始める前の状態について回答してください。表示される項目はすべて必須です。</p>
    <p className="visually-hidden presurvey-announcement" role="status" aria-live="polite" aria-atomic="true">{exposureAnnouncement}</p>
    <h2>用語について</h2>
    <p className="muted">まず見聞きした経験を回答してください。「ある」の場合に、理解度の項目が表示されます。</p>
    {termItems.map(({ key, label }) => {
      const exposure = values[`exposure:${key}`] || "";
      const experienceQuestion = `${label}という用語を、実験の説明を受ける前に見たり聞いたりしたことがありますか。`;
      const understandingQuestion = `${label}の基本的な意味や働きをどの程度理解していますか。`;
      return <section className="stack presurvey-term-item" key={key} aria-label={label}>
        <ChoiceButtons
          label={experienceQuestion}
          value={exposure}
          options={EXPOSURE_OPTIONS}
          disabled={submitting}
          onChange={(value) => updateExposure(key, value)}
        />
        {exposure === "experienced" ? <div className="presurvey-followup">
          <h3 className="presurvey-followup-heading">追加質問：理解度</h3>
          <ChoiceButtons
            label={understandingQuestion}
            value={values[`understanding:${key}`] || ""}
            options={UNDERSTANDING_OPTIONS}
            disabled={submitting}
            onChange={(value) => update(`understanding:${key}`, value)}
          />
        </div> : null}
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
    {error ? <div className="danger" role="alert">{error}</div> : null}
    <button type="submit" disabled={submitting}>{submitting ? "確認しています..." : preview ? "入力を確認する（保存なし）" : "回答を保存して事前テストへ"}</button>
  </form>;
}

export function PosttestQuestionnaire({
  materialRatingsRequired,
  preview = false,
  onSubmit,
}: {
  materialRatingsRequired: boolean;
  preview?: boolean;
  onSubmit: (payload: PosttestSubmission) => Promise<void>;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [completed, setCompleted] = useState(false);
  const update = (key: string, value: string) => setValues((previous) => ({ ...previous, [key]: value }));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const requiredKeys = [
      ...GENERAL.map(([key]) => key),
      ...(materialRatingsRequired ? MATERIAL.map(([key]) => key) : []),
    ];
    if (requiredKeys.some((key) => !values[key])) {
      setError("未選択の項目があります。各項目を選択してください。");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const ratingValue = (value: string): RatingValue => value === "not_applicable" ? value : Number(value);
      const payload: PosttestSubmission = {
        survey_version: "posttest-5point-v3",
        general_ratings: Object.fromEntries(GENERAL.map(([key]) => [key, ratingValue(values[key])])),
        material_ratings: materialRatingsRequired
          ? Object.fromEntries(MATERIAL.map(([key]) => [key, ratingValue(values[key])]))
          : null,
        free_comment: comment.trim(),
      } as PosttestSubmission;
      if (preview) {
        setCompleted(true);
        return;
      }
      await onSubmit(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (completed) return <section className="panel stack">
    <h1>事後アンケートの入力確認</h1>
    <p role="status">入力を確認しました。デバッグプレビューのため、回答は保存されていません。</p>
    <button type="button" onClick={() => { setValues({}); setComment(""); setError(""); setCompleted(false); }}>もう一度入力する</button>
  </section>;

  return <form className="panel stack" onSubmit={submit}>
    <h1>実験後アンケート</h1>
    <p>自由記述以外の表示される項目はすべて必須です。各質問について回答してください。</p>
    <h2>システムについて</h2>
    {GENERAL.map(([key, label]) => <RatingButtons key={key} label={label} options={AGREEMENT_OPTIONS} value={values[key] || ""} disabled={submitting} onChange={(value) => update(key, value)} />)}
    <h2>教材について</h2>
    {materialRatingsRequired
      ? MATERIAL.map(([key, label, scale]) => <RatingButtons key={key} label={label} options={scale === "difficulty" ? DIFFICULTY_OPTIONS : scale === "amount" ? AMOUNT_OPTIONS : AGREEMENT_OPTIONS} value={values[key] || ""} disabled={submitting} onChange={(value) => update(key, value)} />)
      : <p>教材の表示記録がないため、教材評価6項目は対象外です。</p>}
    <label>自由記述（任意）
      <textarea value={comment} disabled={submitting} onChange={(event) => setComment(event.target.value)} rows={5} />
      <span className="muted">操作で迷った点、教材で分かりにくかった点、改善してほしい点などがあれば記入してください。空欄のまま送信できます。</span>
    </label>
    {error ? <div className="danger" role="alert">{error}</div> : null}
    <button type="submit" disabled={submitting}>{submitting ? "確認しています..." : preview ? "入力を確認する（保存なし）" : "回答を保存して終了"}</button>
  </form>;
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
    <div
      className="survey-choice-options"
      role="group"
      aria-label={label}
      style={{ "--survey-choice-option-count": options.length } as CSSProperties}
    >
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

function RatingButtons({ label, options, value, disabled, onChange }: {
  label: string;
  options: readonly (readonly [string, string])[];
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
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
