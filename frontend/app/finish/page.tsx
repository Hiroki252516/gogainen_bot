"use client";

import Link from "next/link";
import { AppShell } from "@/components/AppShell";

export default function FinishPage() {
  const displayCode = typeof window !== "undefined" ? localStorage.getItem("display_code") : "";
  return (
    <AppShell step="終了">
      <section className="panel stack">
        <h1>実験は終了です</h1>
        <p>ご協力ありがとうございました。研究者に終了したことを知らせてください。</p>
        <p className="muted">被験者ID: {displayCode}</p>
        <Link className="button secondary" href="/admin">
          管理画面へ
        </Link>
      </section>
    </AppShell>
  );
}
