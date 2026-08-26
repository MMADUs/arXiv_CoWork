export const conversationKeys = {
  all: ["conversationRooms"] as const,
  room: (roomId: string) => ["conversationRoom", roomId] as const,
  emptyRoom: ["conversationRoom"] as const,
};
