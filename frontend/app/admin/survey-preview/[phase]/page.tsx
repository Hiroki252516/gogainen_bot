"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import {
  FOUR_TOPIC_PRESURVEY_TERM_ITEMS,
  PosttestQuestionnaire,
  PresurveyQuestionnaire,
} from "@/components/SurveyForms";

async function ignorePreviewSubmission() {}

export default function AdminSurveyPreviewPage() {
  const { phase } = useParams<{ phase: string }>();
  const isPresurvey = phase === "presurvey";
  const isPosttest = phase === "posttest";

  return <AppShell step="管理画面">
    <div className="stack admin-content">
      <section className="panel stack">
        <h1>アンケートデバッグ</h1>
        <p>プレビュー専用画面です。入力と必須チェックを試せますが、回答は保存されません。</p>
        <div className="actions">
          <Link className="button secondary" href="/admin">管理画面へ戻る</Link>
          <Link className="button secondary" href="/admin/survey-preview/presurvey" aria-current={isPresurvey ? "page" : undefined}>事前アンケート</Link>
          <Link className="button secondary" href="/admin/survey-preview/posttest" aria-current={isPosttest ? "page" : undefined}>事後アンケート</Link>
        </div>
      </section>
      {isPresurvey ? <PresurveyQuestionnaire
        surveyVersion="presurvey-four-topic-baseline-v3"
        termItems={FOUR_TOPIC_PRESURVEY_TERM_ITEMS}
        preview
        onSubmit={ignorePreviewSubmission}
      /> : isPosttest ? <PosttestQuestionnaire
        materialRatingsRequired
        preview
        onSubmit={ignorePreviewSubmission}
      /> : <section className="panel stack">
        <h2>プレビューを選択してください</h2>
      </section>}
    </div>
  </AppShell>;
}
