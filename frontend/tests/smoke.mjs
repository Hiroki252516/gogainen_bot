import fs from "node:fs";

const required = [
  "app/start/page.tsx",
  "app/pretest/page.tsx",
  "app/learning/[termSlug]/page.tsx",
  "app/admin/page.tsx",
  "components/QuestionRunner.tsx"
];

for (const file of required) {
  if (!fs.existsSync(new URL(`../${file}`, import.meta.url))) {
    throw new Error(`missing ${file}`);
  }
}

console.log("frontend smoke ok");
