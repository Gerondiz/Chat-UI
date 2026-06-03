// const API = '/api'  // через Vite proxy (нестабильно)
const API = 'http://localhost:8000/api'  // напрямую к бэкенду

export async function getProviders() {
  const r = await fetch(`${API}/providers`)
  return r.json()
}

export async function getProvider() {
  const r = await fetch(`${API}/provider`)
  return r.json()
}

export async function switchProvider(name) {
  const r = await fetch(`${API}/provider`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  return r.json()
}

export async function updateProviderConfig(cfg) {
  const r = await fetch(`${API}/provider/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  })
  return r.json()
}

export async function getProviderStatus() {
  const r = await fetch(`${API}/provider/status`)
  return r.json()
}

export async function getProviderModels() {
  const r = await fetch(`${API}/provider/models`)
  return r.json()
}

export async function chat(messages, opts = {}) {
  const r = await fetch(`${API}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages,
      system_prompt: opts.systemPrompt || '',
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

export function chatStream(messages, opts = {}, onToken, onThinking, onDone, onError) {
  const controller = new AbortController()

  fetch(`${API}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages,
      system_prompt: opts.systemPrompt || '',
      mode: opts.mode || 'chat',
      collection: opts.collection || '',
      temperature: opts.temperature ?? 0.7,
      max_tokens: opts.maxTokens ?? 4096,
      top_p: opts.topP ?? 0.9,
      reasoning: opts.reasoning ?? true,
      stream: true,
    }),
    signal: controller.signal,
  }).then(async (r) => {
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }))
      onError?.(err.detail)
      return
    }
    const reader = r.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let raw = ''
    let inThink = false
    let isFirstContent = true

    const flushThinking = () => {
      const parts = raw.split(/(<think[\s\S]*?<\/think>)/)
      for (const part of parts) {
        if (!part) continue
        if (part.startsWith('<think')) {
          const content = part.replace(/<\/?think[^>]*>/g, '')
          inThink = true
          onThinking?.(content, false)
        } else if (inThink) {
          inThink = false
          // flush remaining thinking
        }
      }
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.done) {
              onDone?.(data.full || '', data.thinking || '', data.sources || [], data.metrics || null)
            } else {
              const token = data.token || ''
              if (!token) continue
              raw += token

              // parse think tags in-place
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
                    // check if </think> is also in this chunk
                    const endIdx = remaining.indexOf('</think>')
                    if (endIdx >= 0) {
                      const thinkText = remaining.slice(6, endIdx) // skip <think
                      if (thinkText) onThinking?.(thinkText, false)
                      onThinking?.('', true)
                      remaining = remaining.slice(endIdx + 8)
                      inThink = false
                      isFirstContent = true
                    } else {
                      const thinkText = remaining.slice(6) // skip <think
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
          } catch (_) {}
        }
      }
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') onError?.(err.message)
  })

  return () => controller.abort()
}

export async function getCollections() {
  const r = await fetch(`${API}/collections`)
  return r.json()
}

export async function createCollection(name) {
  const r = await fetch(`${API}/collections?name=${encodeURIComponent(name)}`, {
    method: 'POST',
  })
  if (!r.ok) throw new Error((await r.json()).detail)
  return r.json()
}

export async function deleteCollection(name) {
  const r = await fetch(`${API}/collections/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  if (!r.ok) throw new Error((await r.json()).detail)
  return r.json()
}

export async function getCollectionDocuments(name) {
  const r = await fetch(`${API}/collections/${encodeURIComponent(name)}/documents`)
  return r.json()
}

export async function uploadDocument(name, file) {
  const form = new FormData()
  form.append('file', file)
  const r = await fetch(`${API}/collections/${encodeURIComponent(name)}/documents`, {
    method: 'POST',
    body: form,
  })
  if (!r.ok) throw new Error((await r.json()).detail)
  return r.json()
}

export async function getWorkspaces() {
  const r = await fetch(`${API}/workspaces`)
  return r.json()
}

export async function createWorkspace(data) {
  const r = await fetch(`${API}/workspaces`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return r.json()
}

export async function updateWorkspace(id, data) {
  const r = await fetch(`${API}/workspaces/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return r.json()
}

export async function deleteWorkspace(id) {
  const r = await fetch(`${API}/workspaces/${id}`, {
    method: 'DELETE',
  })
  return r.json()
}
