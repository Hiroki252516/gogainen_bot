import assert from "node:assert/strict";
import fs from "node:fs";

const admin = fs.readFileSync(new URL("../app/admin/page.tsx", import.meta.url), "utf8");
assert(!admin.includes("教材の用語解説モード"), "admin must not show the fixed glossary mode");
assert(!admin.includes("learning_material_glossary_mode"), "admin page must not display glossary mode snapshots");
assert(!admin.includes("/api/admin/learning-material-glossary-mode"), "admin must not expose a glossary mode setting API");
assert(!admin.includes('["annotation_only", "注釈欄のみ"]'), "admin must not offer the annotation-only mode");

const material = fs.readFileSync(new URL("../app/learning/[termSlug]/page.tsx", import.meta.url), "utf8");
assert(material.includes('{turn.show_material_glossary !== false ? <GlossarySidebar glossary={turn.glossary} label="教材の用語の補足" /> : null}'));
assert(material.includes('glossary={feedback.glossary}'));
assert(material.includes('glossary={turn.glossary}'));
console.log("learning material glossary mode display contract passed");
