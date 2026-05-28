"use client";

import { AppShell } from "@/components/AppShell";
import { QuestionRunner } from "@/components/QuestionRunner";

export default function TransferTestPage() {
  return (
    <AppShell step="転移テスト">
      <QuestionRunner
        phase="transfer"
        title="転移テスト"
        sourcePath={(id) => `/api/experiment/${id}/transfer-test`}
        scorePath={(id) => `/api/participants/${id}/score-transfer-test`}
        nextPath="/survey/post"
      />
    </AppShell>
  );
}
