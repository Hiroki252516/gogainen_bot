"use client";

import Link from "next/link";
import { AppShell } from "@/components/AppShell";

export default function SurveyTransitionPage() {
  return (
    <AppShell step="アンケート">
      <section className="panel stack">
        <h1>アンケート</h1>
        <p>確認が完了しました。アンケート画面は次の実装で接続します。</p>
        <div className="actions">
          <Link className="button" href="/finish">
            完了画面へ
          </Link>
        </div>
      </section>
    </AppShell>
  );
}
