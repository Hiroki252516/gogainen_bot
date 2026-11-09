export function optionAnswerClass(answered: boolean, isCorrect: boolean | undefined): string {
  if (!answered) return "";
  return isCorrect ? "option-answer-correct" : "option-answer-incorrect";
}

export function optionCorrectnessForReview(
  selectionMode: "multiple" | "single",
  selectedOptionIsCorrect: boolean | undefined,
  questionIsCorrect: boolean,
): boolean {
  if (selectionMode === "multiple" && typeof selectedOptionIsCorrect === "boolean") {
    return selectedOptionIsCorrect;
  }
  return questionIsCorrect;
}
