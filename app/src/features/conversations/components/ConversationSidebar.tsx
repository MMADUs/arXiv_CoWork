import { useState } from "react";
import type { FormEvent } from "react";
import { Check, MoreHorizontal, Pencil, Plus, Trash2, X } from "lucide-react";
import { Link } from "react-router-dom";
import type { ConversationRoom } from "../model/types";

export function ConversationSidebar({
  activeRoomId,
  rooms,
  loading,
  onNewChat,
  onDeleteRoom,
  onRenameRoom,
  onSelectRoom,
  onClose,
}: {
  activeRoomId: string | null;
  rooms: ConversationRoom[];
  loading: boolean;
  onNewChat: () => void;
  onDeleteRoom: (roomId: string) => void;
  onRenameRoom: (roomId: string, title: string) => Promise<unknown>;
  onSelectRoom: (roomId: string) => void;
  onClose: () => void;
}) {
  const [menuRoomId, setMenuRoomId] = useState<string | null>(null);
  const [editingRoomId, setEditingRoomId] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);

  function startRename(room: ConversationRoom) {
    setEditingRoomId(room.room_id);
    setTitleDraft(room.title || "");
    setRenameError(null);
    setMenuRoomId(null);
  }

  async function submitRename(event: FormEvent, roomId: string) {
    event.preventDefault();
    const title = titleDraft.trim();
    if (!title) return;

    try {
      await onRenameRoom(roomId, title);
      setEditingRoomId(null);
      setRenameError(null);
    } catch (error) {
      setRenameError(
        error instanceof Error
          ? error.message
          : "Could not rename conversation.",
      );
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <Link className="sidebar-brand-link" to="/home" aria-label="Open home">
          <div className="brand-mark">
            <span>arXiv</span>
          </div>
          <div>
            <strong>Co-work</strong>
            <span>Research assistant</span>
          </div>
        </Link>
        <button
          className="icon-button drawer-close"
          type="button"
          onClick={onClose}
          aria-label="Close conversations"
        >
          <X size={18} />
        </button>
      </div>

      <button className="new-chat-button" type="button" onClick={onNewChat}>
        <Plus size={16} />
        New chat
      </button>

      <div className="sidebar-section-label">
        <span>Recent</span>
        <span>{rooms.length}</span>
      </div>

      <div className="room-list">
        {loading ? (
          <div className="empty-state">Loading rooms...</div>
        ) : rooms.length === 0 ? (
          <div className="empty-state">No conversations yet.</div>
        ) : (
          rooms.map((room) => (
            <div
              className={`room-item ${room.room_id === activeRoomId ? "active" : ""} ${menuRoomId === room.room_id ? "menu-open" : ""}`}
              key={room.room_id}
            >
              {editingRoomId === room.room_id ? (
                <form
                  className="room-rename-form"
                  onSubmit={(event) => submitRename(event, room.room_id)}
                >
                  <input
                    autoFocus
                    value={titleDraft}
                    onChange={(event) => {
                      setTitleDraft(event.target.value);
                      setRenameError(null);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Escape") {
                        setEditingRoomId(null);
                        setRenameError(null);
                      }
                    }}
                    maxLength={256}
                    aria-label="Conversation title"
                  />
                  <button
                    type="submit"
                    disabled={!titleDraft.trim()}
                    aria-label="Save title"
                    title="Save"
                  >
                    <Check size={15} />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setEditingRoomId(null);
                      setRenameError(null);
                    }}
                    aria-label="Cancel rename"
                    title="Cancel"
                  >
                    <X size={15} />
                  </button>
                  {renameError ? (
                    <span className="room-rename-error">{renameError}</span>
                  ) : null}
                </form>
              ) : (
                <>
                  <button
                    className="room-select-button"
                    type="button"
                    onClick={() => {
                      setMenuRoomId(null);
                      onSelectRoom(room.room_id);
                    }}
                  >
                    <strong>{room.title || "Untitled research thread"}</strong>
                    <span>{formatDate(room.updated_at)}</span>
                  </button>
                  <div className="room-menu-container">
                    <button
                      className="room-menu-button"
                      type="button"
                      aria-label={`Options for ${room.title || "conversation"}`}
                      aria-expanded={menuRoomId === room.room_id}
                      title="Conversation options"
                      onClick={() =>
                        setMenuRoomId((current) =>
                          current === room.room_id ? null : room.room_id,
                        )
                      }
                    >
                      <MoreHorizontal size={16} />
                    </button>
                    {menuRoomId === room.room_id ? (
                      <div className="room-menu" role="menu">
                        <button
                          type="button"
                          role="menuitem"
                          onClick={() => startRename(room)}
                        >
                          <Pencil size={14} />
                          Rename
                        </button>
                        <button
                          className="danger"
                          type="button"
                          role="menuitem"
                          onClick={() => {
                            setMenuRoomId(null);
                            onDeleteRoom(room.room_id);
                          }}
                        >
                          <Trash2 size={14} />
                          Delete
                        </button>
                      </div>
                    ) : null}
                  </div>
                </>
              )}
            </div>
          ))
        )}
      </div>
    </aside>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}
