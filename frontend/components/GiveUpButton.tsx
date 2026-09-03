"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, requireParticipant } from "@/lib/api";

type GiveUpButtonProps = {
  mode: "learning" | "experiment";
  disabled?: boolean;
};

type GiveUpResponse = {
  next_url?: string;
};

export function GiveUpButton({ mode, disabled = false }: GiveUpButtonProps) {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const isLearning = mode === "learning";

  async function giveUp() {
    if (disabled || saving) return;
    const message = isLearning
      ? "学習セッションを終了して再テストへ進みます。よろしいですか？"
      : "実験をここで終了します。以後の問題には戻れません。よろしいですか？";
    if (!window.confirm(message)) return;

    setSaving(true);
    setError("");
    try {
      const participantId = requireParticipant();
      const result = await api<GiveUpResponse>(
        isLearning
          ? `/api/participants/${participantId}/give-up-learning`
          : `/api/participants/${participantId}/give-up`,
        { method: "POST" },
      );
      router.push(result.next_url || (isLearning ? "/retest" : "/finish"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  return (
    <div className="give-up-control">
      <button type="button" className="danger-button" onClick={giveUp} disabled={disabled || saving}>
        {saving ? "終了処理中..." : isLearning ? "学習をギブアップして再テストへ" : "実験をギブアップして終了"}
      </button>
      {error ? <span className="danger" role="alert">{error}</span> : null}
    </div>
  );
}
