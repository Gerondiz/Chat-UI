import React from 'react'
import type { ChatSettings } from '../types'

interface SettingsPanelProps {
  settings: ChatSettings
  onChange: (settings: ChatSettings) => void
  onClose: () => void
}

export default function SettingsPanel({ settings, onChange, onClose }: SettingsPanelProps) {
  const set = (key: keyof ChatSettings, value: string | number) =>
    onChange({ ...settings, [key]: value })

  return (
    <>
      <div className="settings-overlay" onClick={onClose} />
      <div className="settings-panel">
        <h2>Настройки чата</h2>

        <div className="settings-group">
          <label>Системный промпт</label>
          <textarea
            value={settings.systemPrompt}
            onChange={(e) => set('systemPrompt', e.target.value)}
            placeholder="Введите системный промпт..."
            rows={5}
          />
        </div>

        <div className="settings-group">
          <label>Температура ({settings.temperature})</label>
          <input
            type="range" min="0" max="2" step="0.05"
            value={settings.temperature}
            onChange={(e) => set('temperature', parseFloat(e.target.value))}
          />
          <div className="range-label">
            <span>0 — точнее</span>
            <span>2 — креативнее</span>
          </div>
        </div>

        <div className="settings-group">
          <label>Top P ({settings.topP})</label>
          <input
            type="range" min="0" max="1" step="0.05"
            value={settings.topP}
            onChange={(e) => set('topP', parseFloat(e.target.value))}
          />
        </div>

        <div className="settings-group">
          <label>Max tokens</label>
          <input
            type="number" min="64" max="32768" step="1"
            value={settings.maxTokens}
            onChange={(e) => set('maxTokens', parseInt(e.target.value) || 4096)}
          />
        </div>

        <button
          className="btn btn-primary"
          onClick={onClose}
          style={{ width: '100%', marginTop: 8 }}
        >
          Готово
        </button>
      </div>
    </>
  )
}
