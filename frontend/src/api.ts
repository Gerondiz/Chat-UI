import type {
  ProviderConfig,
  ProviderStatus,
  Collection,
  CollectionDoc,
  Workspace,
  ChatMessage,
  ChatOptions,
  ChatSettings,
  Source,
  SSEData,
  Metrics,
  TokenCallback,
  ThinkingCallback,
  DoneCallback,
  ErrorCallback,
  AbortFn,
} from './types'

const API = 'http://localhost:8000/api'

export async function getProviders(): Promise<{ providers: string[] }> {
  const r = await fetch(`${API}/providers`)
  return r.json()
}

export async function getProvider(): Promise<ProviderConfig> {
  const r = await fetch(`${API}/provider`)
  return r.json()
}

export async function switchProvider(name: string): Promise<ProviderConfig> {
  const r = await fetch(`${API}/provider`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  return r.json()
}

export async function updateProviderConfig(cfg: Partial<ProviderConfig>): Promise<ProviderConfig> {
  const r = await fetch(`${API}/provider/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
  return r.json()
}

export async function getProviderStatus(): Promise<ProviderStatus> {
  const r = await fetch(`${API}/provider/status`)
  return r.json()
}

export async function getProviderModels(): Promise<{ chat_models: string[]; embedding_models: string[] }> {
  const r = await fetch(`${API}/provider/models`)
  return r.json()
}

export async function chat(
  messages: ChatMessage[],
  opts: Partial<ChatOptions> = {},
  settings?: Partial<ChatSettings>,
): Promise<{ role: string; content: string; thinking?: string; sources?: Source[] }> {
  const r = await fetch(`${API}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages,
      system_prompt: settings?.systemPrompt || opts.systemPrompt || '',
      mode: opts.mode || 'chat',
      collection: opts.collection || '',
      temperature: opts.temperature ?? 0.7,
      max_tokens: opts.maxTokens ?? 4096,
      top_p: opts.topP ?? 0.9,
      reasoning: opts.reasoning ?? true,
      stream: false,
    }),
  })
  if (!r.ok) throw new Error((await r.json()).detail)
  return r.json()
}

export function chatStream(
  messages: ChatMessage[],
  opts: Partial<ChatOptions> & { settings?: Partial<ChatSettings> },
  onToken?: TokenCallback,
  onThinking?: ThinkingCallback,
  onDone?: DoneCallback,
  onError?: ErrorCallback,
): AbortFn {
  const controller = new AbortController()

  const body = {
    messages,
    system_prompt: opts.settings?.systemPrompt || opts.systemPrompt || '',
    mode: opts.mode || 'chat',
    collection: opts.collection || '',
    temperature: opts.temperature ?? 0.7,
    max_tokens: opts.maxTokens ?? 4096,
    top_p: opts.topP ?? 0.9,
    reasoning: opts.reasoning ?? true,
    stream: true,
  }

  fetch(`${API}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: controller.signal,
  }).then(async (r) => {
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }))
      onError?.(err.detail)
      return
    }
    const reader = r.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let raw = ''
    let inThink = false
    let isFirstContent = true

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data: SSEData = JSON.parse(line.slice(6))
            if (data.done) {
              onDone?.(data.full || '', data.thinking || '', data.sources || [], data.metrics || null)
            } else {
              const token = data.token || ''
              if (!token) continue
              raw += token

              let remaining = token
              while (remaining.length > 0) {
                if (inThink) {
                  const endIdx = remaining.indexOf('</think>')
                  if (endIdx >= 0) {
                    const thinkText = remaining.slice(0, endIdx)
                    if (thinkText) onThinking?.(thinkText, false)
                    onThinking?.('', true)
                    remaining = remaining.slice(endIdx + 8)
                    inThink = false
                    isFirstContent = true
                  } else {
                    onThinking?.(remaining, false)
                    remaining = ''
                  }
                } else {
                  const startIdx = remaining.indexOf('<think')
                  if (startIdx >= 0) {
                    const before = remaining.slice(0, startIdx)
                    if (before) onToken?.(before)
                    remaining = remaining.slice(startIdx)
                    inThink = true
                    const endIdx = remaining.indexOf('</think>')
                    if (endIdx >= 0) {
                      const thinkText = remaining.slice(6, endIdx)
                      if (thinkText) onThinking?.(thinkText, false)
                      onThinking?.('', true)
                      remaining = remaining.slice(endIdx + 8)
                      inThink = false
                      isFirstContent = true
                    } else {
                      const thinkText = remaining.slice(6)
                      if (thinkText) onThinking?.(thinkText, false)
                      remaining = ''
                    }
                  } else {
                    onToken?.(remaining)
                    remaining = ''
                  }
                }
              }
            }
          } catch (_) { /* ignore parse errors */ }
        }
      }
    }
  }).catch((err: Error) => {
    if (err.name !== 'AbortError') onError?.(err.message)
  })

  return () => controller.abort()
}

export async function getCollections(): Promise<{ collections: Collection[]; error?: string }> {
  const r = await fetch(`${API}/collections`)
  return r.json()
}

export async function createCollection(name: string): Promise<{ status: string; name: string }> {
  const r = await fetch(`${API}/collections?name=${encodeURIComponent(name)}`, {
    method: 'POST',
  })
  if (!r.ok) throw new Error((await r.json()).detail)
  return r.json()
}

export async function deleteCollection(name: string): Promise<{ status: string; name: string }> {
  const r = await fetch(`${API}/collections/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  if (!r.ok) throw new Error((await r.json()).detail)
  return r.json()
}

export async function getCollectionDocuments(name: string): Promise<{ documents: CollectionDoc[]; error?: string }> {
  const r = await fetch(`${API}/collections/${encodeURIComponent(name)}/documents`)
  return r.json()
}

export async function uploadDocument(name: string, file: File): Promise<{ status: string; chunks?: number }> {
  const form = new FormData()
  form.append('file', file)
  const r = await fetch(`${API}/collections/${encodeURIComponent(name)}/documents`, {
    method: 'POST',
    body: form,
  })
  if (!r.ok) throw new Error((await r.json()).detail)
  return r.json()
}

export async function getWorkspaces(): Promise<{ workspaces: Workspace[] }> {
  const r = await fetch(`${API}/workspaces`)
  return r.json()
}

export async function createWorkspace(data: Partial<Workspace>): Promise<Workspace> {
  const r = await fetch(`${API}/workspaces`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return r.json()
}

export async function updateWorkspace(id: number, data: Partial<Workspace>): Promise<Workspace> {
  const r = await fetch(`${API}/workspaces/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return r.json()
}

export async function deleteWorkspace(id: number): Promise<{ status: string }> {
  const r = await fetch(`${API}/workspaces/${id}`, {
    method: 'DELETE',
  })
  return r.json()
}
