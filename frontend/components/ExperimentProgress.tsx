"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, participantId } from "@/lib/api";

type Progress = {
  stage_id: string;
  label: string;
  percent: number;
};

type CurrentStepResponse = {
  progress: Progress | null;
};

type ProgressState = {
  pathname: string;
  progress: Progress | null;
  error: boolean;
};

const PARTICIPANT_PATHS = new Set([
  "/pretest",
  "/diagnosing",
  "/learning-targets",
  "/retest",
  "/final-test",
  "/survey",
  "/finish",
]);

function supportsProgress(pathname: string) {
  return PARTICIPANT_PATHS.has(pathname) || pathname.startsWith("/learning/");
}

export function ExperimentProgress() {
  const pathname = usePathname();
  const [retryCount, setRetryCount] = useState(0);
  const [state, setState] = useState<ProgressState | null>(null);

  useEffect(() => {
    if (!supportsProgress(pathname)) return;
    const id = participantId();
    if (!id) {
      setState({ pathname, progress: null, error: false });
      return;
    }

    let active = true;
    api<CurrentStepResponse>(`/api/participants/${id}/current-step`, { cache: "no-store" })
      .then((data) => {
        if (active) setState({ pathname, progress: data.progress, error: false });
      })
      .catch(() => {
        if (active) setState({ pathname, progress: null, error: true });
      });

    return () => {
      active = false;
    };
  }, [pathname, retryCount]);

  if (!supportsProgress(pathname)) return null;
  if (!state || state.pathname !== pathname) {
    return <div className="experiment-progress-loading" role="status">実験の進捗を確認しています...</div>;
  }
  if (state.error) {
    return (
      <div className="experiment-progress-error" role="status">
        <span>実験の進捗を取得できませんでした。</span>
        <button type="button" className="secondary" onClick={() => setRetryCount((count) => count + 1)}>
          再取得
        </button>
      </div>
    );
  }
  if (!state.progress) return null;

  const label = pathname === "/learning-targets" ? "テストの結果確認" : state.progress.label;
  return (
    <section className="experiment-progress" aria-label="実験全体の進捗">
      <div className="experiment-progress-heading">
        <span>{label}</span>
        <strong>{state.progress.percent}％</strong>
      </div>
      <progress
        max={100}
        value={state.progress.percent}
        aria-label={`実験全体の進捗：${label}`}
      />
      {state.progress.percent === 100 ? (
        <small className="muted">100％は実験手続きの完了を示し、テストの満点到達を示すものではありません。</small>
      ) : null}
    </section>
  );
}
