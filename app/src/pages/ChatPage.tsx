import { useState } from "react";
import { Menu, Moon, PanelRight, Sun } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { ChatThread } from "../features/conversations/components/ChatThread";
import { ConversationSidebar } from "../features/conversations/components/ConversationSidebar";
import { MessageComposer } from "../features/conversations/components/MessageComposer";
import { SourcePanel } from "../features/conversations/components/SourcePanel";
import { useConversationChat } from "../features/conversations/hooks/useConversationChat";
import { useTheme } from "../shared/theme/useTheme";

export function ChatPage() {
  const navigate = useNavigate();
  const { roomId = null } = useParams<{ roomId: string }>();
  const { theme, toggleTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sourcePanelOpen, setSourcePanelOpen] = useState(false);
  const conversation = useConversationChat({
    roomId,
    onRoomCreated: (createdRoomId) =>
      navigate(`/chat/${createdRoomId}`, { replace: true }),
    onRoomDeleted: () => navigate("/chat", { replace: true }),
  });

  function selectRoom(selectedRoomId: string) {
    conversation.setSelectedMessageId(null);
    setSidebarOpen(false);
    navigate(`/chat/${selectedRoomId}`);
  }

  function startNewChat() {
    conversation.setSelectedMessageId(null);
    setSidebarOpen(false);
    navigate("/chat");
  }

  return (
    <main
      className={`app-shell ${sidebarOpen ? "sidebar-open" : ""} ${sourcePanelOpen ? "sources-open" : ""}`}
    >
      {(sidebarOpen || sourcePanelOpen) && (
        <button
          className="drawer-scrim"
          type="button"
          aria-label="Close panel"
          onClick={() => {
            setSidebarOpen(false);
            setSourcePanelOpen(false);
          }}
        />
      )}

      <ConversationSidebar
        activeRoomId={roomId}
        rooms={conversation.rooms}
        loading={conversation.roomsLoading}
        onNewChat={startNewChat}
        onDeleteRoom={conversation.deleteRoom}
        onRenameRoom={conversation.renameRoom}
        onSelectRoom={selectRoom}
        onClose={() => setSidebarOpen(false)}
      />

      <section className="chat-column">
        <header className="topbar">
          <div className="topbar-title">
            <button
              className="icon-button mobile-panel-button"
              type="button"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open conversations"
              title="Open conversations"
            >
              <Menu size={18} />
            </button>
            <div>
              <p className="eyebrow">arXiv co-work</p>
              <h1>
                {conversation.activeRoom?.title || "New research conversation"}
              </h1>
            </div>
          </div>
          <div className="topbar-actions">
            <button
              className="icon-button source-toggle"
              type="button"
              onClick={() => setSourcePanelOpen(true)}
              aria-label="Open sources"
              title="Open sources"
            >
              <PanelRight size={18} />
            </button>
            <button
              className="icon-button"
              type="button"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
        </header>

        <ChatThread
          messages={conversation.messages}
          isLoading={conversation.roomLoading}
          hasError={conversation.roomError}
          selectedMessageId={conversation.selectedMessageId}
          onSelectMessage={conversation.setSelectedMessageId}
        />

        <MessageComposer
          draft={conversation.draft}
          error={conversation.composerError}
          isGenerating={conversation.isGenerating}
          onDraftChange={conversation.updateDraft}
          onSend={conversation.sendMessage}
          onStop={conversation.stopGeneration}
        />
      </section>

      <SourcePanel
        message={conversation.selectedMessage}
        onClose={() => setSourcePanelOpen(false)}
      />
    </main>
  );
}
