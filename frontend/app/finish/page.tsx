"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { clearParticipantSession } from "@/lib/api";

const FINISH_STEPS = ["finish"] as const;

export default function FinishPage() {
  const router = useRouter();
  const displayCode = typeof window !== "undefined" ? localStorage.getItem("display_code") : "";

  function startNewExperiment() {
    if (!window.confirm("現在の参加者情報をこのブラウザから消去して、新しい実験を開始します。よろしいですか？")) return;
    clearParticipantSession();
    router.replace("/start");
  }

  return (
    <ParticipantFlowGuard allowedSteps={FINISH_STEPS}>
      <AppShell step="終了">
        <section className="panel stack">
          <h1>実験は終了です</h1>
          <p>ご協力ありがとうございました。研究者に終了したことを知らせてください。</p>
          <p className="muted">被験者ID: {displayCode}</p>
          <button className="secondary" type="button" onClick={startNewExperiment}>
            新しい実験を開始
          </button>
          <Link className="button secondary" href="/admin">
            管理画面へ
          </Link>
        </section>
      </AppShell>
    </ParticipantFlowGuard>
  );
}
