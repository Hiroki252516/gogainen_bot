"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, requireParticipant } from "@/lib/api";

type Option = { option_id: string; label: string; body: string };
type Question = {
  question_id: string;
  term_slug: string;
  term_label: string;
  body: string;
  question_type: string;
  options: Option[];
  requires_reason?: boolean;
  requires_confidence?: boolean;
};

export function QuestionRunner({
  phase,
  title,
  sourcePath,
  scorePath,
  nextPath,
  collectReason = true,
  collectConfidence = false
}: {
  phase: string;
  title: string;
  sourcePath: (participantId: string) => string;
  scorePath?: (participantId: string) => string;
  nextPath: string;
  collectReason?: boolean;
  collectConfidence?: boolean;
}) {
  const router = useRouter();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState("");
  const [reason, setReason] = useState("");
  const [confidence, setConfidence] = useState("3");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const current = questions[index];

  useEffect(() => {
    const id = requireParticipant();
    api<{ questions: Question[] }>(sourcePath(id))
      .then((data) => setQuestions(data.questions))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [sourcePath]);

  const progress = useMemo(() => (questions.length ? `${index + 1} / ${questions.length}` : ""), [index, questions.length]);

  async function submit() {
    if (!current) return;
    if (current.options.length && !selected) {
      setError("選択肢を選んでください。");
      return;
    }
    const requiresReason = collectReason || current.requires_reason || current.options.length === 0;
    if (requiresReason && !reason.trim()) {
      setError("理由を入力してください。");
      return;
    }
    setSaving(true);
    setError("");
    const id = requireParticipant();
    await api("/api/attempts", {
      method: "POST",
      body: JSON.stringify({
        participant_id: id,
        question_id: current.question_id,
        phase,
        selected_option_id: selected || null,
        free_text_answer: current.options.length ? null : reason || null,
        reason_text: requiresReason ? reason : null,
        confidence: collectConfidence || current.requires_confidence ? Number(confidence) : null,
        response_time_sec: 10
      })
    });
    if (index + 1 < questions.length) {
      setIndex(index + 1);
      setSelected("");
      setReason("");
      setConfidence("3");
      setSaving(false);
      return;
    }
    if (scorePath) {
      await api(scorePath(id), { method: "POST" });
    }
    router.push(nextPath);
  }

  if (loading) return <div className="panel">読み込み中...</div>;
  if (error && !current) return <div className="panel danger">{error}</div>;
  if (!current) return <div className="panel">問題がありません。</div>;

  return (
    <div className="panel stack">
      <div className="topbar">
        <h1>{title}</h1>
        <span className="muted">{progress}</span>
      </div>
      <div className="notice">
        <strong>{current.term_label}</strong>
        <p>{current.body}</p>
      </div>
      {current.options.length > 0 ? (
        <div className="options">
          {current.options.map((option) => (
            <label className="option" key={option.option_id}>
              <input type="radio" name="option" value={option.option_id} checked={selected === option.option_id} onChange={() => setSelected(option.option_id)} />
              <span>
                <strong>{option.label}.</strong> {option.body}
              </span>
            </label>
          ))}
        </div>
      ) : null}
      {collectReason || current.requires_reason || current.options.length === 0 ? (
        <label>
          理由・回答
          <textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="自分の言葉で理由を書いてください。" />
        </label>
      ) : null}
      {collectConfidence || current.requires_confidence ? (
        <label>
          自信度 1〜5
          <select value={confidence} onChange={(event) => setConfidence(event.target.value)}>
            {[1, 2, 3, 4, 5].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {error ? <div className="danger">{error}</div> : null}
      <div className="actions">
        <button onClick={submit} disabled={saving}>
          {index + 1 === questions.length ? "完了" : "次へ"}
        </button>
        <span className="muted">このフェーズでは正誤やヒントは表示されません。</span>
      </div>
    </div>
  );
}
