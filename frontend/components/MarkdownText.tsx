import ReactMarkdown from "react-markdown";

const allowedElements = ["p", "strong", "em", "ul", "ol", "li", "h2", "h3", "br", "a"];

export function MarkdownText({ content }: { content?: string | null }) {
  if (!content) return null;

  return (
    <div className="markdown-text">
      <ReactMarkdown allowedElements={allowedElements} unwrapDisallowed>
        {content}
      </ReactMarkdown>
    </div>
  );
}
