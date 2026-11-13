import { API_BASE } from "@/lib/api";

const LABELS: Record<string, string> = {
  h1: "H1：事前テストから初回再テストへの正答率の伸び（ポイント）",
  h2: "H2：同じ誤答タイプの再選択率",
  h3: "H3：再テスト満点率",
};
const ITEM_LABELS: Record<string, string> = {
  clarity: "内容理解",
  readability: "読みやすさ",
  japanese_clarity: "日本語表現",
  difficulty_appropriateness: "難易度",
  learning_usefulness: "正しい理解への役立ち度",
  amount_appropriateness: "学習時間に対する分量",
};
const H4_NUMERIC_ITEMS = ["clarity", "readability", "japanese_clarity", "learning_usefulness"];
const CENTERED_ITEMS: Record<string, string[]> = {
  difficulty_appropriateness: ["簡単すぎた", "やや簡単", "ちょうどよい", "やや難しい", "難しすぎた"],
  amount_appropriateness: ["少なすぎた", "やや少ない", "ちょうどよい", "やや多い", "多すぎた"],
};
const TEST_CONTENT_MODES: Record<string, string> = {
  application: "現行版（場面応用）",
  basic_understanding: "基礎理解版",
  four_topic_fundamentals: "4用語版",
};
const ROUTES: Record<string, string> = {
  pretest_perfect_early_exit: "事前テスト満点・早期終了",
  learning_retest: "事前テスト完了・再テスト対象",
  pretest_incomplete: "事前テスト未完了",
};

function format(value: number | null | undefined) {
  return value == null ? "対象データなし" : value.toFixed(2);
}
function formatRate(value: number | null | undefined) {
  return value == null ? "対象データなし" : `${(value * 100).toFixed(1)}%`;
}
function testCountLabel(data: any) {
  if (data.test_content_mode === "four_topic_fundamentals") return "4問・4用語";
  return data.first_question_only ? "設問1のみ（3問）" : "設問1・2（6問）";
}
function StatsTable({ groups }: { groups: any[] }) {
  return <div style={{ overflowX: "auto" }}><table>
    <thead><tr><th>仮説</th><th>群</th><th>観測人数</th><th>適用対象</th><th>平均／割合</th><th>中央値</th><th>欠測</th><th>対象外</th></tr></thead>
    <tbody>{Object.entries(LABELS).flatMap(([key, label]) => groups.map((group: any) => {
      const stat = group[key];
      const rate = key === "h2" || key === "h3";
      return <tr key={`${group.group_condition}-${key}`}><th>{label}</th><td>{group.group_condition}</td><td>{stat.n}</td>
        <td>{stat.eligible_count}</td><td>{rate ? formatRate(stat.mean) : stat.mean == null ? "対象データなし" : `${format(stat.mean)} pt`}</td>
        <td>{rate ? formatRate(stat.median) : format(stat.median)}</td><td>{stat.missing_count}</td><td>{stat.not_applicable_count}</td></tr>;
    }))}</tbody>
  </table></div>;
}

function MaterialEvaluation({ data }: { data: any }) {
  return <>
    <h3>H4：教材評価（項目別）</h3>
    <p>教材閲覧者を対象に項目ごとに集計します。4項目は数値回答の平均を示し、難易度・分量は「3＝ちょうどよい」を中央とする分布のみを示します。6項目を合成した総合点は算出しません。</p>
    <div style={{ overflowX: "auto" }}><table><thead><tr><th>項目</th><th>群</th><th>数値回答数</th><th>平均</th><th>中央値</th><th>評価できない</th><th>未回答</th><th>群間差</th></tr></thead>
      <tbody>{H4_NUMERIC_ITEMS.flatMap((key) => data.groups.map((group: any) => {
        const stat = group.h4.items[key];
        return <tr key={`${key}-${group.group_condition}`}><th>{ITEM_LABELS[key]}</th><td>{group.group_condition}</td><td>{stat.n}</td>
          <td>{format(stat.mean)}</td><td>{format(stat.median)}</td><td>{stat.not_applicable_count}</td><td>{stat.missing_count}</td>
          <td>{format(data.h4_item_differences[key])}</td></tr>;
      }))}</tbody></table></div>
    <h4>難易度・分量の回答分布</h4>
    <p>割合の分母は教材閲覧者数です。「評価できない」「未回答」は分けて表示します。未閲覧者はこの分布の分母に含めません。</p>
    <div style={{ overflowX: "auto" }}><table><thead><tr><th>項目</th><th>群</th><th>閲覧者数</th><th>回答</th><th>人数</th><th>割合</th></tr></thead>
      <tbody>{Object.entries(CENTERED_ITEMS).flatMap(([key, options]) => data.groups.flatMap((group: any) => {
        const stat = group.h4.items[key];
        const distribution = stat.distribution;
        const denominator = group.h4.viewed_count;
        const responseRows = [
          ...options.map((label, index) => [String(index + 1), label] as const),
          ["not_applicable", "評価できない"] as const,
          ["missing", "未回答"] as const,
        ];
        return responseRows.map(([value, label]) => {
          const count = distribution[value] || 0;
          return <tr key={`${key}-${group.group_condition}-${value}`}><th>{ITEM_LABELS[key]}</th><td>{group.group_condition}</td>
            <td>{denominator}</td><td>{label}</td><td>{count}</td>
            <td>{denominator ? `${(count / denominator * 100).toFixed(1)}%` : "対象データなし"}</td></tr>;
        });
      }))}</tbody></table></div>
    {data.groups.map((group: any) => <p className="muted" key={`h4-${group.group_condition}`}>
      {group.group_condition}：閲覧者 {group.h4.viewed_count}人、未閲覧 {group.h4.not_viewed_count}人、閲覧後のアンケート欠測 {group.h4.missing_survey_count}人。
    </p>)}
  </>;
}

export function HypothesisMetrics({ data }: { data: any }) {
  if (!data) return null;
  if (data.strata?.length) return <div className="stack">{data.strata.map((stratum: any) => <div className="stack" key={`${stratum.protocol_id}-${stratum.experiment_spec_version}-${stratum.test_content_mode}-${String(stratum.first_question_only)}`}>
    <p className="muted">仕様版{stratum.experiment_spec_version}／{stratum.protocol_id}／事後アンケート {stratum.survey_version || "未回答"}</p>
    <HypothesisMetrics data={stratum} />
  </div>)}</div>;
  const titleId = `hypotheses-title-${data.protocol_id || "mixed"}-${data.test_content_mode || "application"}-${data.first_question_only ? "q1" : "q12"}`;
  const modeLabel = data.test_content_mode_label || TEST_CONTENT_MODES[data.test_content_mode] || "現行版（場面応用）";
  return <section className="panel stack" aria-labelledby={titleId}>
    <h2 id={titleId}>4仮説の記述集計：{modeLabel}</h2>
    <p>集計対象: 仕様版{data.experiment_spec_version}／{data.protocol_id}／事後アンケート {data.survey_version || "回答なし"}／{modeLabel}／{testCountLabel(data)}</p>
    <p>現行仕様版と、明示的に対応付けた仕様版52の2 protocolを対象とします。旧仕様版の参加者進行は読み取り専用のままで、保存済みデータから評価サマリーのみ追加する場合があります。統計検定・仮説支持の自動判定・欠測補完は行いません。H1は事前満点者を対象外とし、その他は事前テストと初回再テストの完答ペアを集計します。H2は事前テストと初回再テストの比較可能な完答ペアを対象とし、参加者ごとの再選択割合を算出します。H3は事前テスト完了者から事前満点者を除いた再テスト対象者が分母で、未受験・中断・未達は未到達として数えます。</p>
    <StatsTable groups={data.groups} />
    <p className="muted">H2の参加者内割合は、事前テストでM1/M3だった項目のうち、初回再テストでも同じタイプを選んだ割合です。群の平均は参加者ごとの割合を等しい重みで集計します。H3の対象外には事前テスト未完了者と事前満点者を含み、人数を別掲します。</p>
    <div className="actions">
      <a className="button secondary" href={`${API_BASE}/api/admin/export/hypothesis_metrics.csv`}>4仮説・参加者別CSV</a>
      <a className="button secondary" href={`${API_BASE}/api/admin/export/hypothesis_metrics.xlsx`}>4仮説・参加者別Excel (.xlsx)</a>
      <a className="button secondary" href={`${API_BASE}/api/admin/export/hypothesis_group_summary.csv`}>4仮説・群別CSV</a>
      <a className="button secondary" href={`${API_BASE}/api/admin/export/hypothesis_group_summary.xlsx`}>4仮説・群別Excel (.xlsx)</a>
    </div>
    <h3>群間差（proposed − control）</h3>
    <ul>{Object.entries(LABELS).map(([key, label]) => {
      const difference = data.differences_proposed_minus_control[key];
      return <li key={key}>{label}：{difference == null ? "対象データなし" : key === "h1" ? `${difference.toFixed(2)} pt` : formatRate(difference)}</li>;
    })}</ul>
    <MaterialEvaluation data={data} />
    {data.groups.map((group: any) => <div className="notice" key={group.group_condition}>
      <strong>{group.group_condition}：登録 {group.participant_count}人、事前満点・早期終了 {group.pretest_perfect_early_exit_count}人、事前未完了 {group.pretest_incomplete_count}人</strong>
      <p>H2：完答ペア {group.h2.paired_complete_count}人、比較対象M1/M3項目 {group.h2.participant_denominator}件、同じタイプの再選択 {group.h2.participant_numerator}件。参考の項目加重率 {formatRate(group.h2.pooled_rate)}。</p>
      <p>H3：満点到達 {group.h3.numerator}/{group.h3.denominator}人。事前未完了 {group.h3.pretest_incomplete_count}人、事前満点・早期終了 {group.pretest_perfect_early_exit_count}人は対象外。</p>
      <p>終了状況：{JSON.stringify(group.completion_reasons)}</p>
    </div>)}
    <details><summary>経路別集計</summary>
      {Object.entries(data.routes).map(([route, groups]) => <div key={route}><h3>{ROUTES[route] || route}</h3><StatsTable groups={groups as any[]} /></div>)}
    </details>
    <details><summary>後続再テストの参考値</summary>
      <p>H1・H2の主比較は初回再テストです。後続回は受験者が異なるため、各回の参考値として分けて表示します。</p>
      {data.groups.map((group: any) => <div key={group.group_condition}><h3>{group.group_condition}</h3>
        <ul>{group.rounds.filter((round: any) => round.round > 1).map((round: any) => <li key={round.round}>
          再テスト{round.round}：正答率の伸び n={round.gain.n}／平均 {format(round.gain.mean)} pt、同タイプ再選択率 n={round.same_type_reselection.n}／平均 {formatRate(round.same_type_reselection.mean)}
        </li>)}</ul>
      </div>)}
    </details>
    <p className="muted">H4は主観評価です。教材表示・評価は読了、理解、または因果関係の証明ではありません。</p>
  </section>;
}

export function ParticipantHypothesisMetrics({ data }: { data: any }) {
  if (!data) return null;
  const modeLabel = data.test_content_mode_label || TEST_CONTENT_MODES[data.test_content_mode] || "現行版（場面応用）";
  const h4Status = data.h4.status === "observed" ? "回答あり" : data.h4.status === "missing_survey" ? "閲覧後アンケート欠測" : "教材未閲覧";
  return <section className="notice stack"><h3>参加者の4仮説対応値</h3>
    <p>テスト問題モード：{modeLabel}</p>
    <p>出題設問：{testCountLabel(data)}</p>
    <p>経路：{data.route}／教材表示：{data.has_viewed_material ? "あり" : "なし"}</p>
    <ul>
      <li>{LABELS.h1}：{data.h1.value == null ? "対象データなし" : `${format(data.h1.value)} pt`}（{data.h1.status}）</li>
      <li>{LABELS.h2}：{formatRate(data.h2.value)}（{data.h2.status}、{data.h2.numerator ?? "-"}/{data.h2.denominator ?? "-"}）</li>
      <li>{LABELS.h3}：{data.h3.value == null ? "対象外" : data.h3.value ? "満点到達" : "未到達"}（{data.h3.status}）</li>
      <li>H4：教材評価・{h4Status}</li>
    </ul>
    {data.h4.items && <ul>{Object.entries(ITEM_LABELS).map(([key, label]) => <li key={key}>{label}：{data.h4.items[key] ?? "未回答"}</li>)}</ul>}
    <details><summary>分母・項目・回次別の詳細</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>
  </section>;
}
