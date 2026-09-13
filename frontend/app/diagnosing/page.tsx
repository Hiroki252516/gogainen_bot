"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { CheckingFlow, useParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { postIdempotent, requireParticipant } from "@/lib/api";

const DIAGNOSING_STEPS = ["pretest"] as const;

export default function DiagnosingPage() {
  const router = useRouter();
  const [message, setMessage] = useState("回答を整理しています...");
  const flow = useParticipantFlowGuard(DIAGNOSING_STEPS);
  const flowReady = flow.ready;

  useEffect(() => {
    if (!flowReady) return;
    const participantId = requireParticipant();
    postIdempotent<{ learning_target_count: number; next_url?: string }>(
      `/api/participants/${participantId}/diagnose-pretest`,
      {},
      `diagnose_pretest:${participantId}`,
    )
      .then((data) => {
        setMessage(`${data.learning_target_count}件の重点確認項目を作成しました。`);
        setTimeout(() => router.replace("/learning-targets"), 500);
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
