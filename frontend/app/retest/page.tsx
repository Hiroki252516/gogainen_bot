"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { QuestionRunner } from "@/components/QuestionRunner";

const retestSourcePath = (id: string) => `/api/experiment/${id}/retest`;
const retestScorePath = (id: string) => `/api/participants/${id}/score-retest`;

export default function RetestPage() {
  const [roundTitle, setRoundTitle] = useState("再テスト1");

  return (
    <AppShell step={roundTitle}>
      <QuestionRunner
        phase="retest"
        title="再テスト1"
        sourcePath={retestSourcePath}
        scorePath={retestScorePath}
        nextPath="/learning-targets"
        onDisplayTitle={setRoundTitle}
      />
    </AppShell>
  );
}
