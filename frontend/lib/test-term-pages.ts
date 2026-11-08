import type { Glossary } from "@/components/LearningGlossary";

export type TestQuestionForPage = {
  question_id: string;
  term_slug: string;
  term_label: string;
  test_round?: string | null;
  answer_status?: "unanswered" | "submitted";
  submitted_answer?: { selected_option_ids?: string[] | null } | null;
  glossary?: Glossary | null;
};

export type TestTermPage<T extends TestQuestionForPage> = {
  key: string;
  term_slug: string;
  term_label: string;
  test_round: string | null;
  questions: T[];
};

export function normalizeTestRound(value: string | null | undefined): string {
  return value ?? "";
}

export function sameTestRound(left: string | null | undefined, right: string | null | undefined): boolean {
  return normalizeTestRound(left) === normalizeTestRound(right);
}

export function groupTestQuestionsByTerm<T extends TestQuestionForPage>(
  questions: T[] | null | undefined,
): TestTermPage<T>[] | null {
  if (!questions?.length) return null;
  const groups = new Map<string, T[]>();
  for (const question of questions) {
    const group = groups.get(question.term_slug) ?? [];
    group.push(question);
    groups.set(question.term_slug, group);
  }
  const pages: TestTermPage<T>[] = [];
  for (const [term_slug, group] of groups) {
    if (![1, 2].includes(group.length) || group.length !== groups.values().next().value?.length || group.some((question) => question.test_round !== questions[0].test_round)) return null;
    pages.push({
      key: `${term_slug}:${group[0].test_round ?? ""}`,
      term_slug,
      term_label: group[0].term_label,
      test_round: group[0].test_round ?? null,
      questions: group,
    });
  }
  return [3, 4].includes(pages.length) ? pages : null;
}

export function combineTestGlossaries(questions: TestQuestionForPage[]): Glossary | null {
  const source = questions.map((question) => question.glossary).find((glossary) => glossary?.entries.length);
  if (!source) return null;
  const entries: Glossary["entries"] = [];
  const seen = new Set<string>();
  for (const question of questions) {
    for (const entry of question.glossary?.entries ?? []) {
      const key = JSON.stringify([entry.id, entry.term, entry.definition]);
      if (seen.has(key)) continue;
      seen.add(key);
      entries.push(entry);
    }
  }
  return { version: source.version, entries };
}

export function initialTestTermPageIndex<T extends TestQuestionForPage>(pages: TestTermPage<T>[]): number {
  const firstIncomplete = pages.findIndex((page) => page.questions.some((question) => question.answer_status !== "submitted"));
  return firstIncomplete >= 0 ? firstIncomplete : Math.max(0, pages.length - 1);
}
