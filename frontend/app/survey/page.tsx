"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { postIdempotent, requireParticipant } from "@/lib/api";

type SurveyValues = {
  ai_experience_level: string;
  programming_experience_level: string;
  llm_usage_level: string;
  self_rated_ai_knowledge: string;
  usability_rating: string;
  helpfulness_rating: string;
  perceived_hint_amount: string;
  free_comment: string;
};

const INITIAL_VALUES: SurveyValues = {
  ai_experience_level: "",
  programming_experience_level: "",
  llm_usage_level: "",
  self_rated_ai_knowledge: "",
  usability_rating: "",
  helpfulness_rating: "",
  perceived_hint_amount: "",
  free_comment: "",
};

const RATING_OPTIONS = [1, 2, 3, 4, 5];
const SURVEY_STEPS = ["survey"] as const;

export default function SurveyPage() {
  const router = useRouter();
  const [values, setValues] = useState<SurveyValues>(INITIAL_VALUES);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function update(field: keyof SurveyValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const participantId = requireParticipant();
      const surveyBody = {
        ai_experience_level: numberOrNull(values.ai_experience_level),
        programming_experience_level: numberOrNull(values.programming_experience_level),
        llm_usage_level: numberOrNull(values.llm_usage_level),
        self_rated_ai_knowledge: numberOrNull(values.self_rated_ai_knowledge),
        usability_rating: Number(values.usability_rating),
        helpfulness_rating: Number(values.helpfulness_rating),
        perceived_hint_amount: Number(values.perceived_hint_amount),
        free_comment: values.free_comment.trim() || null,
      };
      await postIdempotent(
        `/api/participants/${participantId}/survey`,
        surveyBody,
        `survey:${participantId}`,
      );
      router.replace("/finish");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <ParticipantFlowGuard allowedSteps={SURVEY_STEPS}>
      <AppShell step="アンケート">
        <form className="panel stack" onSubmit={submit}>
        <h1>実験後アンケート（仮）</h1>
        <p className="muted">テストと学習セッションについて、感じたことを回答してください。</p>

        <div className="grid">
          <RatingSelect required label="AI利用経験" value={values.ai_experience_level} onChange={(value) => update("ai_experience_level", value)} />
          <RatingSelect required label="プログラミング経験" value={values.programming_experience_level} onChange={(value) => update("programming_experience_level", value)} />
          <RatingSelect required label="LLM利用頻度" value={values.llm_usage_level} onChange={(value) => update("llm_usage_level", value)} />
          <RatingSelect required label="AIに関する自己評価" value={values.self_rated_ai_knowledge} onChange={(value) => update("self_rated_ai_knowledge", value)} />
        </div>

        <RatingSelect required label="操作のしやすさ" value={values.usability_rating} onChange={(value) => update("usability_rating", value)} />
        <RatingSelect required label="学習への役立ち度" value={values.helpfulness_rating} onChange={(value) => update("helpfulness_rating", value)} />
        <RatingSelect required label="ヒント・説明の量" value={values.perceived_hint_amount} onChange={(value) => update("perceived_hint_amount", value)} />
        <label>
          自由記述（任意）
          <textarea value={values.free_comment} onChange={(event) => update("free_comment", event.target.value)} rows={5} />
        </label>
        {error ? <div className="danger">{error}</div> : null}
        <div className="actions">
          <button type="submit" disabled={submitting}>
            {submitting ? "保存しています..." : "回答を保存して終了"}
          </button>
        </div>
        </form>
      </AppShell>
    </ParticipantFlowGuard>
  );
}

function RatingSelect({
  label,
  value,
  onChange,
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  return (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)} required={required}>
        <option value="">選択してください</option>
        {RATING_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}

function numberOrNull(value: string) {
  return value ? Number(value) : null;
}
