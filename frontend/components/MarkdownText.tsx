import ReactMarkdown from "react-markdown";

const allowedElements = ["h1", "h2", "h3", "h4", "p", "ul", "li", "strong", "em", "a", "br"];

type MarkdownTextProps = {
  children: string;
  className?: string;
};

export function MarkdownText({ children, className }: MarkdownTextProps) {
  const classes = ["markdown-body", className].filter(Boolean).join(" ");

  return (
    <div className={classes}>
      <ReactMarkdown
        skipHtml
        allowedElements={allowedElements}
        unwrapDisallowed
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
