import type { QueryClient } from "@tanstack/react-query";
import { getConversationRoom } from "../api/conversations";
import { conversationKeys } from "./queryKeys";
import type {
  ActiveGeneration,
  ConversationMessage,
  ConversationRoom,
  ConversationRoomDetail,
  ConversationRoomList,
  StreamEvent,
} from "./types";

export function seedRoomDetail(
  queryClient: QueryClient,
  room: ConversationRoom,
) {
  queryClient.setQueryData<ConversationRoomDetail>(
    conversationKeys.room(room.room_id),
    {
      room,
      message_count: 0,
      message_total: 0,
      message_page: 1,
      message_page_size: 100,
      message_pages: 0,
      message_offset: 0,
      messages: [],
    },
  );
}

export function updateRoomDetail(
  queryClient: QueryClient,
  roomId: string,
  updater: (detail: ConversationRoomDetail) => ConversationRoomDetail,
) {
  queryClient.setQueryData<ConversationRoomDetail>(
    conversationKeys.room(roomId),
    (detail) => {
      if (!detail) return detail;
      return updater(detail);
    },
  );
}

export function markGenerationInterrupted(
  queryClient: QueryClient,
  generation: ActiveGeneration,
) {
  updateRoomDetail(queryClient, generation.roomId, (detail) => ({
    ...detail,
    messages: detail.messages.map((message) =>
      message.message_id === generation.assistantMessageId ||
      message.message_id === generation.assistantTempId
        ? { ...message, status: "interrupted", error: null }
        : message,
    ),
  }));
}

export async function reconcileAfterAbort(
  queryClient: QueryClient,
  roomId: string,
) {
  await new Promise((resolve) => window.setTimeout(resolve, 250));

  try {
    const detail = await getConversationRoom(roomId);
    const latestAssistant = [...detail.messages]
      .reverse()
      .find((message) => message.role === "assistant");

    if (latestAssistant?.status !== "generating") {
      queryClient.setQueryData(conversationKeys.room(roomId), detail);
      await queryClient.invalidateQueries({ queryKey: conversationKeys.all });
    }
  } catch {
    // Keep the local interrupted state if reconciliation is temporarily unavailable.
  }
}

export function applyStreamEvent({
  queryClient,
  roomId,
  streamEvent,
  userTempId,
  assistantTempId,
  assistantMessageId,
}: {
  queryClient: QueryClient;
  roomId: string;
  streamEvent: StreamEvent;
  userTempId: string;
  assistantTempId: string;
  assistantMessageId: string;
}) {
  if (streamEvent.event === "conversation.room.updated") {
    updateRoomRecord(queryClient, streamEvent.data);
    return;
  }

  updateRoomDetail(queryClient, roomId, (detail) => {
    if (streamEvent.event === "conversation.message.created") {
      return replaceMessage(detail, userTempId, streamEvent.data);
    }

    if (streamEvent.event === "assistant.message.created") {
      return replaceMessage(detail, assistantTempId, streamEvent.data);
    }

    if (streamEvent.event === "assistant.fragment") {
      return {
        ...detail,
        messages: detail.messages.map((message) =>
          message.message_id === assistantMessageId ||
          message.message_id === assistantTempId
            ? {
                ...message,
                content: `${message.content}${streamEvent.data.text}`,
                status: "generating",
              }
            : message,
        ),
      };
    }

    if (streamEvent.event === "assistant.completed") {
      return replaceMessage(detail, assistantMessageId, streamEvent.data);
    }

    if (streamEvent.event === "assistant.error") {
      return {
        ...detail,
        messages: detail.messages.map((message) =>
          message.message_id === assistantMessageId ||
          message.message_id === assistantTempId
            ? {
                ...message,
                status: "failed",
                error: streamEvent.data.message,
              }
            : message,
        ),
      };
    }

    return detail;
  });
}

function updateRoomRecord(queryClient: QueryClient, room: ConversationRoom) {
  queryClient.setQueryData<ConversationRoomList>(
    conversationKeys.all,
    (current) =>
      current
        ? {
            ...current,
            rooms: current.rooms.map((item) =>
              item.room_id === room.room_id ? room : item,
            ),
          }
        : current,
  );
  queryClient.setQueryData<ConversationRoomDetail>(
    conversationKeys.room(room.room_id),
    (current) => (current ? { ...current, room } : current),
  );
}

export function createLocalMessage(
  roomId: string,
  messageId: string,
  role: "user" | "assistant",
  content: string,
  status: "completed" | "generating",
): ConversationMessage {
  const now = new Date().toISOString();

  return {
    message_id: messageId,
    room_id: roomId,
    role,
    content,
    status,
    error: null,
    metadata: {},
    completed_at: status === "completed" ? now : null,
    created_at: now,
    updated_at: now,
  };
}

function replaceMessage(
  detail: ConversationRoomDetail,
  messageId: string,
  replacement: ConversationMessage,
) {
  const exists = detail.messages.some(
    (message) => message.message_id === messageId,
  );
  const duplicate = detail.messages.some(
    (message) => message.message_id === replacement.message_id,
  );

  if (!exists && !duplicate) {
    return {
      ...detail,
      messages: [...detail.messages, replacement],
    };
  }

  return {
    ...detail,
    messages: detail.messages.map((message) => {
      if (message.message_id === messageId) return replacement;
      if (message.message_id === replacement.message_id) return replacement;
      return message;
    }),
  };
}
