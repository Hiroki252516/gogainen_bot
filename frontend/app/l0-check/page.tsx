"use client";

import { AppShell } from "@/components/AppShell";
import { QuestionRunner } from "@/components/QuestionRunner";

export default function ConfirmationCheckPage() {
  return (
    <AppShell step="確認テスト">
      <QuestionRunner
        phase="l0_check"
        title="確認テスト"
        sourcePath={(id) => `/api/experiment/${id}/l0-check`}
        scorePath={(id) => `/api/participants/${id}/score-l0-check`}
        nextPath="/finish"
      />
    </AppShell>
  );
}
