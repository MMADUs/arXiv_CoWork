export type MessageRole = "user" | "assistant" | "system";

export type MessageStatus =
  | "completed"
  | "generating"
  | "interrupted"
  | "failed";

export type ConversationRoom = {
  room_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
};

export type ConversationRoomList = {
  count: number;
  total: number;
  page: number;
  page_size: number;
  pages: number;
  offset: number;
  rooms: ConversationRoom[];
};

export type Citation = {
  source_number?: number;
  chunk_id?: string;
  paper_id?: string;
  arxiv_id?: string;
  title?: string;
  section_title?: string | null;
  pdf_url?: string;
  chunk_index?: number;
  score?: number | null;
  highlights?: string[];
};

export type SourceBlock = {
  paper_source_number?: number;
  paper_id?: string;
  arxiv_id?: string;
  title?: string;
  authors?: string[];
  categories?: string[];
  published_date?: string;
  pdf_url?: string;
  citation_numbers?: number[];
  highlights?: string[];
};

export type ConversationMessage = {
  message_id: string;
  room_id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  error: string | null;
  metadata: {
    citations?: Citation[];
    sources?: SourceBlock[];
    model?: string;
    provider?: string;
    output_limited?: boolean;
    usage?: {
      completion_tokens?: number;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ConversationRoomDetail = {
  room: ConversationRoom;
  message_count: number;
  message_total: number;
  message_page: number;
  message_page_size: number;
  message_pages: number;
  message_offset: number;
  messages: ConversationMessage[];
};

export type StreamEvent =
  | { event: "conversation.message.created"; data: ConversationMessage }
  | { event: "conversation.room.updated"; data: ConversationRoom }
  | { event: "assistant.message.created"; data: ConversationMessage }
  | { event: "assistant.status"; data: { text: string } }
  | { event: "assistant.fragment"; data: { text: string } }
  | { event: "assistant.completed"; data: ConversationMessage }
  | { event: "assistant.error"; data: { message: string } };

export type ActiveGeneration = {
  roomId: string;
  userTempId: string;
  assistantTempId: string;
  assistantMessageId: string;
};
