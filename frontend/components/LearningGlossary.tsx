export type Glossary = {
  version: string;
  entries: { id: string; term: string; definition: string }[];
};

export function LearningGlossary({ glossary, label }: { glossary?: Glossary | null; label: string }) {
  if (!glossary?.entries.length) return null;

  return (
    <aside className="learning-glossary" aria-label={label}>
      <h3>用語の補足</h3>
      <dl>
        {glossary.entries.map((entry) => (
          <div key={entry.id}>
            <dt>{entry.term}</dt>
            <dd>{entry.definition}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}
