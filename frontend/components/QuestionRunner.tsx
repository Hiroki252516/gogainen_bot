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
  selection_mode?: "single" | "multiple" | "free_text";
  min_selections?: number;
  max_selections?: number;
};

function multipleSelectionState(options: Option[], selectedIds: string[], requiredSelections = 3) {
  const selectedOptions = options.filter((option) => selectedIds.includes(option.option_id));
  const hasUnknown = selectedOptions.some((option) => option.label === "J");
  const normalSelectedCount = selectedOptions.filter((option) => option.label !== "J").length;
  const isComplete = (hasUnknown && selectedOptions.length === 1) || (!hasUnknown && normalSelectedCount === requiredSelections);
  return { selectedOptions, hasUnknown, normalSelectedCount, reachedLimit: !hasUnknown && normalSelectedCount >= requiredSelections, isComplete };
}

function nextMultipleSelection(options: Option[], selectedIds: string[], option: Option, requiredSelections = 3) {
  const isSelected = selectedIds.includes(option.option_id);
  if (isSelected) return selectedIds.filter((id) => id !== option.option_id);
  if (option.label === "J") return [option.option_id];
  const withoutUnknown = selectedIds.filter((id) => options.find((item) => item.option_id === id)?.label !== "J");
  return withoutUnknown.length >= requiredSelections ? selectedIds : [...withoutUnknown, option.option_id];
}

export function QuestionRunner({
  phase,
  title,
  sourcePath,
  scorePath,
  nextPath
}: {
  phase: string;
  title: string;
  sourcePath: (participantId: string) => string;
  scorePath?: (participantId: string) => string;
  nextPath: string;
}) {
  const router = useRouter();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [questionStartedAt, setQuestionStartedAt] = useState(() => Date.now());
  const [questionShownAt, setQuestionShownAt] = useState(() => new Date().toISOString());
  const current = questions[index];

  useEffect(() => {
    const id = requireParticipant();
    api<{ questions: Question[] }>(sourcePath(id))
      .then((data) => setQuestions(data.questions))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [sourcePath]);

  const progress = useMemo(() => (questions.length ? `${index + 1} / ${questions.length}` : ""), [index, questions.length]);

  useEffect(() => {
    setQuestionStartedAt(Date.now());
    setQuestionShownAt(new Date().toISOString());
  }, [current?.question_id]);

  async function submit() {
    if (!current) return;
    const isMultiple = current.selection_mode === "multiple";
    const minSelections = current.min_selections ?? (isMultiple ? 1 : 0);
    const maxSelections = current.max_selections ?? (isMultiple ? current.options.length : 1);
    const selectionState = multipleSelectionState(current.options, selectedIds, minSelections);
    if (isMultiple && (!selectionState.isComplete || selectedIds.length > maxSelections)) {
      setError(`A〜Iから${minSelections}つ選ぶか、「わからない」だけを選んでください。`);
      return;
    }
    if (!isMultiple && current.options.length && !selected) {
      setError("選択肢を選んでください。");
      return;
    }
    const requiresReason = current.requires_reason ?? true;
    if (requiresReason && !reason.trim()) {
      setError("理由を入力してください。");
      return;
    }
    setSaving(true);
    setError("");
    const id = requireParticipant();
    const answeredAt = new Date().toISOString();
    const responseTimeSec = Math.max(0.001, (Date.now() - questionStartedAt) / 1000);
    try {
      await api("/api/attempts", {
        method: "POST",
        body: JSON.stringify({
          participant_id: id,
          question_id: current.question_id,
          phase,
          selected_option_id: isMultiple ? (selectedIds[0] || null) : (selected || null),
          selected_option_ids: isMultiple ? selectedIds : null,
          free_text_answer: current.options.length ? null : reason || null,
          reason_text: requiresReason ? reason : null,
          response_time_sec: responseTimeSec,
          question_shown_at: questionShownAt,
          answered_at: answeredAt
        })
      });
      if (index + 1 < questions.length) {
        setIndex(index + 1);
        setSelected("");
        setSelectedIds([]);
        setReason("");
        setQuestionStartedAt(Date.now());
        setQuestionShownAt(new Date().toISOString());
        setSaving(false);
        return;
      }
      if (scorePath) {
        const result = await api<{ next_url?: string }>(scorePath(id), { method: "POST" });
        router.push(result.next_url || nextPath);
        return;
      }
      router.push(nextPath);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  if (loading) return <div className="panel">読み込み中...</div>;
  if (error && !current) return <div className="panel danger">{error}</div>;
  if (!current) return <div className="panel">問題がありません。</div>;

  const isMultipleQuestion = current.selection_mode === "multiple";
  const requiredSelections = current.min_selections ?? 3;
  const selectionState = multipleSelectionState(current.options, selectedIds, requiredSelections);
  const canSubmit = !saving && (!isMultipleQuestion || selectionState.isComplete);

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
      {isMultipleQuestion ? (
        <div className={`selection-status ${selectionState.isComplete ? "ok" : ""}`}>
          <strong>{selectionState.hasUnknown ? "わからないを選択中" : `${selectionState.normalSelectedCount}/${requiredSelections} 選択済み`}</strong>
          <span>
            {selectionState.hasUnknown
              ? "わからないを選ぶ場合は単独選択です。"
              : selectionState.reachedLimit
                ? "上限に達しました。変更するには選択済みの項目を外してください。"
                : `A〜Iから${requiredSelections}つ選ぶか、J「わからない」だけを選んでください。`}
          </span>
        </div>
      ) : null}
      {current.options.length > 0 ? (
        <div className="options">
          {current.options.map((option) => {
            const isSelected = isMultipleQuestion ? selectedIds.includes(option.option_id) : selected === option.option_id;
            const isUnknown = option.label === "J";
            const isDisabled =
              isMultipleQuestion &&
              !isSelected &&
              ((selectionState.hasUnknown && !isUnknown) ||
                (!isUnknown && selectionState.reachedLimit) ||
                (isUnknown && selectionState.normalSelectedCount > 0));
            return (
              <label className={`option ${isDisabled ? "option-disabled" : ""} ${isUnknown ? "option-unknown" : ""}`} key={option.option_id}>
                <input
                  type={isMultipleQuestion ? "checkbox" : "radio"}
                  name="option"
                  value={option.option_id}
                  checked={isSelected}
                  disabled={isDisabled}
                  onChange={() => {
                    if (!isMultipleQuestion) {
                      setSelected(option.option_id);
                      return;
                    }
                    setSelectedIds((currentIds) => nextMultipleSelection(current.options, currentIds, option, requiredSelections));
                  }}
                />
                <span>
                  <strong>{option.label}.</strong> {option.body}
                </span>
              </label>
            );
          })}
        </div>
      ) : null}
      {current.requires_reason ?? true ? (
        <label>
          {current.options.length ? "理由" : "回答"}
          <textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="自分の言葉で書いてください。" />
        </label>
      ) : null}
      {error ? <div className="danger">{error}</div> : null}
      <div className="actions">
        <button
          onClick={submit}
          disabled={!canSubmit}
        >
          {index + 1 === questions.length ? "完了" : "次へ"}
        </button>
        <span className="muted">このフェーズでは正誤やヒントは表示されません。</span>
      </div>
    </div>
  );
}
