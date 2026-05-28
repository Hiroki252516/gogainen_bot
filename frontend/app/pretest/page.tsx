"use client";

import { AppShell } from "@/components/AppShell";
import { QuestionRunner } from "@/components/QuestionRunner";

export default function PretestPage() {
  return (
    <AppShell step="事前テスト">
      <QuestionRunner phase="pretest" title="事前テスト" sourcePath={(id) => `/api/experiment/${id}/pretest`} nextPath="/diagnosing" />
    </AppShell>
  );
}
