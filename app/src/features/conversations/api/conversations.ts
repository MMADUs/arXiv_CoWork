import type {
  ConversationRoom,
  ConversationRoomDetail,
  ConversationRoomList,
  StreamEvent,
} from "../model/types";
import { api } from "../../../shared/api/client";

export async function listConversationRooms() {
  const response = await api.get<ConversationRoomList>("/conversation-rooms");
  return response.data;
}

export async function createConversationRoom(title?: string | null) {
  const response = await api.post<ConversationRoom>("/conversation-rooms", {
    title: title ?? null,
  });
  return response.data;
}

export async function getConversationRoom(roomId: string) {
  const response = await api.get<ConversationRoomDetail>(
    `/conversation-rooms/${roomId}`,
  );
  return response.data;
}

export async function deleteConversationRoom(roomId: string) {
  await api.delete(`/conversation-rooms/${roomId}`);
}

export async function updateConversationRoom({
  roomId,
  title,
}: {
  roomId: string;
  title: string;
}) {
  const response = await api.patch<ConversationRoom>(
    `/conversation-rooms/${roomId}`,
    {
      title,
    },
  );
  return response.data;
}

export async function sendConversationMessage({
  roomId,
  content,
  metadata = {},
  signal,
  onEvent,
}: {
  roomId: string;
  content: string;
  metadata?: Record<string, unknown>;
  signal?: AbortSignal;
  onEvent: (event: StreamEvent) => void;
}) {
  const response = await fetch(`/api/conversation-rooms/${roomId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ content, metadata }),
    signal,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }

  if (!response.body) {
    throw new Error("The browser did not expose a response stream.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const event = parseSseBlock(part);
        if (event) onEvent(event);
      }
    }

    buffer += decoder.decode();
    const finalEvent = parseSseBlock(buffer);
    if (finalEvent) onEvent(finalEvent);
  } finally {
    reader.releaseLock();
  }
}

function parseSseBlock(block: string): StreamEvent | null {
  const lines = block.split(/\r?\n/);
  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    }

    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  if (dataLines.length === 0) return null;

  let data: unknown;

  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    data = dataLines.join("\n");
  }

  switch (event) {
    case "conversation.message.created":
    case "conversation.room.updated":
    case "assistant.message.created":
    case "assistant.status":
    case "assistant.fragment":
    case "assistant.completed":
    case "assistant.error":
      return { event, data } as StreamEvent;
    default:
      return null;
  }
}
