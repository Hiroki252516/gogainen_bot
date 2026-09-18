"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { GiveUpButton } from "@/components/GiveUpButton";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { api, participantId } from "@/lib/api";

const LEARNING_TARGETS_STEPS = ["learning_targets"] as const;

const toFullWidthDigits = (value: number) =>
  String(value).replace(/\d/g, (digit) => String.fromCharCode(digit.charCodeAt(0) + 0xfee0));

type Target = { term_slug: string; term_label: string; summary_for_learner: string; current_stage_for_display: string };
type PretestResult = {
  term_slug: string;
  term_label: string;
  is_correct: boolean | null;
  result_label: string;
  result_summary: string;
  is_learning_target: boolean;
};
type TestResult = {
  term_slug: string;
  term_label: string;
  question_body: string | null;
  selected_options: { label: string; body: string }[];
  is_correct: boolean | null;
  result_label: string;
  is_learning_target: boolean;
};
type TestResults = {
  test_round: string | null;
  test_round_label: string | null;
  results: TestResult[];
};
type LearningTargetsResponse = {
  current_step: string;
  targets: Target[];
  pretest_results: PretestResult[];
  test_results: TestResults;
};

export default function LearningTargetsPage() {
  const [currentStep, setCurrentStep] = useState("");
  const [targets, setTargets] = useState<Target[]>([]);
  const [pretestResults, setPretestResults] = useState<PretestResult[]>([]);
  const [testResults, setTestResults] = useState<TestResults>({ test_round: null, test_round_label: null, results: [] });
  const [error, setError] = useState("");
  const isRetestResult = testResults.test_round?.startsWith("retest_") ?? false;

  useEffect(() => {
    const id = participantId();
    if (!id) return;
    api<LearningTargetsResponse>(`/api/participants/${id}/learning-targets`)
      .then((data) => {
        setCurrentStep(data.current_step);
        setTargets(data.targets);
        setPretestResults(data.pretest_results);
        setTestResults(data.test_results || { test_round: null, test_round_label: null, results: [] });
        localStorage.setItem("learning_targets", JSON.stringify(data.targets.map((t) => t.term_slug)));
      })
      .catch((err) => setError(err.message));
  }, []);

  return (
    <ParticipantFlowGuard allowedSteps={LEARNING_TARGETS_STEPS}>
      <AppShell step="学習対象">
        <section className="panel stack">
        <h1>{testResults.test_round_label ? `${testResults.test_round_label}の確認結果` : "今回の確認結果"}</h1>
        {error ? <div className="danger">{error}</div> : null}
        <div className="stack">
          {testResults.results.length ? testResults.results.map((result, i) => (
            <div
              className={`notice pretest-result ${result.is_correct === true ? "pretest-result-correct" : result.is_correct === false ? "pretest-result-incorrect" : "pretest-result-pending"}`}
              key={result.term_slug}
            >
              <div className="term-row-head">
                <span className="question-heading">
                  問{toFullWidthDigits(i + 1)}：<strong>{result.term_label}</strong>
                </span>
                <span className="status-pill">{result.result_label}</span>
              </div>
              <p>{result.question_body || "問題文を確認できません。"}</p>
              <div className="result-detail">
                <strong>自分が選んだ選択肢</strong>
                {result.selected_options.length ? (
                  <ul>
                    {result.selected_options.map((option) => (
                      <li key={`${result.term_slug}-${option.label}-${option.body}`}>
                        <strong>{option.label}.</strong> {option.body}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>未回答</p>
                )}
              </div>
              <p className="result-verdict">
                {result.is_correct === true ? "この問題は正解です。" : result.is_correct === false ? "この問題は不正解です。" : "この問題は未回答です。"}
              </p>
            </div>
          )) : pretestResults.map((result, i) => (
            <div className={`notice pretest-result ${result.is_correct === true ? "pretest-result-correct" : "pretest-result-incorrect"}`} key={result.term_slug}>
              <div className="term-row-head">
                <span className="question-heading">
                  問{toFullWidthDigits(i + 1)}：<strong>{result.term_label}</strong>
                </span>
                <span className="status-pill">{result.result_label}</span>
              </div>
              <p className="result-verdict">{result.result_summary}</p>
            </div>
          ))}
        </div>
        {currentStep === "learning_targets" && targets[0] ? (
          <Link className="button" href={`/learning/${targets[0].term_slug}`}>
            学習を開始
          </Link>
        ) : (
          <span className="muted">学習対象を確認しています。</span>
        )}
        {isRetestResult && currentStep !== "finish" ? (
          <div className="give-up-footer">
            <GiveUpButton mode="experiment" />
          </div>
        ) : null}
        </section>
      </AppShell>
    </ParticipantFlowGuard>
  );
}
