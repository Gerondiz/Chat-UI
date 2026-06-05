import { useState, useRef, useCallback } from 'react'
import * as api from '../api'
import type { Message, ChatSettings, Source, Metrics } from '../types'

export function useProviders() {
  const [providerName, setProviderName] = useState('ollama')
  const [providerOnline, setProviderOnline] = useState(false)
  const [chatModel, setChatModel] = useState('')
  const [embeddingModel, setEmbeddingModel] = useState('')
  const [chatModels, setChatModels] = useState<string[]>([])
  const [embeddingModels, setEmbeddingModels] = useState<string[]>([])

  const loadProviderInfo = useCallback(async () => {
    try {
      const cfg = await api.getProvider()
      setProviderName(cfg.name)
      setChatModel(cfg.chat_model)
      setEmbeddingModel(cfg.embedding_model)
      const st = await api.getProviderStatus()
      setProviderOnline(st.online)
      setChatModels(st.chat_models || [])
      setEmbeddingModels(st.embedding_models || [])
    } catch (_) { /* ignore */ }
  }, [])

  const handleSwitchProvider = useCallback(async (name: string) => {
    try {
      setProviderOnline(false)
      setChatModels([])
      setChatModel('')
      const cfg = await api.switchProvider(name)
      setProviderName(cfg.name)
      setChatModel(cfg.chat_model)
      setEmbeddingModel(cfg.embedding_model)
      const st = await api.getProviderStatus()
      setProviderOnline(st.online)
      setChatModels(st.chat_models || [])
      setEmbeddingModels(st.embedding_models || [])
    } catch (_) { /* ignore */ }
  }, [])

  const handleSelectModel = useCallback(async (model: string) => {
    setChatModel(model)
    try {
      const cfg = await api.getProvider()
      cfg.chat_model = model
      await api.updateProviderConfig(cfg)
      const st = await api.getProviderStatus()
      setProviderOnline(st.online)
    } catch (_) { /* ignore */ }
  }, [])

  return {
    providerName, setProviderName,
    providerOnline, setProviderOnline,
    chatModel, setChatModel,
    embeddingModel, setEmbeddingModel,
    chatModels, setChatModels,
    embeddingModels, setEmbeddingModels,
    loadProviderInfo,
    handleSwitchProvider,
    handleSelectModel,
  }
}
