"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { api, requireParticipant } from "@/lib/api";

type Target = { term_slug: string; term_label: string; summary_for_learner: string; current_stage_for_display: string };
type PretestResult = {
  term_slug: string;
  term_label: string;
  is_correct: boolean | null;
  result_label: string;
  result_summary: string;
  is_learning_target: boolean;
};
type LearningTargetsResponse = {
  current_step: string;
  targets: Target[];
  pretest_results: PretestResult[];
};

export default function LearningTargetsPage() {
  const [currentStep, setCurrentStep] = useState("");
  const [targets, setTargets] = useState<Target[]>([]);
  const [pretestResults, setPretestResults] = useState<PretestResult[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<LearningTargetsResponse>(`/api/participants/${requireParticipant()}/learning-targets`)
      .then((data) => {
        setCurrentStep(data.current_step);
        setTargets(data.targets);
        setPretestResults(data.pretest_results);
        localStorage.setItem("learning_targets", JSON.stringify(data.targets.map((t) => t.term_slug)));
      })
      .catch((err) => setError(err.message));
  }, []);

  return (
    <AppShell step="学習対象">
      <section className="panel stack">
        <h1>今回の確認結果</h1>
        {error ? <div className="danger">{error}</div> : null}
        <div className="stack">
          {pretestResults.map((result, i) => (
            <div className={`notice pretest-result ${result.is_correct ? "pretest-result-correct" : "pretest-result-incorrect"}`} key={result.term_slug}>
              <div className="term-row-head">
                <strong>{i + 1}. {result.term_label}</strong>
                <span className="status-pill">{result.result_label}</span>
              </div>
              <p>{result.result_summary}</p>
              {result.is_learning_target ? (
                <>
                  <span className="muted">この用語を学習します。</span>
                  {(() => {
                    const target = targets.find((item) => item.term_slug === result.term_slug);
                    return target ? <span className="muted">学習段階: {target.current_stage_for_display}</span> : null;
                  })()}
                </>
              ) : (
                <span className="muted">この用語は今回の学習対象ではありません。</span>
              )}
            </div>
          ))}
        </div>
        {currentStep === "learning_targets" && targets[0] ? (
          <Link className="button" href={`/learning/${targets[0].term_slug}`}>
            学習を開始
          </Link>
        ) : currentStep === "final_test" ? (
          <Link className="button" href="/final-test">
            再テスト1へ
          </Link>
        ) : (
          <span className="muted">学習対象を確認しています。</span>
        )}
      </section>
    </AppShell>
  );
}
