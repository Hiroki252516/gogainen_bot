"use client";

import { AppShell } from "@/components/AppShell";
import { QuestionRunner } from "@/components/QuestionRunner";

export default function RetestPage() {
  return (
    <AppShell step="即時再テスト">
      <QuestionRunner
        phase="retest"
        title="即時再テスト"
        sourcePath={(id) => `/api/experiment/${id}/retest`}
        scorePath={(id) => `/api/participants/${id}/score-retest`}
        nextPath="/survey/post"
        collectReason={false}
      />
    </AppShell>
  );
}
