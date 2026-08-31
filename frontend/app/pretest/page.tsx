"use client";

import { AppShell } from "@/components/AppShell";
import { QuestionRunner } from "@/components/QuestionRunner";

export default function PretestPage() {
  return (
    <AppShell step="テスト">
      <QuestionRunner phase="pretest" title="テスト" sourcePath={(id) => `/api/experiment/${id}/pretest`} nextPath="/diagnosing" />
    </AppShell>
  );
}
