"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { api, requireParticipant } from "@/lib/api";

type Target = { term_slug: string; term_label: string; summary_for_learner: string; current_scaffolding_level_for_display: string };

export default function LearningTargetsPage() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ targets: Target[] }>(`/api/participants/${requireParticipant()}/learning-targets`)
      .then((data) => {
        setTargets(data.targets);
        localStorage.setItem("learning_targets", JSON.stringify(data.targets.map((t) => t.term_slug)));
      })
      .catch((err) => setError(err.message));
  }, []);

  return (
    <AppShell step="学習対象">
      <section className="panel stack">
        <h1>今回重点的に確認する内容</h1>
        {error ? <div className="danger">{error}</div> : null}
        <div className="stack">
          {targets.map((target, i) => (
            <div className="notice" key={target.term_slug}>
              <strong>
                {i + 1}. {target.term_label}
              </strong>
              <p>{target.summary_for_learner}</p>
              <span className="muted">{target.current_scaffolding_level_for_display}</span>
            </div>
          ))}
        </div>
        {targets[0] ? (
          <Link className="button" href={`/learning/${targets[0].term_slug}`}>
            学習を開始
          </Link>
        ) : (
          <span>対象を読み込み中...</span>
        )}
      </section>
    </AppShell>
  );
}
