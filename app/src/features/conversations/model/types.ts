export type MessageRole = "user" | "assistant" | "system";

export type MessageStatus =
  | "completed"
  | "generating"
  | "interrupted"
  | "failed";

export type RetrievalMode = "bm25" | "vector" | "hybrid";

export type RetrievalConfig = {
  retrieval_mode: RetrievalMode;
  top_k: number;
  candidate_pool_size: number;
  use_reranker: boolean;
  include_highlights: boolean;
  latest_first: boolean;
};

export type MessageRetrievalFilters = {
  paper_id?: string;
  categories?: string[];
  published_from?: string;
  published_to?: string;
};

export type MessageRetrievalFilterDraft = {
  paper_id: string;
  categories: string;
  published_from: string;
  published_to: string;
};

export type ConversationRoom = {
  room_id: string;
  title: string | null;
  metadata: {
    total_input_tokens?: number;
    total_output_tokens?: number;
    total_tokens?: number;
    min_latency_ms?: number | null;
    max_latency_ms?: number | null;
    avg_latency_ms?: number | null;
    [key: string]: unknown;
  };
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
  citation_index?: number;
  document_id?: string;
  document_version?: string | null;
  chunk_id?: string;
  paper_id?: string;
  arxiv_id?: string;
  title?: string;
  page?: number | null;
  section_title?: string | null;
  pdf_url?: string;
  chunk_index?: number;
  score?: number | null;
  source_storage_key?: string | null;
  start_char?: number | null;
  end_char?: number | null;
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

export type SourceChunk = {
  source_number?: number | null;
  chunk_id: string;
  paper_id: string;
  section_title?: string | null;
  chunk_index: number;
  score?: number | null;
  highlights: string[];
  text: string;
  word_count: number;
  start_word: number;
  end_word: number;
  start_char: number;
  end_char: number;
};

export type SourceChunksResponse = {
  paper: SourceBlock;
  chunks: SourceChunk[];
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
    reasoning_status?: string;
    output_limited?: boolean;
    input_tokens?: number;
    output_tokens?: number;
    total_tokens?: number;
    latency_ms?: number | null;
    prefill_duration_ms?: number | null;
    decode_duration_ms?: number | null;
    model_load_duration_ms?: number | null;
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
