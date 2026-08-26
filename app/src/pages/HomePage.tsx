import { ArrowRight, MessageSquareText, Moon, Plus, Sun } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listConversationRooms } from "../features/conversations/api/conversations";
import { conversationKeys } from "../features/conversations/model/queryKeys";
import { useTheme } from "../shared/theme/useTheme";

export function HomePage() {
  const { theme, toggleTheme } = useTheme();
  const roomsQuery = useQuery({
    queryKey: conversationKeys.all,
    queryFn: listConversationRooms,
  });
  const rooms = roomsQuery.data?.rooms ?? [];

  return (
    <main className="home-page">
      <header className="home-header">
        <Link className="home-brand" to="/home">
          <span className="brand-mark">arXiv</span>
          <span>Co-work</span>
        </Link>
        <nav className="home-nav" aria-label="Primary navigation">
          <Link to="/chat">Chat</Link>
          <button
            className="icon-button"
            type="button"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </nav>
      </header>

      <section className="home-content">
        <div className="home-intro">
          <p className="eyebrow">Research workspace</p>
          <h1>Continue your work</h1>
          <p>
            Start a focused conversation or return to a recent research thread.
          </p>
          <Link className="home-primary-action" to="/chat">
            <Plus size={17} />
            New conversation
          </Link>
        </div>

        <section className="recent-section" aria-labelledby="recent-heading">
          <div className="recent-heading-row">
            <div>
              <p className="eyebrow">Workspace</p>
              <h2 id="recent-heading">Recent conversations</h2>
            </div>
            <Link to="/chat">
              Open chat
              <ArrowRight size={15} />
            </Link>
          </div>

          <div className="home-room-list">
            {roomsQuery.isLoading ? (
              <p className="home-empty">Loading conversations...</p>
            ) : rooms.length === 0 ? (
              <div className="home-empty">
                <MessageSquareText size={22} />
                <p>Your recent conversations will appear here.</p>
              </div>
            ) : (
              rooms.slice(0, 6).map((room) => (
                <Link
                  className="home-room-row"
                  to={`/chat/${room.room_id}`}
                  key={room.room_id}
                >
                  <div>
                    <strong>{room.title || "Untitled research thread"}</strong>
                    <span>{formatDate(room.updated_at)}</span>
                  </div>
                  <ArrowRight size={16} />
                </Link>
              ))
            )}
          </div>
        </section>
      </section>
    </main>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}
