"use client";

import { AppShell } from "@/components/AppShell";
import { QuestionRunner } from "@/components/QuestionRunner";

export default function RetestPage() {
  return (
    <AppShell step="再テスト">
      <QuestionRunner
        phase="retest"
        title="再テスト"
        sourcePath={(id) => `/api/experiment/${id}/retest`}
        scorePath={(id) => `/api/participants/${id}/score-retest`}
        nextPath="/final-test"
        collectReason={false}
      />
    </AppShell>
  );
}
