"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { GiveUpButton } from "@/components/GiveUpButton";
import { ApiError, api, clearPendingIdempotency, postIdempotent, requireParticipant } from "@/lib/api";

type Option = { option_id: string; label: string; body: string };
type SubmittedAnswer = {
  selected_option_id?: string | null;
  selected_option_ids?: string[] | null;
  free_text_answer?: string | null;
  reason_text?: string | null;
};
type Question = {
  question_id: string;
  term_slug: string;
  term_label: string;
  body: string;
  question_type: string;
  options: Option[];
  test_round?: string | null;
  test_round_label?: string | null;
  requires_reason?: boolean;
  selection_mode?: "single" | "multiple" | "free_text";
  min_selections?: number;
  max_selections?: number;
  answer_status?: "unanswered" | "submitted";
  submitted_answer?: SubmittedAnswer | null;
};
type ScoreResult = { next_url?: string; learning_target_slugs?: string[] };

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
  nextPath,
  onDisplayTitle,
  allowExperimentGiveUp = false,
}: {
  phase: string;
  title: string;
  sourcePath: (participantId: string) => string;
  scorePath?: (participantId: string) => string;
  nextPath: string;
  onDisplayTitle?: (displayTitle: string) => void;
  allowExperimentGiveUp?: boolean;
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
  const [displayTitle, setDisplayTitle] = useState(title);
  const [questionStartedAt, setQuestionStartedAt] = useState(() => Date.now());
  const [questionShownAt, setQuestionShownAt] = useState(() => new Date().toISOString());
  const current = questions[index];

  useEffect(() => {
    const id = requireParticipant();
    api<{ questions: Question[] }>(sourcePath(id))
      .then((data) => {
        setQuestions(data.questions);
        const nextTitle = data.questions[0]?.test_round_label || title;
        setDisplayTitle(nextTitle);
        onDisplayTitle?.(nextTitle);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [onDisplayTitle, sourcePath, title]);

  const progress = useMemo(() => (questions.length ? `${index + 1} / ${questions.length}` : ""), [index, questions.length]);

  useEffect(() => {
    setQuestionStartedAt(Date.now());
    setQuestionShownAt(new Date().toISOString());
    const submittedAnswer = current?.submitted_answer;
    const submittedIds = submittedAnswer?.selected_option_ids?.length
      ? submittedAnswer.selected_option_ids
      : submittedAnswer?.selected_option_id
        ? [submittedAnswer.selected_option_id]
        : [];
    setSelected(submittedAnswer?.selected_option_id || "");
    setSelectedIds(submittedIds);
    setReason(submittedAnswer?.reason_text || submittedAnswer?.free_text_answer || "");
  }, [current?.answer_status, current?.question_id, current?.submitted_answer]);

  async function advanceAfterAnswer() {
    if (index + 1 < questions.length) {
      setIndex(index + 1);
      setSelected("");
      setSelectedIds([]);
      setReason("");
      setError("");
      setQuestionStartedAt(Date.now());
      setQuestionShownAt(new Date().toISOString());
      setSaving(false);
      return;
    }
    if (!scorePath) {
      router.replace(nextPath);
      return;
    }

    setSaving(true);
    setError("");
    try {
      const id = requireParticipant();
      const result = await postIdempotent<ScoreResult>(
        scorePath(id),
        {},
        `score:${id}:${phase}`,
      );
      if (Array.isArray(result.learning_target_slugs)) {
        localStorage.setItem("learning_targets", JSON.stringify(result.learning_target_slugs));
      }
      router.replace(result.next_url || nextPath);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  async function submit() {
    if (!current) return;
    if (current.answer_status === "submitted") {
      await advanceAfterAnswer();
      return;
    }
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
    const attemptBody = {
      participant_id: id,
      question_id: current.question_id,
      phase,
      selected_option_id: isMultiple ? (selectedIds[0] || null) : (selected || null),
      selected_option_ids: isMultiple ? selectedIds : null,
      free_text_answer: current.options.length ? null : reason || null,
      reason_text: requiresReason ? reason : null,
      response_time_sec: responseTimeSec,
      question_shown_at: questionShownAt,
      answered_at: answeredAt,
    };
    const attemptScope = `attempt:${id}:${phase}:${current.question_id}:${current.test_round || ""}`;
    try {
      await postIdempotent("/api/attempts", attemptBody, attemptScope);
      await advanceAfterAnswer();
    } catch (err) {
      if (err instanceof ApiError && (err.code === "answer_already_submitted" || err.code === "idempotency_key_conflict")) {
        clearPendingIdempotency(attemptScope);
        let refreshed = false;
        try {
          const latest = await api<{ questions: Question[] }>(sourcePath(id));
          setQuestions(latest.questions);
          refreshed = true;
        } catch {
          // Keep the locked state even if the follow-up read also fails.
        }
        if (!refreshed) {
          setQuestions((previous) => previous.map((question, questionIndex) => (
            questionIndex === index ? { ...question, answer_status: "submitted" } : question
          )));
        }
        setError("この問題はすでに回答済みです。回答は変更できません。次の問題へ進んでください。");
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
      setSaving(false);
    }
  }

  if (loading) return <div className="panel">読み込み中...</div>;
  if (error && !current) return <div className="panel danger">{error}</div>;
  if (!current) return <div className="panel">問題がありません。</div>;

  const isMultipleQuestion = current.selection_mode === "multiple";
  const isAnswered = current.answer_status === "submitted";
  const lockedAnswer = current.submitted_answer;
  const lockedSelectedIds = lockedAnswer?.selected_option_ids?.length
    ? lockedAnswer.selected_option_ids
    : lockedAnswer?.selected_option_id
      ? [lockedAnswer.selected_option_id]
      : [];
  const displayedSelectedIds = isAnswered && lockedAnswer ? lockedSelectedIds : selectedIds;
  const displayedSelectedId = isAnswered && lockedAnswer
    ? lockedAnswer.selected_option_id || lockedSelectedIds[0] || ""
    : selected;
  const displayedReason = isAnswered && lockedAnswer
    ? lockedAnswer.reason_text || lockedAnswer.free_text_answer || ""
    : reason;
  const requiredSelections = current.min_selections ?? 3;
  const selectionState = multipleSelectionState(current.options, selectedIds, requiredSelections);
  const canSubmit = !saving && (isAnswered || !isMultipleQuestion || selectionState.isComplete);

  return (
    <div className="panel stack">
      <div className="topbar">
        <h1>{displayTitle}</h1>
        <span className="muted">{progress}</span>
      </div>
      <div className="notice">
        <strong>{current.term_label}</strong>
        <p>{current.body}</p>
      </div>
      {isAnswered ? (
        <div className="notice answer-locked" role="status">
          <strong>回答済み・変更不可</strong>
          <p>この問題の回答は保存済みです。内容を変更せず、次の問題へ進んでください。</p>
        </div>
      ) : isMultipleQuestion ? (
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
            const isSelected = isMultipleQuestion
              ? displayedSelectedIds.includes(option.option_id)
              : displayedSelectedId === option.option_id;
            const isUnknown = option.label === "J";
            const isDisabled =
              isMultipleQuestion &&
              !isSelected &&
              ((selectionState.hasUnknown && !isUnknown) ||
                (!isUnknown && selectionState.reachedLimit) ||
                (isUnknown && selectionState.normalSelectedCount > 0));
            return (
              <label className={`option ${isDisabled ? "option-disabled" : ""} ${isAnswered && isSelected ? "option-selected-locked" : ""} ${isUnknown ? "option-unknown" : ""}`} key={option.option_id}>
                <input
                  type={isMultipleQuestion ? "checkbox" : "radio"}
                  name="option"
                  value={option.option_id}
                  checked={isSelected}
                  disabled={isAnswered || isDisabled}
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
          <textarea value={displayedReason} onChange={(event) => setReason(event.target.value)} placeholder="自分の言葉で書いてください。" disabled={isAnswered || saving} />
        </label>
      ) : null}
      {error ? <div className="danger">{error}</div> : null}
      <div className="actions">
        <button
          type="button"
          onClick={submit}
          disabled={!canSubmit}
        >
          {isAnswered ? (index + 1 === questions.length ? "完了" : "次の問題へ") : index + 1 === questions.length ? "完了" : "次へ"}
        </button>
        <span className="muted">このフェーズでは正誤やヒントは表示されません。</span>
      </div>
      {allowExperimentGiveUp ? (
        <div className="give-up-footer">
          <GiveUpButton mode="experiment" disabled={saving} />
        </div>
      ) : null}
    </div>
  );
}
