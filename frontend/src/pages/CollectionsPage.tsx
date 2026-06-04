import React, { useState, useEffect } from 'react'
import * as api from '../api'
import type { Collection } from '../types'

export default function CollectionsPage() {
  const [collections, setCollections] = useState<Collection[]>([])
  const [newName, setNewName] = useState('')
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState<string | null>(null)

  const load = async () => {
    try {
      const data = await api.getCollections()
      setCollections(data.collections || [])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleCreate = async () => {
    const name = newName.trim()
    if (!name) return
    try {
      await api.createCollection(name)
      setNewName('')
      load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleDelete = async (name: string) => {
    if (!confirm(`Удалить коллекцию "${name}"?`)) return
    try {
      await api.deleteCollection(name)
      load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleUpload = async (collectionName: string, file: File) => {
    setUploading(collectionName)
    setError('')
    try {
      await api.uploadDocument(collectionName, file)
      load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setUploading(null)
    }
  }

  return (
    <div className="collections-page">
      <h2>📚 Коллекции RAG</h2>

      {error && (
        <div style={{ color: 'var(--red)', marginBottom: 12, fontSize: 13 }}>
          ❌ {error}
        </div>
      )}

      <div className="create-collection">
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => e.key === 'Enter' && handleCreate()}
          placeholder="Название новой коллекции..."
        />
        <button className="btn btn-primary" onClick={handleCreate}>
          + Создать
        </button>
      </div>

      {collections.length === 0 && (
        <div style={{ color: 'var(--text2)', textAlign: 'center', marginTop: 40, fontSize: 14 }}>
          Пока нет ни одной коллекции
        </div>
      )}

      {collections.map((col) => (
        <div key={col.name} className="collection-card">
          <div className="info">
            <div className="name">{col.name}</div>
            <div className="meta">{col.count} документов</div>
            <div className="upload-area" style={{ marginTop: 8 }}>
              <input
                type="file"
                accept=".pdf,.txt,.docx"
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                  if (e.target.files?.[0]) handleUpload(col.name, e.target.files[0])
                  e.target.value = ''
                }}
                disabled={uploading === col.name}
              />
              {uploading === col.name && (
                <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--accent)' }}>
                  Загрузка...
                </span>
              )}
            </div>
          </div>
          <div className="collection-actions">
            <button
              className="btn btn-danger"
              onClick={() => handleDelete(col.name)}
            >
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
