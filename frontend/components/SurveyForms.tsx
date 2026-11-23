"use client";

import { useState, type CSSProperties, type FormEvent, type ReactNode } from "react";

export type SurveyTermItem = { key: string; label: string };

export const FOUR_TOPIC_PRESURVEY_TERM_ITEMS: readonly SurveyTermItem[] = [
  { key: "transformer", label: "Transformer" },
  { key: "pretraining", label: "事前学習" },
  { key: "instruction_tuning", label: "インストラクションチューニング" },
  { key: "human_feedback_post_training", label: "事後学習" },
  { key: "multi_agent", label: "マルチエージェント" },
  { key: "memory_process", label: "記憶プロセス" },
];

const EXPOSURE_OPTIONS = [
  ["experienced", "ある"],
  ["not_experienced", "ない"],
  ["cannot_recall", "判断できない"],
] as const;
const UNDERSTANDING_OPTIONS = [
  ["not_at_all", "全く理解していない"],
  ["hardly", "あまり理解していない"],
  ["neither", "どちらとも言えない"],
  ["moderately", "ある程度理解している"],
  ["well", "よく理解している"],
] as const;
const WEEKLY_AI_USAGE_OPTIONS = [
  ["0", "0日"],
  ["1", "1日"],
  ["2", "2日"],
  ["3", "3日"],
  ["4", "4日"],
  ["5", "5日"],
  ["6", "6日"],
  ["7", "7日"],
] as const;
const PROFICIENCY_OPTIONS = [
  ["1", "全くできない"],
  ["2", "あまりできない"],
  ["3", "どちらでもない"],
  ["4", "ある程度できる"],
  ["5", "よくできる"],
] as const;
const PROFICIENCY_ITEMS = [
  ["goal_aligned_output", "AIに目的を伝え、目的に合った回答を得ることができますか。", "例：週末の外食先を探すとき、希望を伝えて候補を提案してもらう。"],
  ["revise_instructions", "AIの回答が期待と異なるとき、指示や条件を修正できますか。", "例：候補が希望と違うとき、予算や移動時間などの条件を伝え直す。"],
  ["verify_with_sources", "AIの回答が正しいか、公式サイトや別の資料で確かめられますか。", "例：AIが答えた営業時間を、お店の公式サイトで確認する。"],
] as const;

const GENERAL = [
  ["system_usability", "必要な操作をスムーズに行えた"],
] as const;
const MATERIAL = [
  ["clarity", "教材で説明された内容を理解できた", "agreement"],
  ["readability", "教材は読みやすかった", "agreement"],
  ["japanese_clarity", "教材の日本語表現は分かりやすかった", "agreement"],
  ["learning_usefulness", "教材は、用語や仕組みを正しく理解するために役立った", "agreement"],
  ["difficulty_appropriateness", "教材の難易度はどの程度でしたか", "difficulty"],
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

type ExposureValue = (typeof EXPOSURE_OPTIONS)[number][0];
type UnderstandingValue = (typeof UNDERSTANDING_OPTIONS)[number][0];
type RatingValue = number;

export type PresurveySubmission = {
  survey_version: string;
  prior_term_exposure: Record<string, ExposureValue>;
  prior_term_understanding: Record<string, UnderstandingValue | null>;
  general_ratings: {
    ai_usage_days_per_week: number;
    ai_proficiency: Record<string, number>;
  };
};

export type PosttestSubmission = {
  survey_version: "posttest-5point-v5";
  general_ratings: Record<string, number>;
  material_ratings: Record<string, number> | null;
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
      "ai_usage_days_per_week",
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
          ai_usage_days_per_week: Number(values.ai_usage_days_per_week),
          ai_proficiency: Object.fromEntries(PROFICIENCY_ITEMS.map(([key]) => [key, Number(values[`proficiency:${key}`])])) as Record<string, number>,
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
      const experienceQuestion = `実験を始める前に、${label}という用語を見たり聞いたりしたことがありますか。`;
      const understandingQuestion = `${label}の基本的な仕組みを、どの程度理解していますか。`;
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
          <RatingButtons
            label={understandingQuestion}
            description={<><strong>回答の目安</strong><br />基本的な仕組みがあまり分からない場合は「2 あまり理解していない」が目安です。基本的な仕組みは分かるものの、分からない部分もある場合は「4 ある程度理解している」が目安です。</>}
            value={values[`understanding:${key}`] || ""}
            options={UNDERSTANDING_OPTIONS}
            disabled={submitting}
            onChange={(value) => update(`understanding:${key}`, value)}
          />
        </div> : null}
      </section>;
    })}
    <h2 className="survey-section-heading">AIの利用経験</h2>
    <ChoiceButtons
      label="普段の生活では、1週間あたり何日程度AIを利用しますか。"
      value={values.ai_usage_days_per_week || ""}
      options={WEEKLY_AI_USAGE_OPTIONS}
      disabled={submitting}
      onChange={(value) => update("ai_usage_days_per_week", value)}
    />
    <h2 className="survey-section-heading">AIの使い方についての自己評価</h2>
    <p className="muted">次の各項目について、最も当てはまるものを選んでください。</p>
    {PROFICIENCY_ITEMS.map(([key, label, example]) => <RatingButtons
      key={key}
      label={label}
      description={example}
      value={values[`proficiency:${key}`] || ""}
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
      const ratingValue = (value: string): RatingValue => Number(value);
      const payload: PosttestSubmission = {
        survey_version: "posttest-5point-v5",
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
    <h2 className="survey-section-heading">教材について</h2>
    {materialRatingsRequired
      ? <>
        {MATERIAL.slice(0, 4).map(([key, label]) => <RatingButtons key={key} label={label} options={AGREEMENT_OPTIONS} value={values[key] || ""} disabled={submitting} onChange={(value) => update(key, value)} />)}
        <div className="survey-rating-spacer survey-rating-scale-change">
          {MATERIAL.slice(4).map(([key, label, scale]) => <RatingButtons key={key} label={label} options={scale === "difficulty" ? DIFFICULTY_OPTIONS : AMOUNT_OPTIONS} value={values[key] || ""} disabled={submitting} onChange={(value) => update(key, value)} />)}
        </div>
      </>
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
  description,
}: {
  label: string;
  value: string;
  options: readonly (readonly [string, string])[];
  disabled: boolean;
  onChange: (value: string) => void;
  description?: string;
}) {
  return <div className="survey-choice-question">
    <div className="survey-rating-label"><span className="survey-question-label">{label}</span><span className="required-indicator">必須</span></div>
    {description ? <p className="muted survey-choice-description">{description}</p> : null}
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

function RatingButtons({ label, options, value, disabled, onChange, description }: {
  label: string;
  options: readonly (readonly [string, string])[];
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  description?: ReactNode;
}) {
  return <div className="survey-rating">
    <div className="survey-rating-label"><span>{label}</span><span className="required-indicator">必須</span></div>
    {description ? <p className="muted survey-choice-description">{description}</p> : null}
    <div className="survey-rating-options" role="group" aria-label={label}>
      {options.map(([rating, optionLabel], index) => <button
        key={rating}
        type="button"
        className={`survey-rating-button${value === rating ? " selected" : ""}`}
        data-rating-value={rating}
        aria-label={optionLabel}
        aria-pressed={value === rating}
        disabled={disabled}
        onClick={() => onChange(rating)}
      ><span className="survey-rating-value">{index + 1}</span><span>{optionLabel}</span></button>)}
    </div>
  </div>;
}
