"use client";

import { AppShell } from "@/components/AppShell";
import { QuestionRunner } from "@/components/QuestionRunner";

export default function L0CheckPage() {
  return (
    <AppShell step="L0確認">
      <QuestionRunner
        phase="l0_check"
        title="ヒントなし確認"
        sourcePath={(id) => `/api/experiment/${id}/l0-check`}
        scorePath={(id) => `/api/participants/${id}/score-l0-check`}
        nextPath="/transfer-test"
      />
    </AppShell>
  );
}
