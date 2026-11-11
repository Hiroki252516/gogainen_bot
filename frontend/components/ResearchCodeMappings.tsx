"use client";

import { useState } from "react";
import { API_BASE, api } from "@/lib/api";

type Mapping = { participant_id: string; display_code: string; research_code: string; created_at: string };

export function ResearchCodeMappings() {
  const [rows, setRows] = useState<Mapping[]>([]);
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setBusy(true); setError(""); setRows([]);
    try {
      const data = await api<{ mappings: Mapping[] }>("/api/admin/research-code-mappings", { cache: "no-store" });
      setRows(data.mappings); setVisible(true);
    } catch { setError("研究用コード対応表を取得できませんでした。"); }
    finally { setBusy(false); }
  }

  async function remove(row?: Mapping) {
    if (!window.confirm(row
      ? `参加者 ${row.display_code} の研究用コード対応表を削除しますか？研究データは残ります。必要な対応表を安全な場所へ保存したことを確認してください。`
      : "アプリ内の研究用コード対応表を全件削除しますか？研究データは残ります。必要な対応表を安全な場所へ保存したことを確認してください。")) return;
    setBusy(true); setError("");
    try {
      await api(`/api/admin/research-code-mappings${row ? `/${row.participant_id}` : ""}`, { method: "DELETE" });
      setRows([]);
      const data = await api<{ mappings: Mapping[] }>("/api/admin/research-code-mappings", { cache: "no-store" });
      setRows(data.mappings);
    } catch { setError("対応表の操作に失敗しました。再表示して状態を確認してください。"); }
    finally { setBusy(false); }
  }

  return <section className="panel stack">
    <h2>研究用コードと参加者IDの対応表</h2>
    <p>研究用コード対応表は研究データとは別に保管しています。撤回対応に必要な場合のみ表示し、CSVを安全な場所へ保存した後、保管方針に従ってアプリ内の対応表を削除してください。</p>
    <p className="muted">対応表の削除では研究データは削除されません。ダウンロード済みファイルや外部保存先のファイルは、この画面から削除できません。</p>
    <div className="actions">
      <button type="button" className="secondary" disabled={busy} onClick={load}>研究用コード対応表を表示・更新</button>
      <a className="button secondary" href={`${API_BASE}/api/admin/research-code-mappings.csv`} download>研究用コード対応表CSVをダウンロード</a>
      <button type="button" className="secondary" disabled={busy} onClick={() => remove()}>研究用コード対応表を全件削除</button>
      {visible ? <button type="button" className="secondary" disabled={busy} onClick={() => { setRows([]); setVisible(false); }}>対応表を隠す</button> : null}
    </div>
    {error ? <p className="danger" role="alert">{error}</p> : null}
    {visible && !busy ? rows.length ? <div style={{ overflowX: "auto" }}><table>
      <thead><tr><th>研究用コード</th><th>表示コード</th><th>参加者ID</th><th>登録日時（UTC）</th><th>操作</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={row.participant_id}>
        <td>{row.research_code}</td><td>{row.display_code}</td><td>{row.participant_id}</td><td>{row.created_at}</td>
        <td><button type="button" className="secondary" disabled={busy} onClick={() => remove(row)}>対応表を個別削除</button></td>
      </tr>)}</tbody>
    </table></div> : <p>アプリ内に研究用コード対応表はありません。</p> : null}
  </section>;
}
