"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { api, postIdempotent, requireParticipant } from "@/lib/api";

const SURVEY_STEPS = ["survey"] as const;
const EXPERIENCES = [
  ["chat", "チャット形式でAIを利用した経験"],
  ["coding_assistance", "プログラミングの補助にAIを利用した経験"],
  ["cli", "CLIからAIを利用した経験"],
  ["api", "APIからAIを利用した経験"],
] as const;
const GENERAL = [
  ["ai_usage_frequency", "普段のAI利用頻度", "1：使用しない ／ 10：非常に頻繁に使用する"],
  ["self_rated_ai_knowledge", "AIに関する知識の自己評価", "1：全く理解していない ／ 10：非常によく理解している"],
  ["system_usability", "システムは操作しやすかった", ""],
  ["system_clarity", "システムの使い方はわかりやすかった", ""],
] as const;
const MATERIAL = [
  ["clarity", "教材の内容はわかりやすかった"],
  ["readability", "教材は読みやすかった"],
  ["japanese_clarity", "教材の日本語はわかりやすかった"],
  ["difficulty_appropriateness", "教材の難易度は適切だった"],
  ["learning_usefulness", "教材は学習に役立った"],
  ["amount_appropriateness", "教材の量は適切だった"],
] as const;
const AGREEMENT_ANCHORS = "1：全くそう思わない ／ 10：非常にそう思う";
type Context = { survey_version: string; has_viewed_material: boolean; material_ratings_required: boolean };

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
    if (!comment.trim()) { setError("自由記述も必須です。特記事項がない場合は「特になし」と回答してください。"); return; }
    setSubmitting(true);
    setError("");
    try {
      const participantId = requireParticipant();
      await postIdempotent(`/api/participants/${participantId}/survey`, {
        survey_version: context.survey_version,
        experiences: Object.fromEntries(EXPERIENCES.map(([key]) => [key, values[key] === "yes"])),
        general_ratings: Object.fromEntries(GENERAL.map(([key]) => [key, Number(values[key])])),
        material_ratings: context.material_ratings_required ? Object.fromEntries(MATERIAL.map(([key]) => [key, Number(values[key])])) : null,
        free_comment: comment.trim(),
      }, `survey:${participantId}`);
      router.replace("/finish");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); setSubmitting(false); }
  }

  return <ParticipantFlowGuard allowedSteps={SURVEY_STEPS}>
    <AppShell step="アンケート">
      <form className="panel stack" onSubmit={submit}>
        <h1>実験後アンケート</h1>
        <p>表示される項目はすべて必須です。各質問について回答してください。</p>
        {!context ? <p>回答項目を確認しています。</p> : <>
          <h2>AIの利用経験</h2>
          {EXPERIENCES.map(([key, label]) => <label key={key}>{label}
            <select required value={values[key] || ""} disabled={submitting} onChange={(event) => update(key, event.target.value)}>
              <option value="">選択してください</option><option value="yes">ある</option><option value="no">ない</option>
            </select>
          </label>)}
          <h2>AIとシステムについて</h2>
          {GENERAL.map(([key, label, anchors]) => <RatingSelect key={key} label={label} anchors={anchors || AGREEMENT_ANCHORS} value={values[key] || ""} disabled={submitting} onChange={(value) => update(key, value)} />)}
          <h2>教材について</h2>
          {context.material_ratings_required
            ? MATERIAL.map(([key, label]) => <RatingSelect key={key} label={label} anchors={AGREEMENT_ANCHORS} value={values[key] || ""} disabled={submitting} onChange={(value) => update(key, value)} />)
            : <p>教材の表示記録がないため、教材評価6項目は対象外です。</p>}
          <label>自由記述（必須）
            <textarea required value={comment} disabled={submitting} onChange={(event) => setComment(event.target.value)} rows={5} />
            <span className="muted">特記事項がない場合は「特になし」と回答してください。</span>
          </label>
        </>}
        {error ? <div className="danger" role="alert">{error}</div> : null}
        {!context && error ? <button type="button" onClick={() => void loadContext()}>再読み込み</button> : null}
        <button type="submit" disabled={submitting || !context}>{submitting ? "保存しています..." : "回答を保存して終了"}</button>
      </form>
    </AppShell>
  </ParticipantFlowGuard>;
}

function RatingSelect({ label, anchors, value, disabled, onChange }: { label: string; anchors: string; value: string; disabled: boolean; onChange: (value: string) => void }) {
  return <label>{label}<span className="muted">{anchors}</span>
    <select required value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
      <option value="">選択してください</option>
      {Array.from({ length: 10 }, (_, index) => index + 1).map((number) => <option key={number} value={number}>{number}</option>)}
    </select>
  </label>;
}
