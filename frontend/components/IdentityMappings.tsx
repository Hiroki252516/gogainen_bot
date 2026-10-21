"use client";

import { useState } from "react";
import { API_BASE, api } from "@/lib/api";

type Mapping = { participant_id: string; display_code: string; student_number: string; created_at: string };

export function IdentityMappings() {
  const [rows, setRows] = useState<Mapping[]>([]);
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setBusy(true); setError(""); setRows([]);
    try {
      const data = await api<{ mappings: Mapping[] }>("/api/admin/identity-mappings", { cache: "no-store" });
      setRows(data.mappings); setVisible(true);
    } catch { setError("対応表を取得できませんでした。"); }
    finally { setBusy(false); }
  }

  async function remove(row?: Mapping) {
    if (!window.confirm(row
      ? `参加者 ${row.display_code} の対応表を削除しますか？研究データは残ります。必要な対応表をUSBへ保存したことを確認してください。`
      : "アプリ内の対応表を全件削除しますか？研究データは残ります。必要な対応表をUSBへ保存したことを確認してください。")) return;
    setBusy(true); setError("");
    try {
      await api(`/api/admin/identity-mappings${row ? `/${row.participant_id}` : ""}`, { method: "DELETE" });
      // Clear identifiers immediately, even if the refresh subsequently fails.
      setRows([]);
      const data = await api<{ mappings: Mapping[] }>("/api/admin/identity-mappings", { cache: "no-store" });
      setRows(data.mappings);
    } catch { setError("対応表の操作に失敗しました。再表示して状態を確認してください。"); }
    finally { setBusy(false); }
  }

  return <section className="panel stack">
    <h2>学籍番号と参加者IDの対応表</h2>
    <p>対応表は研究データとは別に保管しています。CSVをダウンロードし、USBに保存した内容を確認してからアプリ内の対応表を削除してください。</p>
    <p className="muted">対応表の削除では研究データは削除されません。ダウンロード済みファイルやUSB内のファイルは、この画面から削除できません。</p>
    <div className="actions">
      <button type="button" className="secondary" disabled={busy} onClick={load}>対応表を表示・更新</button>
      <a className="button secondary" href={`${API_BASE}/api/admin/identity-mappings.csv`} download>対応表CSVをダウンロード</a>
      <button type="button" className="secondary" disabled={busy} onClick={() => remove()}>対応表を全件削除</button>
      {visible ? <button type="button" className="secondary" disabled={busy} onClick={() => { setRows([]); setVisible(false); }}>対応表を隠す</button> : null}
    </div>
    {error ? <p className="danger" role="alert">{error}</p> : null}
    {visible && !busy ? rows.length ? <div style={{ overflowX: "auto" }}><table>
      <thead><tr><th>学籍番号</th><th>表示コード</th><th>参加者ID</th><th>登録日時（UTC）</th><th>操作</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={row.participant_id}>
        <td>{row.student_number}</td><td>{row.display_code}</td><td>{row.participant_id}</td><td>{row.created_at}</td>
        <td><button type="button" className="secondary" onClick={() => remove(row)}>対応表を個別削除</button></td>
      </tr>)}</tbody>
    </table></div> : <p>アプリ内に対応表はありません。</p> : null}
  </section>;
}
