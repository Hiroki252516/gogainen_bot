export function saveLearningTargets(participantId: string, slugs: string[], preserveExisting = false) {
  if (preserveExisting && localStorage.getItem("learning_targets_participant_id") === participantId) {
    try {
      const previous: unknown = JSON.parse(localStorage.getItem("learning_targets") || "null");
      if (Array.isArray(previous) && previous.every((slug) => typeof slug === "string")
        && slugs.every((slug) => previous.includes(slug))) return;
    } catch {
      // Replace a damaged cache with the server's current list.
    }
  }
  localStorage.setItem("learning_targets", JSON.stringify(slugs));
  localStorage.setItem("learning_targets_participant_id", participantId);
}
