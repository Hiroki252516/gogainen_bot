"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { type Glossary } from "@/components/LearningGlossary";
import { GlossarySidebar } from "@/components/GlossarySidebar";
import { prepareGroupedQuestionDisplay } from "@/lib/learning-question-display";
import { combineTestGlossaries, groupTestQuestionsByTerm, initialTestTermPageIndex, normalizeTestRound, sameTestRound } from "@/lib/test-term-pages";
import { optionAnswerClass } from "@/lib/option-answer-display";
import { ApiError, api, clearPendingIdempotency, getPendingIdempotentBody, postIdempotent, requireParticipant } from "@/lib/api";

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
  selection_mode?: "multiple" | "single";
  min_selections?: number;
  max_selections?: number;
  answer_status?: "unanswered" | "submitted";
  submitted_answer?: SubmittedAnswer | null;
};
type ScoreResult = { next_url?: string; learning_target_slugs?: string[]; review_required?: boolean };
type PendingQuestionReview = {
  phase: string;
  term_slug: string;
  term_label: string;
  results: Array<{
    question_number: 1 | 2;
    selected_option: { label: string; body: string };
    is_correct: boolean;
  }>;
};
type GiveUpActionState = { visible: boolean; disabled: boolean };
type TestQuestionsResponse = {
  questions: Question[];
  pending_question_review?: PendingQuestionReview | null;
  test_page_mode?: "per_question" | "per_term";
};
type TestPageAnswer = { question_id: string; selected_option_ids: string[] };
type TestPageSubmission = {
  participant_id: string;
  phase: string;
  term_slug: string;
  test_round: string;
  page_id: string;
  answers: TestPageAnswer[];
  question_shown_at: string;
  answered_at: string;
  elapsed_time_sec: number;
};

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

function QuestionReviewPanel({
  review,
  saving,
  error,
  onContinue,
}: {
  review: PendingQuestionReview;
  saving: boolean;
  error: string;
  onContinue: () => void;
}) {
  return (
    <div className="panel stack">
      <div className="topbar">
        <h1>{review.term_label}の答え合わせ</h1>
      </div>
      <div className="notice stack" role="status">
        {review.results.map((result) => (
          <div className="notice" key={result.question_number}>
            <strong>設問{toFullWidthDigits(result.question_number)}：{result.is_correct ? "正解" : "不正解"}</strong>
            <p>あなたの選択：{result.selected_option.label}. {result.selected_option.body}</p>
          </div>
        ))}
      </div>
      {error ? <div className="danger" role="alert">{error}</div> : null}
      <div className="actions corner-primary">
        <button type="button" onClick={onContinue} disabled={saving}>
          {saving ? "保存中..." : "続行"}
        </button>
      </div>
    </div>
  );
}

export function QuestionRunner({
  phase,
  title,
  sourcePath,
  scorePath,
  nextPath,
  onDisplayTitle,
  allowExperimentGiveUp = false,
  onGiveUpStateChange,
}: {
  phase: string;
  title: string;
  sourcePath: (participantId: string) => string;
  scorePath?: (participantId: string) => string;
  nextPath: string;
  onDisplayTitle?: (displayTitle: string) => void;
  allowExperimentGiveUp?: boolean;
  onGiveUpStateChange?: (state: GiveUpActionState) => void;
}) {
  const router = useRouter();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [index, setIndex] = useState(0);
  const [pendingQuestionReview, setPendingQuestionReview] = useState<PendingQuestionReview | null>(null);
  const [testPageMode, setTestPageMode] = useState<"per_question" | "per_term">("per_question");

  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [displayTitle, setDisplayTitle] = useState(title);
  const [questionStartedAt, setQuestionStartedAt] = useState(() => Date.now());
  const [questionShownAt, setQuestionShownAt] = useState(() => new Date().toISOString());
  const completionStarted = useRef(false);
  const current = questions[index];
  useEffect(() => {
    if (testPageMode === "per_term") return;
    onGiveUpStateChange?.({
      visible: allowExperimentGiveUp && !loading && Boolean(current || pendingQuestionReview),
      disabled: saving,
    });
  }, [allowExperimentGiveUp, current?.question_id, loading, onGiveUpStateChange, pendingQuestionReview, saving, testPageMode]);

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

  const completePhase = useCallback(async () => {
    if (completionStarted.current) return;
    completionStarted.current = true;
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
      const reviewRequired = result.review_required ?? (phase === "retest" || phase === "final_test");
      router.replace(reviewRequired ? "/learning-targets" : (result.next_url || nextPath));
    } catch (err) {
      completionStarted.current = false;
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }, [nextPath, phase, router, scorePath]);

  const reviewQuestionIndex = useCallback((review: PendingQuestionReview, rows: Question[]) => {
    const matching = rows.reduce((lastIndex, question, questionIndex) => (
      question.term_slug === review.term_slug ? questionIndex : lastIndex
    ), -1);
    return matching;
  }, []);

  useEffect(() => {
    const id = requireParticipant();
    api<TestQuestionsResponse>(sourcePath(id))
      .then((data) => {
        setQuestions(data.questions);
        setTestPageMode(data.test_page_mode === "per_term" ? "per_term" : "per_question");
        if (data.pending_question_review) {
          setPendingQuestionReview(data.pending_question_review);
          setIndex(reviewQuestionIndex(data.pending_question_review, data.questions));
        } else if (data.test_page_mode === "per_term") {
          const pages = groupTestQuestionsByTerm(data.questions);
          if (pages) setIndex(initialTestTermPageIndex(pages));
        } else {
          const firstUnanswered = data.questions.findIndex((question) => question.answer_status !== "submitted");
          if (firstUnanswered >= 0) {
            setIndex(firstUnanswered);
          } else if (data.questions.length) {
            setIndex(data.questions.length - 1);
            void completePhase();
          }
        }
        const nextTitle = data.questions[0]?.test_round_label || title;
        setDisplayTitle(nextTitle);
        onDisplayTitle?.(nextTitle);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [completePhase, onDisplayTitle, reviewQuestionIndex, sourcePath, title]);

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
    await completePhase();
  }

  async function submit() {
    if (!current) return;
    if (current.answer_status === "submitted") {
      await advanceAfterAnswer();
      return;
    }
    const isMultiple = current.selection_mode !== "single";
    const minSelections = current.min_selections ?? 3;
    const maxSelections = current.max_selections ?? 3;
    const selectionState = multipleSelectionState(current.options, selectedIds, minSelections);
    if (isMultiple && (!selectionState.isComplete || selectedIds.length > maxSelections)) {
      setError(`選択肢から正しい説明を${minSelections}つ、または「わからない」のみを選んでください。`);
      return;
    }
    if (!isMultiple && selectedIds.length !== 1) { setError("選択肢を1つ選んでください。"); return; }
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
      const latest = await api<TestQuestionsResponse>(sourcePath(id));
      setQuestions(latest.questions);
      if (latest.pending_question_review) {
        setPendingQuestionReview(latest.pending_question_review);
        setIndex(reviewQuestionIndex(latest.pending_question_review, latest.questions));
        setSaving(false);
      } else {
        setPendingQuestionReview(null);
        await advanceAfterAnswer();
      }
    } catch (err) {
      if (err instanceof ApiError && (err.code === "answer_already_submitted" || err.code === "idempotency_key_conflict")) {
        clearPendingIdempotency(attemptScope);
        let refreshed = false;
        let hasPendingReview = false;
        try {
          const latest = await api<TestQuestionsResponse>(sourcePath(id));
          setQuestions(latest.questions);
          if (latest.pending_question_review) {
            hasPendingReview = true;
            setPendingQuestionReview(latest.pending_question_review);
            setIndex(reviewQuestionIndex(latest.pending_question_review, latest.questions));
          }
          refreshed = true;
        } catch {
          // Keep the locked state even if the follow-up read also fails.
        }
        if (!refreshed) {
          setQuestions((previous) => previous.map((question, questionIndex) => (
            questionIndex === index ? { ...question, answer_status: "submitted" } : question
          )));
        }
        setError(hasPendingReview ? "" : "この問題はすでに回答済みです。回答は変更できません。次の問題へ進んでください。");
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
      setSaving(false);
    }
  }

  async function continueFromQuestionReview() {
    if (!pendingQuestionReview || saving) return;
    setSaving(true);
    setError("");
    try {
      const id = requireParticipant();
      await api(`/api/participants/${id}/question-review-acknowledgements`, {
        method: "POST",
        body: JSON.stringify({ phase, term_slug: pendingQuestionReview.term_slug }),
      });
      const latest = await api<TestQuestionsResponse>(sourcePath(id));
      setQuestions(latest.questions);
      if (latest.pending_question_review) {
        setPendingQuestionReview(latest.pending_question_review);
        setIndex(reviewQuestionIndex(latest.pending_question_review, latest.questions));
        setSaving(false);
        return;
      }
      setPendingQuestionReview(null);
      const firstUnanswered = latest.questions.findIndex((question) => question.answer_status !== "submitted");
      if (firstUnanswered >= 0) {
        setIndex(firstUnanswered);
        setSaving(false);
        return;
      }
      setIndex(Math.max(0, latest.questions.length - 1));
      await completePhase();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  if (loading) return <div className="panel">読み込み中...</div>;
  if (testPageMode === "per_term") {
    return (
      <TermPageQuestionRunner
        questions={questions}
        initialPendingQuestionReview={pendingQuestionReview}
        phase={phase}
        title={displayTitle}
        sourcePath={sourcePath}
        scorePath={scorePath}
        nextPath={nextPath}
        allowExperimentGiveUp={allowExperimentGiveUp}
        onGiveUpStateChange={onGiveUpStateChange}
      />
    );
  }
  if (pendingQuestionReview) {
    return (
      <QuestionReviewPanel
        review={pendingQuestionReview}
        saving={saving}
        error={error}
        onContinue={continueFromQuestionReview}
      />
    );
  }
  if (error && !current) return <div className="panel danger">{error}</div>;
  if (!current) return <div className="panel">問題がありません。</div>;

  const isMultipleQuestion = current.selection_mode !== "single";
  const isAnswered = current.answer_status === "submitted";
  const lockedAnswer = current.submitted_answer;
  const lockedSelectedIds = lockedAnswer?.selected_option_ids || [];
  const displayedSelectedIds = isAnswered && lockedAnswer ? lockedSelectedIds : selectedIds;
  const requiredSelections = current.min_selections ?? 3;
  const selectionState = multipleSelectionState(current.options, selectedIds, requiredSelections);
  const canSubmit = !saving && (isAnswered || (isMultipleQuestion ? selectionState.isComplete : selectedIds.length === 1));

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
        <p className={preserveQuestionLines || current.selection_mode === "single" ? "preserve-lines" : undefined}>{current.body}</p>
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
      ) : <div className="selection-status">最も適切なものを1つ選んでください。</div>}
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
                  type={isMultipleQuestion ? "checkbox" : "radio"}
                  name="option"
                  value={option.option_id}
                  checked={isSelected}
                  disabled={isAnswered || isDisabled}
                  onChange={() => {
                    setSelectedIds((currentIds) => isMultipleQuestion ? nextMultipleSelection(current.options, currentIds, option, requiredSelections) : [option.option_id]);
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
      </div>
      <GlossarySidebar key={current.question_id} glossary={current.glossary} label="テストの用語の補足" />
    </div>
  );
}

function newPageId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16);
    return (character === "x" ? random : (random & 0x3) | 0x8).toString(16);
  });
}

function newPageTiming() {
  const startedAt = Date.now();
  return { pageId: newPageId(), startedAt, shownAt: new Date(startedAt).toISOString() };
}

function pageSubmissionScope(participantId: string, phase: string, page: { term_slug: string; test_round: string | null }) {
  return `test-page:${participantId}:${phase}:${page.term_slug}:${normalizeTestRound(page.test_round)}`;
}

function isPageSubmissionFor(
  value: unknown,
  participantId: string,
  phase: string,
  page: { term_slug: string; test_round: string | null; questions: Question[] },
): value is TestPageSubmission {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<TestPageSubmission>;
  const expectedIds = new Set(page.questions.map((question) => question.question_id));
  return candidate.participant_id === participantId
    && candidate.phase === phase
    && candidate.term_slug === page.term_slug
    && sameTestRound(candidate.test_round, page.test_round)
    && typeof candidate.page_id === "string"
    && typeof candidate.question_shown_at === "string"
    && typeof candidate.answered_at === "string"
    && typeof candidate.elapsed_time_sec === "number"
    && Number.isFinite(candidate.elapsed_time_sec)
    && candidate.elapsed_time_sec > 0
    && Array.isArray(candidate.answers)
    && candidate.answers.length === 2
    && candidate.answers.every((answer) => Boolean(
      answer
      && typeof answer === "object"
      && expectedIds.has(answer.question_id)
      && Array.isArray(answer.selected_option_ids)
      && answer.selected_option_ids.length === 1
      && typeof answer.selected_option_ids[0] === "string"
      && answer.selected_option_ids[0].length > 0
    ))
    && new Set(candidate.answers.map((answer) => answer.question_id)).size === 2;
}

function TermPageQuestionRunner({
  questions,
  initialPendingQuestionReview,
  phase,
  title,
  sourcePath,
  scorePath,
  nextPath,
  allowExperimentGiveUp,
  onGiveUpStateChange,
}: {
  questions: Question[];
  initialPendingQuestionReview: PendingQuestionReview | null;
  phase: string;
  title: string;
  sourcePath: (participantId: string) => string;
  scorePath?: (participantId: string) => string;
  nextPath: string;
  allowExperimentGiveUp: boolean;
  onGiveUpStateChange?: (state: GiveUpActionState) => void;
}) {
  const router = useRouter();
  const [participantId, setParticipantId] = useState("");

  useEffect(() => {
    try {
      setParticipantId(requireParticipant());
    } catch {
      setParticipantId("");
    }
  }, []);
  const [currentQuestions, setCurrentQuestions] = useState(questions);
  const pages = useMemo(() => groupTestQuestionsByTerm(currentQuestions), [currentQuestions]);
  const [pageIndex, setPageIndex] = useState(() => {
    if (!pages) return 0;
    if (initialPendingQuestionReview) {
      const reviewIndex = pages.findIndex((candidate) => candidate.term_slug === initialPendingQuestionReview.term_slug);
      if (reviewIndex >= 0) return reviewIndex;
    }
    return initialTestTermPageIndex(pages);
  });
  const [selectedByQuestion, setSelectedByQuestion] = useState<Record<string, string[]>>(() => Object.fromEntries(
    questions.map((question) => [question.question_id, question.submitted_answer?.selected_option_ids || []]),
  ));
  const [timing, setTiming] = useState(newPageTiming);
  const [frozenPage, setFrozenPage] = useState<{ scope: string; body: TestPageSubmission } | null>(null);
  const [pendingQuestionReview, setPendingQuestionReview] = useState<PendingQuestionReview | null>(initialPendingQuestionReview);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const page = pages?.[pageIndex];
  const glossary = useMemo(() => page ? combineTestGlossaries(page.questions) : null, [page]);
  const pageScope = page && participantId ? pageSubmissionScope(participantId, phase, page) : "";
  const pageIsFrozen = frozenPage?.scope === pageScope;
  const pageAlreadySaved = Boolean(page?.questions.every((question) => question.answer_status === "submitted"));
  const canAnswerAll = Boolean(page?.questions.every((question) =>
    question.answer_status === "submitted" || (selectedByQuestion[question.question_id] || []).length === 1,
  ));

  useEffect(() => {
    onGiveUpStateChange?.({
      visible: allowExperimentGiveUp && Boolean(page),
      disabled: saving,
    });
  }, [allowExperimentGiveUp, onGiveUpStateChange, page?.key, saving]);

  useEffect(() => {
    if (!page || !participantId) return;
    const scope = pageSubmissionScope(participantId, phase, page);
    setTiming(newPageTiming());
    setError("");
    const pending = getPendingIdempotentBody<TestPageSubmission>(scope);
    if (isPageSubmissionFor(pending, participantId, phase, page)) {
      setFrozenPage({ scope, body: pending });
      setSelectedByQuestion((previous) => ({
        ...previous,
        ...Object.fromEntries(pending.answers.map((answer) => [answer.question_id, answer.selected_option_ids])),
      }));
    } else {
      clearPendingIdempotency(scope);
      setFrozenPage(null);
      setSelectedByQuestion((previous) => ({
        ...previous,
        ...Object.fromEntries(page.questions.map((question) => [
          question.question_id,
          question.submitted_answer?.selected_option_ids || previous[question.question_id] || [],
        ])),
      }));
    }
  }, [page?.key, phase, participantId]);

  async function advance() {
    if (!pages || !page) return;
    if (pageIndex + 1 < pages.length) {
      setPageIndex((previous) => previous + 1);
      setError("");
      setSaving(false);
      return;
    }
    await completePhase();
  }

  async function completePhase() {
    if (!scorePath) {
      router.replace(nextPath);
      return;
    }
    setSaving(true);
    setError("");
    try {
      const participantId = requireParticipant();
      const result = await postIdempotent<ScoreResult>(scorePath(participantId), {}, `score:${participantId}:${phase}`);
      if (Array.isArray(result.learning_target_slugs)) {
        localStorage.setItem("learning_targets", JSON.stringify(result.learning_target_slugs));
      }
      const reviewRequired = result.review_required ?? (phase === "retest" || phase === "final_test");
      router.replace(reviewRequired ? "/learning-targets" : (result.next_url || nextPath));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  async function submitPage() {
    if (!page || !pages || saving) return;
    if (pageAlreadySaved) {
      await advance();
      return;
    }
    if (!participantId) {
      setError("参加者情報を確認できません。開始画面から再開してください。");
      return;
    }
    const scope = pageSubmissionScope(participantId, phase, page);
    let body = frozenPage?.scope === scope ? frozenPage.body : null;
    if (!body) {
      const answers = page.questions.map((question) => ({
        question_id: question.question_id,
        selected_option_ids: selectedByQuestion[question.question_id] || [],
      }));
      if (answers.some((answer) => answer.selected_option_ids.length !== 1)) {
        setError("各設問で選択肢を1つ選んでください。");
        return;
      }
      const answeredAt = new Date().toISOString();
      body = {
        participant_id: participantId,
        phase,
        term_slug: page.term_slug,
        test_round: normalizeTestRound(page.test_round),
        page_id: timing.pageId,
        answers,
        question_shown_at: timing.shownAt,
        answered_at: answeredAt,
        elapsed_time_sec: Math.max(0.001, (Date.now() - timing.startedAt) / 1000),
      };
      setFrozenPage({ scope, body });
    }
    setSaving(true);
    setError("");
    try {
      await postIdempotent("/api/attempts/term-page", body, scope);
      setFrozenPage(null);
      const latest = await api<TestQuestionsResponse>(sourcePath(participantId));
      setCurrentQuestions(latest.questions);
      setSelectedByQuestion((previous) => ({
        ...previous,
        ...Object.fromEntries(latest.questions.map((question) => [
          question.question_id,
          question.submitted_answer?.selected_option_ids || previous[question.question_id] || [],
        ])),
      }));
      if (latest.pending_question_review) {
        setPendingQuestionReview(latest.pending_question_review);
        const reviewPages = groupTestQuestionsByTerm(latest.questions);
        const reviewIndex = reviewPages?.findIndex((candidate) => candidate.term_slug === latest.pending_question_review?.term_slug) ?? -1;
        if (reviewIndex >= 0) setPageIndex(reviewIndex);
        setSaving(false);
        return;
      }
      const latestPages = groupTestQuestionsByTerm(latest.questions);
      if (!latestPages) throw new Error("テスト問題を用語ごとにまとめられません。管理者に連絡してください。");
      const firstIncomplete = latestPages.findIndex((candidate) => candidate.questions.some((question) => question.answer_status !== "submitted"));
      if (firstIncomplete >= 0) {
        setPageIndex(firstIncomplete);
        setSaving(false);
      } else {
        await completePhase();
      }
    } catch (err) {
      if (err instanceof ApiError && (err.code === "answer_already_submitted" || err.code === "idempotency_key_conflict")) {
        try {
          const latest = await api<TestQuestionsResponse>(sourcePath(participantId));
          setCurrentQuestions(latest.questions);
          if (latest.pending_question_review) setPendingQuestionReview(latest.pending_question_review);
          setSelectedByQuestion((previous) => ({
            ...previous,
            ...Object.fromEntries(latest.questions.map((question) => [
              question.question_id,
              question.submitted_answer?.selected_option_ids || previous[question.question_id] || [],
            ])),
          }));
          clearPendingIdempotency(scope);
          setFrozenPage(null);
          setError(latest.pending_question_review ? "" : "保存済みの回答と競合しました。保存された回答を確認してください。");
        } catch {
          setError(err.message);
        }
      } else {
        if (err instanceof ApiError && err.status >= 400 && err.status < 500 && err.code !== "idempotency_in_progress") {
          setFrozenPage(null);
        }
        setError(err instanceof Error ? err.message : String(err));
      }
      setSaving(false);
    }
  }

  async function continueFromQuestionReview() {
    if (!pendingQuestionReview || saving || !participantId) return;
    setSaving(true);
    setError("");
    try {
      await api(`/api/participants/${participantId}/question-review-acknowledgements`, {
        method: "POST",
        body: JSON.stringify({ phase, term_slug: pendingQuestionReview.term_slug }),
      });
      const latest = await api<TestQuestionsResponse>(sourcePath(participantId));
      setCurrentQuestions(latest.questions);
      setPendingQuestionReview(latest.pending_question_review || null);
      if (latest.pending_question_review) {
        const latestPages = groupTestQuestionsByTerm(latest.questions);
        const reviewIndex = latestPages?.findIndex((candidate) => candidate.term_slug === latest.pending_question_review?.term_slug) ?? -1;
        if (reviewIndex >= 0) setPageIndex(reviewIndex);
        setSaving(false);
        return;
      }
      const latestPages = groupTestQuestionsByTerm(latest.questions);
      if (!latestPages) throw new Error("テスト問題を用語ごとにまとめられません。管理者に連絡してください。");
      const firstIncomplete = latestPages.findIndex((candidate) => candidate.questions.some((question) => question.answer_status !== "submitted"));
      if (firstIncomplete >= 0) {
        setPageIndex(firstIncomplete);
        setSaving(false);
        return;
      }
      setPageIndex(Math.max(0, latestPages.length - 1));
      await completePhase();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  if (!pages) return <div className="panel danger">テスト問題を用語ごとにまとめられません。管理者に連絡してください。</div>;
  if (!page) return <div className="panel">問題がありません。</div>;

  const display = prepareGroupedQuestionDisplay(page.questions);
  const questionBodies = display?.questionBodies || page.questions.map((question) => question.body);
  const isLastPage = pageIndex + 1 === pages.length;

  return (
    <div className={`panel glossary-layout term-page-runner ${glossary?.entries.length ? "has-glossary" : ""}`}>
      <div className="stack glossary-main">
        <div className="topbar">
          <h1>{title}</h1>
          <span className="muted question-progress" aria-label={`${pageIndex + 1} / ${pages.length}`}>{pageIndex + 1} / {pages.length}</span>
        </div>
        <div className="notice">
          <div className="question-heading">
            <span>問{toFullWidthDigits(pageIndex + 1)}：</span>
            <strong>{page.term_label}</strong>
          </div>
          {display?.sharedScenario ? <p className="preserve-lines">{display.sharedScenario}</p> : null}
        </div>
        <div className="stack term-page-questions">
          {page.questions.map((question, questionIndex) => {
            const isAnswered = question.answer_status === "submitted";
            const selectedIds = isAnswered
              ? question.submitted_answer?.selected_option_ids || []
              : selectedByQuestion[question.question_id] || [];
            const reviewResult = pendingQuestionReview?.term_slug === page.term_slug
              ? pendingQuestionReview.results.find((result) => result.question_number === questionIndex + 1)
              : undefined;
            return (
              <section className="stack term-page-question" key={question.question_id} aria-label={`設問${questionIndex + 1}`}>
                <p className="preserve-lines term-page-question-body">{questionBodies[questionIndex]}</p>
                {isAnswered && !reviewResult ? (
                  <div className="notice answer-locked" role="status">
                    <strong>回答済み・変更不可</strong>
                    <p>この設問の回答は保存済みです。</p>
                  </div>
                ) : !isAnswered ? <div className="selection-status">最も適切なものを1つ選んでください。</div> : null}
                {question.options.length ? (
                  <div className="options">
                    {question.options.map((option) => {
                      const selected = selectedIds.includes(option.option_id);
                      const answerClass = selected && reviewResult
                        ? optionAnswerClass(true, reviewResult.is_correct)
                        : "";
                      return (
                        <label className={`option ${isAnswered && selected && !reviewResult ? "option-selected-locked" : ""} ${option.exclusive ? "option-unknown" : ""} ${answerClass}`} key={option.option_id}>
                          <input
                            type="radio"
                            name={`option-${question.question_id}`}
                            value={option.option_id}
                            checked={selected}
                            disabled={isAnswered || saving || pageIsFrozen}
                            onChange={() => setSelectedByQuestion((previous) => ({ ...previous, [question.question_id]: [option.option_id] }))}
                          />
                          <span>
                            {selected && reviewResult ? (
                              <strong className="option-verdict">{reviewResult.is_correct ? "正解" : "不正解"}</strong>
                            ) : null}
                            <strong>{option.label}.</strong> {option.body}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                ) : null}
              </section>
            );
          })}
        </div>
        {error ? <div className="danger" role="alert">{error}</div> : null}
        <div className="actions corner-primary">
          {pendingQuestionReview?.term_slug === page.term_slug ? (
            <button type="button" onClick={continueFromQuestionReview} disabled={saving}>
              {saving ? "保存中..." : isLastPage ? "テストを完了" : "次の用語へ"}
            </button>
          ) : (
            <button type="button" onClick={submitPage} disabled={saving || (!pageAlreadySaved && !pageIsFrozen && !canAnswerAll)}>
              {saving ? "保存中..." : pageIsFrozen ? "同じ回答を再送" : pageAlreadySaved ? (isLastPage ? "完了" : "次へ") : isLastPage ? "完了" : "次へ"}
            </button>
          )}
        </div>
        {!pendingQuestionReview ? <span className="muted">このフェーズでは正誤や正解の解説は表示されません。</span> : null}
      </div>
      <GlossarySidebar key={page.key} glossary={glossary} label="テストの用語の補足" />
    </div>
  );
}
