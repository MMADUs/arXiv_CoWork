import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createConversationRoom,
  deleteConversationRoom,
  getConversationRoom,
  listConversationRooms,
  sendConversationMessage,
  updateConversationRoom,
} from "../api/conversations";
import {
  applyStreamEvent,
  createLocalMessage,
  markGenerationInterrupted,
  reconcileAfterAbort,
  seedRoomDetail,
  updateRoomDetail,
} from "../model/conversationCache";
import { conversationKeys } from "../model/queryKeys";
import type {
  ActiveGeneration,
  ConversationMessage,
  ConversationRoom,
  ConversationRoomDetail,
  ConversationRoomList,
} from "../model/types";

const emptyRooms: ConversationRoom[] = [];
const emptyMessages: ConversationMessage[] = [];

export function useConversationChat({
  roomId,
  onRoomCreated,
  onRoomDeleted,
}: {
  roomId: string | null;
  onRoomCreated: (roomId: string) => void;
  onRoomDeleted: () => void;
}) {
  const queryClient = useQueryClient();
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(
    null,
  );
  const [draft, setDraft] = useState("");
  const [composerError, setComposerError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const activeGenerationRef = useRef<ActiveGeneration | null>(null);

  const roomsQuery = useQuery({
    queryKey: conversationKeys.all,
    queryFn: listConversationRooms,
  });

  const roomQuery = useQuery({
    queryKey: roomId
      ? conversationKeys.room(roomId)
      : conversationKeys.emptyRoom,
    queryFn: () => getConversationRoom(roomId as string),
    enabled: Boolean(roomId),
  });

  const rooms = roomsQuery.data?.rooms ?? emptyRooms;
  const messages = roomQuery.data?.messages ?? emptyMessages;
  const selectedMessage = useMemo(() => {
    if (selectedMessageId) {
      const selected = messages.find(
        (message) => message.message_id === selectedMessageId,
      );
      if (selected) return selected;
    }

    return (
      [...messages].reverse().find((message) => message.role === "assistant") ??
      null
    );
  }, [messages, selectedMessageId]);

  const deleteRoomMutation = useMutation({
    mutationFn: deleteConversationRoom,
    onSuccess: async (_, deletedRoomId) => {
      queryClient.removeQueries({
        queryKey: conversationKeys.room(deletedRoomId),
      });
      await queryClient.invalidateQueries({ queryKey: conversationKeys.all });

      if (roomId === deletedRoomId) {
        setSelectedMessageId(null);
        onRoomDeleted();
      }
    },
  });

  const renameRoomMutation = useMutation({
    mutationFn: updateConversationRoom,
    onSuccess: (updatedRoom) => {
      queryClient.setQueryData<ConversationRoomList>(
        conversationKeys.all,
        (current) =>
          current
            ? {
                ...current,
                rooms: current.rooms.map((room) =>
                  room.room_id === updatedRoom.room_id ? updatedRoom : room,
                ),
              }
            : current,
      );
      queryClient.setQueryData<ConversationRoomDetail>(
        conversationKeys.room(updatedRoom.room_id),
        (current) => (current ? { ...current, room: updatedRoom } : current),
      );
    },
  });

  const sendMessageMutation = useMutation({
    mutationFn: async (content: string) => {
      let targetRoomId = roomId;

      if (!targetRoomId) {
        const room = await createConversationRoom(null);
        targetRoomId = room.room_id;
        seedRoomDetail(queryClient, room);
        onRoomCreated(targetRoomId);
        await queryClient.invalidateQueries({ queryKey: conversationKeys.all });
      }

      const userTempId = `temp-user-${Date.now()}`;
      const assistantTempId = `temp-assistant-${Date.now()}`;
      let assistantMessageId = assistantTempId;
      const controller = new AbortController();
      abortControllerRef.current = controller;
      activeGenerationRef.current = {
        roomId: targetRoomId,
        userTempId,
        assistantTempId,
        assistantMessageId,
      };

      updateRoomDetail(queryClient, targetRoomId, (detail) => ({
        ...detail,
        messages: [
          ...detail.messages,
          createLocalMessage(
            targetRoomId,
            userTempId,
            "user",
            content,
            "completed",
          ),
          createLocalMessage(
            targetRoomId,
            assistantTempId,
            "assistant",
            "",
            "generating",
          ),
        ],
      }));
      setSelectedMessageId(assistantTempId);

      await sendConversationMessage({
        roomId: targetRoomId,
        content,
        signal: controller.signal,
        onEvent: (streamEvent) => {
          if (streamEvent.event === "assistant.message.created") {
            assistantMessageId = streamEvent.data.message_id;
            if (
              activeGenerationRef.current?.assistantTempId === assistantTempId
            ) {
              activeGenerationRef.current.assistantMessageId =
                assistantMessageId;
            }
            setSelectedMessageId(assistantMessageId);
          }

          applyStreamEvent({
            queryClient,
            roomId: targetRoomId,
            streamEvent,
            userTempId,
            assistantTempId,
            assistantMessageId,
          });
        },
      });

      abortControllerRef.current = null;
      activeGenerationRef.current = null;
      await queryClient.invalidateQueries({
        queryKey: conversationKeys.room(targetRoomId),
      });
      await queryClient.invalidateQueries({ queryKey: conversationKeys.all });
    },
    onError: (error, content) => {
      abortControllerRef.current = null;
      const generation = activeGenerationRef.current;
      activeGenerationRef.current = null;

      if (isAbortError(error)) {
        if (generation) {
          markGenerationInterrupted(queryClient, generation);
          void reconcileAfterAbort(queryClient, generation.roomId);
        }
        return;
      }

      const message =
        error instanceof Error ? error.message : "Message failed.";
      setComposerError(message);
      setDraft((current) => current || content);
      const targetRoomId = generation?.roomId ?? roomId;
      if (!targetRoomId) return;

      updateRoomDetail(queryClient, targetRoomId, (detail) => ({
        ...detail,
        messages: detail.messages.map((item, index, list) => {
          const isTarget = generation
            ? item.message_id === generation.assistantMessageId ||
              item.message_id === generation.assistantTempId
            : item.role === "assistant" &&
              index ===
                list.findLastIndex(
                  (candidate) => candidate.role === "assistant",
                );

          return isTarget
            ? { ...item, status: "failed", error: message }
            : item;
        }),
      }));
    },
  });

  function sendMessage(content: string) {
    if (!content.trim() || sendMessageMutation.isPending) return;
    setComposerError(null);
    setDraft("");
    sendMessageMutation.mutate(content.trim());
  }

  function stopGeneration() {
    const generation = activeGenerationRef.current;
    if (generation) {
      markGenerationInterrupted(queryClient, generation);
    }
    abortControllerRef.current?.abort();
  }

  function updateDraft(value: string) {
    setDraft(value);
    setComposerError(null);
  }

  return {
    rooms,
    roomsLoading: roomsQuery.isLoading,
    activeRoom: roomQuery.data?.room ?? null,
    roomLoading: roomQuery.isLoading,
    roomError: roomQuery.isError,
    messages,
    selectedMessage,
    selectedMessageId: selectedMessage?.message_id ?? null,
    setSelectedMessageId,
    draft,
    updateDraft,
    composerError,
    isGenerating: sendMessageMutation.isPending,
    sendMessage,
    stopGeneration,
    deleteRoom: deleteRoomMutation.mutate,
    renameRoom: (roomId: string, title: string) =>
      renameRoomMutation.mutateAsync({ roomId, title: title.trim() }),
  };
}

function isAbortError(error: unknown) {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    error.name === "AbortError"
  );
}
