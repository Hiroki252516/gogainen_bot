"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { GiveUpButton } from "@/components/GiveUpButton";
import { type Glossary } from "@/components/LearningGlossary";
import { GlossarySidebar } from "@/components/GlossarySidebar";
import { ApiError, api, clearPendingIdempotency, postIdempotent, requireParticipant } from "@/lib/api";

type Option = { option_id: string; label: string; body: string; exclusive?: boolean };
type SubmittedAnswer = {
  selected_option_ids?: string[] | null;
};
type Question = {
  question_id: string;
  term_slug: string;
  term_label: string;
  body: string;
  question_type: string;
  options: Option[];
  glossary?: Glossary | null;
  test_round?: string | null;
  test_round_label?: string | null;
  selection_mode?: "multiple";
  min_selections?: number;
  max_selections?: number;
  answer_status?: "unanswered" | "submitted";
  submitted_answer?: SubmittedAnswer | null;
};
type ScoreResult = { next_url?: string; learning_target_slugs?: string[] };

function multipleSelectionState(options: Option[], selectedIds: string[], requiredSelections = 3) {
  const selectedOptions = options.filter((option) => selectedIds.includes(option.option_id));
  const hasUnknown = selectedOptions.some((option) => option.exclusive);
  const normalSelectedCount = selectedOptions.filter((option) => !option.exclusive).length;
  const isComplete = (hasUnknown && selectedOptions.length === 1) || (!hasUnknown && normalSelectedCount === requiredSelections);
  return { selectedOptions, hasUnknown, normalSelectedCount, reachedLimit: !hasUnknown && normalSelectedCount >= requiredSelections, isComplete };
}

function nextMultipleSelection(options: Option[], selectedIds: string[], option: Option, requiredSelections = 3) {
  const isSelected = selectedIds.includes(option.option_id);
  if (isSelected) return selectedIds.filter((id) => id !== option.option_id);
  if (option.exclusive) return [option.option_id];
  const withoutUnknown = selectedIds.filter((id) => !options.find((item) => item.option_id === id)?.exclusive);
  return withoutUnknown.length >= requiredSelections ? selectedIds : [...withoutUnknown, option.option_id];
}

const toFullWidthDigits = (value: number) =>
  String(value).replace(/\d/g, (digit) => String.fromCharCode(digit.charCodeAt(0) + 0xfee0));

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

  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [displayTitle, setDisplayTitle] = useState(title);
  const [questionStartedAt, setQuestionStartedAt] = useState(() => Date.now());
  const [questionShownAt, setQuestionShownAt] = useState(() => new Date().toISOString());
  const current = questions[index];
  const preserveQuestionLines = (current?.term_slug === "llm_knowledge"
    && ((current.body.startsWith("企業が、社員からの「パスワードを忘れた」")
        && current.body.includes("\n\nこれらの目的を実現するための開発担当者の対応として、"))
      || (current.body.startsWith("大学が、教職員からの「学内ポータルのパスワードを忘れた」")
        && current.body.includes("\n\nこれらの目的を実現するための開発担当者の対応として、"))
      || (current.body.startsWith("企業が、会議の文字起こしをもとに議事録を作成するAI")
        && current.body.includes("\n\n現在は、AIが作成する議事録の文章構成や表現に"))))
    || (current?.term_slug === "multi_agent"
      && ((current.body.startsWith("旅行会社が、公共交通を利用する日帰り観光プラン")
          && current.body.includes("\n\nこのような旅行計画AIを実現するための"))
        || (current.body.startsWith("博物館が、館内を移動する短時間の見学コースを提案するAI")
          && current.body.includes("\n\nこのような見学計画AIを実現するための"))
        || (current.body.startsWith("博物館が、来館者に短い見学コースを提案するAI")
          && current.body.includes("\n\nこのAIシステムで複数のAIエージェントを協力させる設計として、"))))
    || (current?.term_slug === "memory_process"
      && (current.body.startsWith("料理の献立を提案するAIサービスを開発している。")
        || current.body.startsWith("企業が、利用者からの問い合わせに対応するAIを開発している。")
        || current.body.startsWith("企業が、利用者からの問い合わせに対応するAIサービスを開発している。"))
      && current.body.includes("\n\nこの目的を実現するための情報の保存・利用方法として、"));

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

  const progress = useMemo(
    () => (questions.length ? `${index + 1} / ${questions.length}` : ""),
    [index, questions.length],
  );

  useEffect(() => {
    setQuestionStartedAt(Date.now());
    setQuestionShownAt(new Date().toISOString());
    const submittedAnswer = current?.submitted_answer;
    setSelectedIds(submittedAnswer?.selected_option_ids || []);
  }, [current?.answer_status, current?.question_id, current?.submitted_answer]);

  async function advanceAfterAnswer() {
    if (index + 1 < questions.length) {
      setIndex(index + 1);
      setSelectedIds([]);
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
      // Test results are reviewed before moving to the next phase. The review
      // page reads the participant's current step to render the right action.
      const reviewRequired = phase === "retest" || phase === "final_test";
      router.replace(reviewRequired ? "/learning-targets" : (result.next_url || nextPath));
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
    const isMultiple = true;
    const minSelections = current.min_selections ?? 3;
    const maxSelections = current.max_selections ?? 3;
    const selectionState = multipleSelectionState(current.options, selectedIds, minSelections);
    if (isMultiple && (!selectionState.isComplete || selectedIds.length > maxSelections)) {
      setError(`選択肢から正しい説明を${minSelections}つ、または「わからない」のみを選んでください。`);
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
      selected_option_ids: selectedIds,
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

  const isMultipleQuestion = true;
  const isAnswered = current.answer_status === "submitted";
  const lockedAnswer = current.submitted_answer;
  const lockedSelectedIds = lockedAnswer?.selected_option_ids || [];
  const displayedSelectedIds = isAnswered && lockedAnswer ? lockedSelectedIds : selectedIds;
  const requiredSelections = current.min_selections ?? 3;
  const selectionState = multipleSelectionState(current.options, selectedIds, requiredSelections);
  const canSubmit = !saving && (isAnswered || !isMultipleQuestion || selectionState.isComplete);

  return (
    <div className={`panel glossary-layout ${current.glossary?.entries.length ? "has-glossary" : ""}`}>
      <div className="stack glossary-main">
      <div className="topbar">
        <h1>{displayTitle}</h1>
        <span className="muted question-progress" aria-label={progress}>{progress}</span>
      </div>
      <div className="notice">
        <div className="question-heading">
          <span>問{toFullWidthDigits(index + 1)}：</span>
          <strong>{current.term_label}</strong>
        </div>
        <p className={preserveQuestionLines ? "preserve-lines" : undefined}>{current.body}</p>
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
                : `選択肢から正しい説明を${requiredSelections}つ、または「わからない」のみを選んでください。`}
          </span>
        </div>
      ) : null}
      {current.options.length > 0 ? (
        <div className="options">
          {current.options.map((option) => {
            const isSelected = displayedSelectedIds.includes(option.option_id);
            const isUnknown = Boolean(option.exclusive);
            const isDisabled =
              isMultipleQuestion &&
              !isSelected &&
              ((selectionState.hasUnknown && !isUnknown) ||
                (!isUnknown && selectionState.reachedLimit) ||
                (isUnknown && selectionState.normalSelectedCount > 0));
            return (
              <label className={`option ${isDisabled ? "option-disabled" : ""} ${isAnswered && isSelected ? "option-selected-locked" : ""} ${isUnknown ? "option-unknown" : ""}`} key={option.option_id}>
                <input
                  type="checkbox"
                  name="option"
                  value={option.option_id}
                  checked={isSelected}
                  disabled={isAnswered || isDisabled}
                  onChange={() => {
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
      {error ? <div className="danger">{error}</div> : null}
      <div className="actions corner-primary">
        <button
          type="button"
          onClick={submit}
          disabled={!canSubmit}
        >
          {isAnswered ? (index + 1 === questions.length ? "完了" : "次の問題へ") : index + 1 === questions.length ? "完了" : "次へ"}
        </button>
      </div>
      <span className="muted">このフェーズでは正誤や正解の解説は表示されません。</span>
      {allowExperimentGiveUp ? (
        <div className="give-up-footer corner-exit">
          <GiveUpButton mode="experiment" disabled={saving} />
        </div>
      ) : null}
      </div>
      <GlossarySidebar key={current.question_id} glossary={current.glossary} label="テストの用語の補足" />
    </div>
  );
}
