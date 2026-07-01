"use client";

import { AppShell } from "@/components/AppShell";
import { QuestionRunner } from "@/components/QuestionRunner";

export default function InitialTestPage() {
  return (
    <AppShell step="初期テスト">
      <QuestionRunner
        phase="initial_test"
        title="初期テスト"
        sourcePath={(id) => `/api/experiment/${id}/initial-test`}
        nextPath="/diagnosing"
        collectReason={false}
      />
    </AppShell>
  );
}
