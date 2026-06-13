"use client";

import { AppShell } from "@/components/AppShell";
import { QuestionRunner } from "@/components/QuestionRunner";

export default function FinalTestPage() {
  return (
    <AppShell step="最終テスト">
      <QuestionRunner
        phase="final_test"
        title="最終テスト"
        sourcePath={(id) => `/api/experiment/${id}/final-test`}
        scorePath={(id) => `/api/participants/${id}/score-final-test`}
        nextPath="/survey"
      />
    </AppShell>
  );
}
