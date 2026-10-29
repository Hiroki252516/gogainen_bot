"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { CheckingFlow, useParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { api, postIdempotent, requireParticipant } from "@/lib/api";
import { saveLearningTargets } from "@/lib/learning-targets";

const DIAGNOSING_STEPS = ["pretest"] as const;

export default function DiagnosingPage() {
  const router = useRouter();
  const [message, setMessage] = useState("回答を整理しています...");
  const flow = useParticipantFlowGuard(DIAGNOSING_STEPS);
  const flowReady = flow.ready;

  useEffect(() => {
    if (!flowReady) return;
    const participantId = requireParticipant();
    postIdempotent<{ learning_target_count: number; learning_target_slugs?: string[]; next_url?: string; review_required?: boolean }>(
      `/api/participants/${participantId}/diagnose-pretest`,
      {},
      `diagnose_pretest:${participantId}`,
    )
      .then(async (data) => {
        let targets = data.learning_target_slugs;
        if (!targets && data.review_required === false) {
          const current = await api<{ targets: { term_slug: string }[] }>(`/api/participants/${participantId}/learning-targets`);
          targets = current.targets.map((target) => target.term_slug);
        }
        if (targets) saveLearningTargets(participantId, targets);
        setMessage(`${data.learning_target_count}件の重点確認項目を作成しました。`);
        setTimeout(() => router.replace(data.review_required === false ? (data.next_url || "/learning-targets") : "/learning-targets"), 500);
      })
      .catch((err) => setMessage(err.message));
  }, [flowReady, router]);

  if (!flowReady) return <CheckingFlow error={flow.error} onRetry={flow.retry} />;

  return (
    <AppShell step="診断">
      <section className="panel stack">
        <h1>診断中</h1>
        <p>{message}</p>
      </section>
    </AppShell>
  );
}
