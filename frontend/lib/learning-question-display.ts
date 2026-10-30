type QuestionBody = { body: string };

type ParsedQuestionBody = {
  scenario: string;
  question: string;
  number: number;
};

export type GroupedQuestionDisplay = {
  sharedScenario: string | null;
  questionBodies: string[];
};

function parseQuestionBody(body: string): ParsedQuestionBody | null {
  const match = body.match(/^([\s\S]+?)\n\n設問([12])：([\s\S]+)$/);
  if (!match || !match[1].trim() || !match[3].trim()) return null;

  return {
    scenario: match[1],
    question: `設問${match[2]}：${match[3]}`,
    number: Number(match[2]),
  };
}

export function prepareGroupedQuestionDisplay(questions: QuestionBody[] | null | undefined): GroupedQuestionDisplay | null {
  if (!questions) return null;
  const questionBodies = questions.map((question) => question.body);
  if (questions.length !== 2) return { sharedScenario: null, questionBodies };

  const parsed = questions.map((question) => parseQuestionBody(question.body));
  if (
    parsed.some((question) => question === null)
    || parsed[0]!.scenario !== parsed[1]!.scenario
    || new Set(parsed.map((question) => question!.number)).size !== 2
  ) {
    return { sharedScenario: null, questionBodies };
  }

  return {
    sharedScenario: parsed[0]!.scenario,
    questionBodies: parsed.map((question) => question!.question),
  };
}
