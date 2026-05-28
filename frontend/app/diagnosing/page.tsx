"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, requireParticipant } from "@/lib/api";

export default function DiagnosingPage() {
  const router = useRouter();
  const [message, setMessage] = useState("回答を整理しています...");

  useEffect(() => {
    api<{ learning_target_count: number }>(`/api/participants/${requireParticipant()}/diagnose-pretest`, { method: "POST" })
      .then((data) => {
        setMessage(`${data.learning_target_count}件の重点確認項目を作成しました。`);
        setTimeout(() => router.push("/learning-targets"), 500);
      })
      .catch((err) => setMessage(err.message));
  }, [router]);

  return (
    <AppShell step="診断">
      <section className="panel stack">
        <h1>診断中</h1>
        <p>{message}</p>
      </section>
    </AppShell>
  );
}
