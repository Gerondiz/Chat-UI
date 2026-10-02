import React, { useState } from 'react'
import * as api from '../api'
import type { ProviderConfig, ProviderTestResult } from '../types'

interface ConnectionSettingsProps {
  onClose: () => void
  onSaved: (cfg: ProviderConfig) => void
}

const PROVIDERS = [
  { id: 'openai', label: 'OpenAI-совместимый (LMStudio/vLLM)' },
  { id: 'lmstudio', label: 'LMStudio (Native)' },
  { id: 'ollama', label: 'Ollama' },
]

export default function ConnectionSettings({ onClose, onSaved }: ConnectionSettingsProps) {
  const [cfg, setCfg] = useState<ProviderConfig | null>(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null)
  const [saved, setSaved] = useState(false)
  const [loadError, setLoadError] = useState('')

  React.useEffect(() => {
    api.getProvider().then((c) => setCfg(c)).catch(() => setLoadError('Не удалось загрузить текущий конфиг'))
  }, [])

  const set = (key: keyof ProviderConfig, value: string) => {
    setCfg((prev) => (prev ? { ...prev, [key]: value } : prev))
    setSaved(false)
    setTestResult(null)
  }

  const handleTest = async () => {
    if (!cfg) return
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.testProviderConfig(cfg)
      setTestResult(res)
      if (res.online && res.chat_models.length > 0 && !cfg.chat_model) {
        setCfg((prev) => prev ? { ...prev, chat_model: res.chat_models[0] } : prev)
      }
      if (res.online && res.embedding_models.length > 0 && !cfg.embedding_model) {
        setCfg((prev) => prev ? { ...prev, embedding_model: res.embedding_models[0] } : prev)
      }
    } catch (e: any) {
      setTestResult({ name: cfg.name, online: false, chat_model: '', embedding_model: '', chat_models: [], embedding_models: [], error: String(e.message || e) })
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    if (!cfg) return
    try {
      const savedCfg = await api.updateProviderConfig(cfg)
      setCfg(savedCfg)
      setSaved(true)
      onSaved(savedCfg)
    } catch (e: any) {
      setTestResult({ name: cfg.name, online: false, chat_model: '', embedding_model: '', chat_models: [], embedding_models: [], error: String(e.message || e) })
    }
  }

  if (loadError) {
    return (
      <>
        <div className="settings-overlay" onClick={onClose} />
        <div className="settings-panel">
          <h2>Подключение</h2>
          <div className="conn-error">{loadError}</div>
          <button className="btn btn-primary" onClick={onClose} style={{ width: '100%', marginTop: 8 }}>Закрыть</button>
        </div>
      </>
    )
  }

  return (
    <>
      <div className="settings-overlay" onClick={onClose} />
      <div className="settings-panel">
        <h2>Подключение к LLM</h2>

        {!cfg ? (
          <div className="conn-loading">Загрузка...</div>
        ) : (
          <>
            <div className="settings-group">
              <label>Провайдер</label>
              <select value={cfg.name} onChange={(e) => set('name', e.target.value)}>
                {PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
              </select>
            </div>

            <div className="settings-group">
              <label>Base URL</label>
              <input
                type="text"
                value={cfg.base_url}
                onChange={(e) => set('base_url', e.target.value)}
                placeholder="http://host:port/v1"
                spellCheck={false}
              />
            </div>

            <div className="settings-group">
              <label>API Key (если требуется)</label>
              <input
                type="password"
                value={cfg.api_key || ''}
                onChange={(e) => set('api_key', e.target.value)}
                placeholder="sk-..."
                spellCheck={false}
              />
            </div>

            <div className="settings-group">
              <label>Чат-модель</label>
              <select value={cfg.chat_model} onChange={(e) => set('chat_model', e.target.value)}>
                {testResult && testResult.chat_models.length > 0 ? (
                  testResult.chat_models.map(m => <option key={m} value={m}>{m}</option>)
                ) : (
                  <option value={cfg.chat_model}>{cfg.chat_model || '— выберите модель —'}</option>
                )}
              </select>
            </div>

            <div className="settings-group">
              <label>Эмбеддинг-модель (для RAG)</label>
              <select value={cfg.embedding_model} onChange={(e) => set('embedding_model', e.target.value)}>
                {testResult && testResult.embedding_models.length > 0 ? (
                  testResult.embedding_models.map(m => <option key={m} value={m}>{m}</option>)
                ) : (
                  <option value={cfg.embedding_model}>{cfg.embedding_model || '— выберите модель —'}</option>
                )}
              </select>
            </div>

            <div className="conn-actions">
              <button className="btn" onClick={handleTest} disabled={testing}>
                {testing ? 'Проверка...' : '🔌 Проверить'}
              </button>
              <button className="btn btn-primary" onClick={handleSave}>Сохранить</button>
            </div>

            {testResult && (
              <div className={`conn-result ${testResult.online ? 'ok' : 'fail'}`}>
                <div className="conn-result-title">
                  {testResult.online ? '✅ Подключение работает' : '❌ Не удалось подключиться'}
                </div>
                {testResult.error && <div className="conn-result-err">{testResult.error}</div>}
                {testResult.online && (
                  <div className="conn-result-models">
                    Модели ({testResult.chat_models.length}): {testResult.chat_models.join(', ')}
                  </div>
                )}
              </div>
            )}

            {saved && <div className="conn-saved">✅ Настройки сохранены</div>}

            <button className="btn" onClick={onClose} style={{ width: '100%', marginTop: 8 }}>Закрыть</button>
          </>
        )}
      </div>
    </>
  )
}
