export function optionAnswerClass(answered: boolean, isCorrect: boolean | undefined): string {
  if (!answered) return "";
  return isCorrect ? "option-answer-correct" : "option-answer-incorrect";
}
