import { useEffect, useRef } from "react";
import { BookOpen, CircleAlert, Square } from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";
import type { ConversationMessage } from "../model/types";

export function ChatThread({
  messages,
  isLoading,
  hasError,
  selectedMessageId,
  onSelectMessage,
}: {
  messages: ConversationMessage[];
  isLoading: boolean;
  hasError: boolean;
  selectedMessageId: string | null;
  onSelectMessage: (messageId: string) => void;
}) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  if (isLoading) {
    return (
      <div className="chat-thread">
        <div className="empty-chat">Loading conversation...</div>
      </div>
    );
  }

  if (hasError) {
    return (
      <div className="chat-thread">
        <div className="empty-chat">
          <CircleAlert size={28} />
          <h2>Conversation unavailable</h2>
          <p>This chat may have been deleted or the address is invalid.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-thread">
      {messages.length === 0 ? (
        <div className="empty-chat">
          <BookOpen size={28} />
          <h2>Start with a paper question.</h2>
          <p>
            Ask for a summary, compare methods, or dig into evidence from your
            indexed arXiv papers.
          </p>
        </div>
      ) : (
        messages.map((message) => (
          <ChatMessage
            key={message.message_id}
            message={message}
            selected={message.message_id === selectedMessageId}
            onSelect={() => onSelectMessage(message.message_id)}
          />
        ))
      )}
      <div ref={bottomRef} />
    </div>
  );
}

function ChatMessage({
  message,
  selected,
  onSelect,
}: {
  message: ConversationMessage;
  selected: boolean;
  onSelect: () => void;
}) {
  const isUser = message.role === "user";
  const outputLimited =
    message.metadata.output_limited === true ||
    message.metadata.usage?.completion_tokens === 1024;

  return (
    <article
      className={`message-row ${isUser ? "user" : "assistant"} ${selected ? "selected" : ""}`}
      onClick={isUser ? undefined : onSelect}
      onKeyDown={
        isUser
          ? undefined
          : (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect();
              }
            }
      }
      role={isUser ? undefined : "button"}
      tabIndex={isUser ? undefined : 0}
      aria-label={isUser ? undefined : "Inspect sources for this answer"}
    >
      <div className="message-bubble">
        {message.content ? (
          <div className="markdown-body">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[
                rehypeKatex,
                [
                  rehypeHighlight,
                  {
                    detect: true,
                    ignoreMissing: true,
                    subset: [
                      "bash",
                      "c",
                      "cpp",
                      "css",
                      "java",
                      "javascript",
                      "json",
                      "markdown",
                      "python",
                      "rust",
                      "shell",
                      "sql",
                      "typescript",
                      "yaml",
                    ],
                  },
                ],
              ]}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        ) : message.status === "generating" ? (
          <div className="typing-indicator">
            <span />
            <span />
            <span />
          </div>
        ) : null}
        {message.status === "interrupted" ? (
          <div className="message-state">
            <Square size={10} />
            Stopped
          </div>
        ) : outputLimited ? (
          <div className="message-state output-limit">
            <CircleAlert size={13} />
            Output limit reached
          </div>
        ) : null}
        {message.error ? (
          <p className="message-error">{message.error}</p>
        ) : null}
      </div>
    </article>
  );
}
