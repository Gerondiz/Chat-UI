export interface Source {
  content: string
  filename: string
  chunk?: number
}

export interface ChatMessage {
  role: string
  content: string
}

export interface ChatOptions {
  systemPrompt?: string
  mode?: string
  collection?: string
  temperature?: number
  maxTokens?: number
  topP?: number
  reasoning?: boolean
}

export interface ProviderConfig {
  name: string
  chat_model: string
  embedding_model: string
  base_url: string
  api_key?: string
}

export interface ProviderStatus {
  name: string
  online: boolean
  chat_model: string
  embedding_model: string
  chat_models: string[]
  embedding_models: string[]
  error?: string
}

export interface Collection {
  name: string
  count: number
}

export interface CollectionDoc {
  filename: string
}

export interface Workspace {
  id: number
  name: string
  provider: string
  chat_model: string
  embedding_model: string
  system_prompt: string
  temperature: number
  max_tokens: number
  top_p: number
  context_length: number
  collections: string[]
}

export interface Metrics {
  time_sec: number
  tokens: number
  output_time_sec: number
  output_tokens: number
  tokens_per_sec: number
  input_tokens?: number
  reasoning_tokens?: number
  lm_tokens_per_sec?: number
  ttft?: number
}

export interface SSEData {
  token?: string
  done?: boolean
  full?: string
  thinking?: string
  sources?: Source[]
  metrics?: Metrics
}

export interface UserMessage {
  role: 'user'
  content: string
  id: string
  ts: number
}

export interface AssistantMessage {
  role: 'assistant'
  content: string
  thinking?: string
  metrics?: Metrics | null
  id: string
  ts: number
}

export type Message = UserMessage | AssistantMessage

export interface EditInfo {
  msgId: string
  text: string
}

export interface ChatSettings {
  systemPrompt: string
  temperature: number
  maxTokens: number
  topP: number
  contextLength: number
}

export interface ChatSummary {
  id: number
  title: string
  message_count: number
  created_at: string
  updated_at: string
}

export type TokenCallback = (token: string) => void
export type ThinkingCallback = (thinking: string, isEnd: boolean) => void
export type DoneCallback = (full: string, thinking: string, sources: Source[], metrics: Metrics | null) => void
export type ErrorCallback = (err: string) => void
export type AbortFn = () => void
