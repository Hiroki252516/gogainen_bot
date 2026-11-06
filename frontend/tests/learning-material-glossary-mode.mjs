import assert from "node:assert/strict";
import fs from "node:fs";

const admin = fs.readFileSync(new URL("../app/admin/page.tsx", import.meta.url), "utf8");
for (const expected of [
  '教材内解説</p>',
  '新規参加者には教材内解説を適用します。',
  'learning_material_glossary_mode: "教材の用語解説モード"',
  '教材の用語解説モード: {materialGlossaryModeLabel(participantLog.participant.learning_material_glossary_mode)}',
]) {
  assert(admin.includes(expected), `admin glossary mode contract missing: ${expected}`);
}
assert(!admin.includes("/api/admin/learning-material-glossary-mode"), "admin must not expose a glossary mode setting API");
assert(!admin.includes('["annotation_only", "注釈欄のみ"]'), "admin must not offer the annotation-only mode");
assert(admin.includes('mode === "annotation_only"\n  ? "注釈欄のみ"'), "admin must retain labels for historical participant logs");

const material = fs.readFileSync(new URL("../app/learning/[termSlug]/page.tsx", import.meta.url), "utf8");
assert(material.includes('{turn.show_material_glossary !== false ? <GlossarySidebar glossary={turn.glossary} label="教材の用語の補足" /> : null}'));
assert(material.includes('glossary={feedback.glossary}'));
assert(material.includes('glossary={turn.glossary}'));
console.log("learning material glossary mode display contract passed");
