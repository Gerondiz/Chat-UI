# Спецификация проекта: Chat-UI — лёгкая альтернатива Open WebUI

## 1. Назначение

Веб-интерфейс для общения с LLM через бэкенды Ollama и OpenAI-совместимые API (LMStudio, vLLM, LocalAI). Минималистичная замена Open WebUI с возможностью переключения провайдера на лету и поддержкой RAG.

В перспективе — основа для создания агентов и рабочих пространств (Workspace) с собственными моделями, системными промптами и подключенными коллекциями.

---

## 2. Архитектура

```
React + Vite (JS) ──HTTP──> FastAPI ──HTTP──> Ollama (localhost:11434)
                                      ──HTTP──> OpenAI-совместимый API (LMStudio, vLLM…)
                                      ──HTTP──> ChromaDB (localhost:8000)
                                      └── SQLite (workspaces, история)
```

### 2.1. Бэкенд: FastAPI (Python 3.11+)

**Стек:** FastAPI, httpx, chromadb-client, PyMuPDF (pdf), python-docx, aiofiles.

**Роли:**
- Единый прокси для чата и эмбеддингов
- Переключение провайдера (Ollama / OpenAI) в рантайме
- Потоковая передача ответа (Server-Sent Events)
- Управление RAG-коллекциями (список, создание, удаление, загрузка документов)
- Управление Workspace (свои модели с системным промптом, настройками, коллекциями)
- Хранение Workspace в SQLite

**Конфигурация провайдеров** — через переменные окружения / `.env`:
- `OLLAMA_BASE_URL` — по умолчанию `http://localhost:11434`
- `OPENAI_BASE_URL` — по умолчанию `http://localhost:1234/v1`
- `OPENAI_API_KEY` — опционально

### 2.2. Фронтенд: React + Vite + JavaScript

**Стек:** React, Vite, react-markdown + remark-gfm, CSS (тёмная тема, без Tailwind).

**Страницы:**
1. **Чат** — основная страница (сообщения, ввод, статус-бар)
2. **Коллекции** — управление RAG-коллекциями
3. **Workspace** — создание/редактирование своих моделей (системный промпт, параметры, коллекции)

---

## 3. Функциональные требования

### 3.1. Переключение провайдера

- Боковая панель (слева): выбор `Ollama` | `OpenAI (LMStudio)`
- При выборе — запрос к `/api/provider/status`
- Индикатор: цветной кружок (зелёный / красный)
- После переключения — обновление списка моделей

### 3.2. Чат

- Поле ввода, кнопка отправки (Enter)
- История сообщений рендерится как markdown:
  - заголовки, списки, таблицы
  - подсветка кода (без prism/highlight.js — достаточно моноширинного блока)
- Потоковый вывод (SSE)
- Кнопка "Новый чат" (очищает историю)
- Переключение режима: **Обычный чат** / **Чат + RAG**
- При RAG — выбор коллекции для поиска

### 3.3. Системный промпт

- Панель настроек текущего чата (шестерёнка или выезжающая панель справа)
- Текстовое поле (textarea) для системного промпта
- Применяется к последующим запросам (добавляется в начало списка messages)
- По умолчанию: `"Ты — полезный ассистент. Отвечай на русском языке."`

### 3.4. Параметры модели

В той же панели настроек:
| Параметр | Тип | По умолчанию | Диапазон |
|---|---|---|---|
| Температура | slider | 0.7 | 0.0 – 2.0 |
| Max tokens | number | 4096 | 64 – 32768 |
| Top P | slider | 0.9 | 0.0 – 1.0 |
| Context length | number | 8192 | 1024 – 131072 |

### 3.5. RAG (Retrieval-Augmented Generation)

- Режим "Чат + RAG": перед отправкой к LLM поиск релевантных чанков в ChromaDB
- Выпадающий список выбора коллекции
- Отображение источников под ответом (сворачиваемый блок "Источники: N документов")

### 3.6. Управление коллекциями (страница)

- Список коллекций: имя, кол-во документов, дата создания
- Кнопка "Создать коллекцию" (ввод имени)
- Загрузка документов (pdf, txt, docx) — drag & drop или кнопка
- Удаление коллекции (с подтверждением)
- Просмотр списка файлов в коллекции

### 3.7. Workspace (рабочее пространство)

**Отложено, но архитектура закладывается сейчас.**

Сущность Workspace — "своя модель" со всеми настройками:
- Название (отображается в списке)
- Провайдер и модель (chat_model)
- Системный промпт
- Параметры (температура, max_tokens, top_p, context_length)
- Привязанные RAG-коллекции (одна или несколько)
- embedding_model для RAG

Использование:
1. Пользователь создаёт Workspace (набор настроек)
2. В чате выбирает Workspace из выпадающего списка
3. Применяются все настройки + системный промпт + коллекции для RAG

### 3.8. Статус-бар (нижняя панель или хедер)

- Активный провайдер + статус (🟢/🔴)
- Текущая модель (chat_model)
- Режим: 💬 Чат / 📄 RAG
- Активная коллекция (если RAG)

---

## 4. API Endpoints (FastAPI)

### Провайдер
| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/provider` | Получить текущего провайдера и его настройки |
| GET | `/api/providers` | Список доступных провайдеров |
| PUT | `/api/provider` | Переключить провайдера |
| GET | `/api/provider/status` | Статус + список доступных моделей |
| GET | `/api/provider/models` | Список моделей у активного провайдера |

### Чат
| Метод | Путь | Описание |
|---|---|---|
| POST | `/api/chat` | Отправить сообщение, ответ целиком |
| POST | `/api/chat/stream` | Отправить сообщение, ответ потоком (SSE) |

### RAG / Коллекции
| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/collections` | Список коллекций ChromaDB |
| POST | `/api/collections` | Создать коллекцию |
| DELETE | `/api/collections/{name}` | Удалить коллекцию |
| POST | `/api/collections/{name}/documents` | Загрузить документ(ы) |
| GET | `/api/collections/{name}/documents` | Список документов в коллекции |

### Workspace (отложено, но API закладывается)
| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/workspaces` | Список Workspace |
| POST | `/api/workspaces` | Создать Workspace |
| GET | `/api/workspaces/{id}` | Получить Workspace |
| PUT | `/api/workspaces/{id}` | Обновить Workspace |
| DELETE | `/api/workspaces/{id}` | Удалить Workspace |

---

## 5. Модели данных

### Провайдер
```python
class ProviderConfig(BaseModel):
    name: str             # "ollama" | "openai"
    chat_model: str
    embedding_model: str
    base_url: str
    api_key: str = ""
```

### Сообщение чата
```python
class Message(BaseModel):
    role: str     # "user" | "assistant" | "system"
    content: str

class ChatRequest(BaseModel):
    messages: list[Message]
    system_prompt: str = ""
    mode: str = "chat"          # "chat" | "rag"
    collection: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 0.9
    stream: bool = False
```

### Workspace (SQLite)
```sql
CREATE TABLE workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'ollama',
    chat_model TEXT NOT NULL DEFAULT '',
    embedding_model TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    temperature REAL NOT NULL DEFAULT 0.7,
    max_tokens INTEGER NOT NULL DEFAULT 4096,
    top_p REAL NOT NULL DEFAULT 0.9,
    context_length INTEGER NOT NULL DEFAULT 8192,
    collections TEXT NOT NULL DEFAULT '[]',  -- JSON-массив имён коллекций
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. UI / UX

- **Тёмная тема** (background `#1a1a2e`, surface `#16213e`, accent `#0f3460`, text `#e0e0e0`)
- **Слева** — боковая панель (300px):
  - Кнопка "Новый чат"
  - Список Workspace (позже)
  - Переключатель провайдера + статус
  - Ссылки: Коллекции, Workspace
- **Центр** — чат (сообщения по центру, max-width 900px)
- **Справа (выезжает)** — панель настроек (системный промпт, параметры)
- **Снизу** — поле ввода (мультилайн, растягивается до 200px)
- **Адаптивность** — на мобильных панель слева скрывается в бургер

---

## 7. План реализации

1. **FastAPI:** провайдеры, чат (plain + SSE), конфиг
2. **React:** базовая страница чата, markdown, переключение провайдера + статус
3. **FastAPI:** RAG (ChromaDB), загрузка документов
4. **React:** режим RAG, выбор коллекции, источники
5. **FastAPI + React:** управление коллекциями (страница)
6. **FastAPI + React:** системный промпт, настройки модели (панель справа)
7. **FastAPI + React:** Workspace (вся логика)
8. Полировка: мобильная вёрстка, ошибки, индикаторы загрузки

---

## 8. Зависимости

### Backend
```
fastapi, uvicorn[standard], httpx, chromadb-client, pymupdf, python-docx, aiofiles
```

### Frontend
```
react, react-dom, react-markdown, remark-gfm
```

devDependencies: `vite`, `@vitejs/plugin-react`

---

## 9. Запуск

```bash
# Backend
cd backend && pip install -r requirements.txt && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

Прокси Vite: `/api/*` → `http://localhost:8000`
