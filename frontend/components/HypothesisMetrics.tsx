import { API_BASE } from "@/lib/api";

const LABELS: Record<string, string> = {
  h1: "仮説1：初回再テストの伸び（ポイント）",
  h2: "仮説2：満点までの用語別学習セッション数",
  h3: "仮説3：一用語当たりの不正解数",
  h4: "仮説4：同種誤答の再選択率",
  h5: "仮説5：教材6項目の平均（1〜10）",
  h6: "仮説6：再テスト満点到達割合",
};
const ITEMS: Record<string, string> = {
  clarity: "内容のわかりやすさ", readability: "読みやすさ", japanese_clarity: "日本語のわかりやすさ",
  difficulty_appropriateness: "難易度の適切さ", learning_usefulness: "学習への役立ち度", amount_appropriateness: "量の適切さ",
};
const CENSORING_REASONS: Record<string, string> = {
  give_up: "途中中断", in_progress: "継続中", completed_without_mastery: "完了・満点未達", other: "終了状況不明",
};
function format(value: number | null | undefined, rate = false) {
  return value == null ? "対象データなし" : rate ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);
}
function StatsTable({ groups }: { groups: any[] }) {
  return <div style={{ overflowX: "auto" }}><table>
    <thead><tr><th>指標</th><th>群</th><th>対象人数</th><th>平均／割合</th><th>中央値</th><th>欠測・未観測</th><th>対象外</th></tr></thead>
    <tbody>{Object.entries(LABELS).flatMap(([key, label]) => groups.map((group: any) => {
      const stat = group[key];
      return <tr key={`${group.group_condition}-${key}`}><th>{label}</th><td>{group.group_condition}</td><td>{stat.n}</td>
        <td>{format(stat.mean, key === "h4" || key === "h6")}</td><td>{format(stat.median, key === "h4" || key === "h6")}</td>
        <td>{stat.missing_count}</td><td>{stat.not_applicable_count}</td></tr>;
    }))}</tbody>
  </table></div>;
}
export function HypothesisMetrics({ data }: { data: any }) {
  if (!data) return null;
  if (data.strata?.length) return <div className="stack">{data.strata.map((stratum: any) => <HypothesisMetrics key={String(stratum.first_question_only)} data={stratum} />)}</div>;
  const titleId = `hypotheses-title-${data.first_question_only ? "q1" : "q12"}`;
  return <section className="panel stack" aria-labelledby={titleId}>
    <h2 id={titleId}>6仮説の記述集計</h2>
    <p>集計対象: 通常版／{data.first_question_only ? "設問1のみ（3問）" : "設問1・2（6問）"}</p>
    <p>新プロトコル登録者のみ。統計検定・仮説支持の自動判定は行いません。欠測は補完しません。</p>
    <StatsTable groups={data.groups} />
    <p className="muted">仮説2は満点到達者のみの条件付き集計です。仮説2の未観測は満点までの総回数が未確定の人数であり、表示済みセッションの記録欠落を意味しません。仮説3は用語内平均→参加者内平均、仮説4は参加者ごとの率の平均です。</p>
    <div className="actions">
      <a className="button secondary" href={`${API_BASE}/api/admin/export/hypothesis_metrics.csv?question_set_mode=standard`}>6仮説・参加者別CSV</a>
      <a className="button secondary" href={`${API_BASE}/api/admin/export/hypothesis_metrics.xlsx?question_set_mode=standard`}>6仮説・参加者別Excel (.xlsx)</a>
      <a className="button secondary" href={`${API_BASE}/api/admin/export/hypothesis_group_summary.csv?question_set_mode=standard`}>6仮説・群別CSV</a>
      <a className="button secondary" href={`${API_BASE}/api/admin/export/hypothesis_group_summary.xlsx?question_set_mode=standard`}>6仮説・群別Excel (.xlsx)</a>
    </div>
    <h3>群間差（proposed − control）</h3>
    <ul>{Object.entries(LABELS).map(([key, label]) => {
      const difference = data.differences_proposed_minus_control[key];
      return <li key={key}>{label}：{key === "h4" || key === "h6" ? difference == null ? "対象データなし" : `${(difference * 100).toFixed(1)}ポイント` : format(difference)}</li>;
    })}</ul>
    <h3>教材評価6項目</h3>
    <div style={{ overflowX: "auto" }}><table><thead><tr><th>項目</th><th>群</th><th>回答者数</th><th>平均</th><th>中央値</th><th>閲覧者の欠測</th><th>群間差</th></tr></thead>
      <tbody>{Object.entries(ITEMS).flatMap(([key, label]) => data.groups.map((group: any) => {
        const stat = group.h5.items[key];
        return <tr key={`${key}-${group.group_condition}`}><th>{label}</th><td>{group.group_condition}</td><td>{stat.n}</td><td>{format(stat.mean)}</td><td>{format(stat.median)}</td><td>{stat.missing_count}</td><td>{format(data.material_item_differences[key])}</td></tr>;
      }))}</tbody></table></div>
    {data.groups.map((group: any) => <div className="notice" key={group.group_condition}>
      <strong>{group.group_condition}：登録 {group.participant_count}人</strong>
      <p>満点到達 {group.h6.numerator}/{group.h6.denominator}人、未達 {group.h2.not_attained_count}人、学習なし到達 {group.h2.attained_without_learning_count}人</p>
      <p>未達者の観測セッション数：n={group.h2.observed_nonattainer_sessions.n}、平均 {format(group.h2.observed_nonattainer_sessions.mean)}、中央値 {format(group.h2.observed_nonattainer_sessions.median)}</p>
      <ul>{Object.entries(CENSORING_REASONS).map(([reason, label]) => {
        const stat = group.h2.censoring_breakdown[reason];
        return <li key={reason}>{label}：{stat.n}人、観測セッション数の平均 {format(stat.mean)}、中央値 {format(stat.median)}</li>;
      })}</ul>
      <p>参考・用語件数比：{group.h4.pooled_numerator}/{group.h4.pooled_denominator}（{format(group.h4.pooled_rate, true)}）、教材表示者 {group.h5.viewed_count}人</p>
      <p>終了状況：{JSON.stringify(group.completion_reasons)}</p>
    </div>)}
    <details><summary>経路別集計（事前満点・通常学習・事前未完了）</summary>
      {Object.entries(data.routes).map(([route, groups]) => <div key={route}><h3>{route}</h3><StatsTable groups={groups as any[]} /></div>)}
    </details>
    <details><summary>再テスト回次別の参考値</summary>
      <p>後半の回次は受験者が異なります。全回をまとめた平均を主指標にはしません。</p>
      {data.groups.map((group: any) => <div key={group.group_condition}><h3>{group.group_condition}</h3>
        <ul>{group.rounds.map((round: any) => <li key={round.round}>再テスト{round.round}：伸び n={round.gain.n} 平均 {format(round.gain.mean)}／中央値 {format(round.gain.median)}／欠測 {round.gain.missing_count}、再選択率 n={round.recurrence.n} 平均 {format(round.recurrence.mean, true)}</li>)}</ul>
      </div>)}
    </details>
    <p className="muted">教材表示は読了・理解の証明ではありません。正答のデバッグ配置・管理アクセス対策は別途確認が必要です。</p>
  </section>;
}

export function ParticipantHypothesisMetrics({ data }: { data: any }) {
  if (!data) return null;
  return <section className="notice stack"><h3>参加者の6仮説対応値</h3>
    <p>出題設問：{data.first_question_only ? "設問1のみ（3問）" : "設問1・2（6問）"}</p>
    <p>経路：{data.route}／教材表示：{data.has_viewed_material ? "あり" : "なし"}</p>
    {data.h2.censoring_reason && <p>満点未達の終了状況：{CENSORING_REASONS[data.h2.censoring_reason]}</p>}
    <ul>{Object.entries(LABELS).map(([key, label]) => <li key={key}>{label}：{format(data[key].value, key === "h4" || key === "h6")}（{data[key].status || "observed"}）</li>)}</ul>
    <details><summary>分母・用語別・回次別の詳細</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>
  </section>;
}
