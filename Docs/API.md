# Provider API Reference

Документация по API трёх поддерживаемых провайдеров: **Ollama**, **OpenAI-совместимые** (включая LM Studio), **LM Studio Native API**.

---

## 1. Ollama API

**Базовый URL:** `http://localhost:11434`  
**Формат:** NDJSON (по одной JSON-строке на строку)  
**Эндпоинты:** `/api/chat`, `/api/tags`, `/api/embed`, `/api/tags`

---

### 1.1. Chat — `POST /api/chat`

#### Запрос

```json
{
  "model": "gemma3:4b",
  "messages": [
    {"role": "system", "content": "Ты — полезный ассистент."},
    {"role": "user", "content": "Привет"}
  ],
  "stream": true,
  "options": {
    "temperature": 0.7,
    "top_p": 0.9,
    "num_predict": 4096
  },
  "tools": [
    {
      "function": {
        "name": "search_chromadb",
        "description": "Поиск в коллекции ChromaDB",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {"type": "string", "description": "Поисковый запрос"},
            "collection_name": {"type": "string", "description": "Имя коллекции"}
          },
          "required": ["query", "collection_name"]
        }
      }
    }
  ]
}
```

**Параметры:**

| Поле | Тип | По умолч. | Описание |
|------|-----|-----------|----------|
| `model` | string | — | Имя модели |
| `messages` | `[{role, content}]` | — | История сообщений |
| `stream` | bool | `false` | Поточный режим (NDJSON) |
| `options.temperature` | float | `0.8` | Температура (0.0–2.0) |
| `options.top_p` | float | `0.9` | Top-p sampling |
| `options.num_predict` | int | `128` | Максимум токенов |
| `system` | string | — | Системный промпт (альтернатива messages) |
| `tools` | `[{function}]` | — | Схемы инструментов |

#### Ответ (stream: false)

```json
{
  "model": "gemma3:4b",
  "created_at": "2024-01-01T00:00:00Z",
  "message": {
    "role": "assistant",
    "content": "Привет! Чем могу помочь?"
  },
  "done": true,
  "done_reason": "stop",
  "total_duration": 5123456789,
  "load_duration": 123456789,
  "prompt_eval_count": 45,
  "prompt_eval_duration": 234567890,
  "eval_count": 120,
  "eval_duration": 4567890123
}
```

#### Ответ (stream: true) — NDJSON

Каждая строка — валидный JSON:

```json
{"model":"gemma3:4b","created_at":"...","message":{"role":"assistant","content":"При"},"done":false}
{"model":"gemma3:4b","created_at":"...","message":{"role":"assistant","content":"вет"},"thinking":"пользователь здоровается","done":false}
{"model":"gemma3:4b","created_at":"...","message":{"role":"assistant","content":"!"},"done":false}
```

**Поле `thinking`** — опционально, может присутствовать в любом чанке. Содержит фрагмент размышлений модели.

**Последний чанк (done: true):**
```json
{
  "model": "gemma3:4b",
  "message": {"role": "assistant", "content": "Привет!"},
  "done": true,
  "total_duration": 5000000000,
  "prompt_eval_count": 45,
  "eval_count": 120,
  "eval_duration": 4000000000
}
```

#### Tool calls (Ollama)

```json
{
  "model": "gemma3:4b",
  "message": {
    "role": "assistant",
    "content": "",
    "tool_calls": [
      {
        "function": {
          "name": "search_chromadb",
          "arguments": {"query": "правила", "collection_name": "docs"}
        }
      }
    ]
  },
  "done": true
}
```

Ollama использует `id` в tool_calls, но НЕ использует `type: "function"` (в отличие от OpenAI). `arguments` — объект JSON, а не строка.

---

#### Tool calls в стриме

```
{"model":"gemma4:e4b","message":{"role":"assistant","content":"","thinking":"1. **"},"done":false}
{"model":"gemma4:e4b","message":{"role":"assistant","content":"","thinking":"Analyze the Request..."},"done":false}
...
{"model":"gemma4:e4b","message":{"role":"assistant","content":"","tool_calls":[{"id":"call_xxx","function":{"index":0,"name":"get_weather","arguments":{"city":"Пенза","date":"tomorrow"}}}]},"done":false}
{"model":"gemma4:e4b","message":{"role":"assistant","content":""},"done":true,"done_reason":"stop","total_duration":146905951638,"prompt_eval_count":75,"eval_count":274}
```

> **Важно:** В стриме Ollama thinking приходит в каждом чанке как отдельное поле `thinking`, **не** в `message.content`. Поле `content` во время размышлений пустое (`""`).
>
> Tool calls приходят как `tool_calls` с `id`, `function.index`, `function.name`, `function.arguments` (объект, не строка).

#### Полный цикл с инструментом

**Шаг 1:** Запрос → модель просит вызвать инструмент:
```bash
curl http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4:e4b",
    "messages": [{"role": "user", "content": "Какая погода завтра в Пензе?"}],
    "tools": [{
      "function": {
        "name": "get_weather",
        "description": "Получить прогноз погоды",
        "parameters": {
          "type": "object",
          "properties": {
            "city": {"type": "string"},
            "date": {"type": "string"}
          },
          "required": ["city"]
        }
      }
    }],
    "stream": true
  }'
```

**Шаг 2:** Возвращаем результат инструмента модели:
```bash
curl http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4:e4b",
    "messages": [
      {"role": "user", "content": "Какая погода завтра в Пензе?"},
      {"role": "assistant", "content": "", "tool_calls": [{"id":"call_xxx","function":{"name":"get_weather","arguments":{"city":"Пенза","date":"tomorrow"}}}]},
      {"role": "tool", "content": "{\"temperature\":25,\"condition\":\"солнечно\"}", "name": "get_weather"}
    ],
    "stream": false
  }'
```

---

### 1.2. Список моделей — `GET /api/tags`

#### Ответ

```json
{
  "models": [
    {"name": "gemma4:e4b", "modified_at": "...", "size": 9608350718, "capabilities": ["completion", "tools", "thinking"]},
    {"name": "llama3:70b", "modified_at": "...", "size": 40000000000}
  ]
}
```

---

### 1.3. Эмбеддинги — `POST /api/embed`

#### Запрос

```json
{
  "model": "nomic-embed-text",
  "input": ["текст для эмбеддинга"]
}
```

#### Ответ

```json
{
  "model": "nomic-embed-text",
  "embeddings": [[0.001, -0.002, ...]]
}
```

---

### 1.4. Проверка доступности — `GET /api/tags`

Успех: `200 OK`. Ошибка: соединение не установлено.

---

## 2. OpenAI-compatible API

**Базовый URL:** `http://localhost:1234/v1`  
**Формат:** JSON / SSE  
**Поддерживается:** LMStudio (OpenAI mode), vLLM, LocalAI, OpenAI API

---

### 2.1. Chat Completions — `POST /v1/chat/completions`

#### Запрос

```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "system", "content": "Ты — полезный ассистент."},
    {"role": "user", "content": "Привет"}
  ],
  "temperature": 0.7,
  "max_tokens": 4096,
  "top_p": 0.9,
  "stream": false,
  "stream_options": {"include_usage": true}
}
```

**Параметры:**

| Поле | Тип | По умолч. | Описание |
|------|-----|-----------|----------|
| `model` | string | — | Имя модели |
| `messages` | `[{role, content}]` | — | История сообщений |
| `temperature` | float | `1.0` | Температура |
| `max_tokens` | int | inf | Максимум токенов |
| `top_p` | float | `1.0` | Top-p sampling |
| `stream` | bool | `false` | Поточный режим (SSE) |
| `stream_options.include_usage` | bool | `false` | Включить usage в последний чанк |
| `tools` | `[{type, function}]` | — | Схемы инструментов (см. ниже) |

#### Ответ (stream: false) — полный

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Привет! Чем могу помочь?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 45,
    "completion_tokens": 120,
    "total_tokens": 165
  }
}
```

**С reasoning/thinking (не-стриминг):**
```json
{
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": null,
      "reasoning_content": "Пользователь здоровается, нужно ответить приветствием."
    },
    "finish_reason": "stop"
  }]
}
```
Если `content` пуст, а `reasoning_content` заполнен — контент был только размышлением.

#### Ответ (stream: true) — SSE

Каждый чанк:

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"При"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"вет"},"finish_reason":null}]}
```

**Чанк с reasoning:**
```
data: {"id":"...","choices":[{"index":0,"delta":{"reasoning_content":"пользователь здоровается"},"finish_reason":null}]}
```

Поле `reasoning_content` в delta — фрагмент размышлений. Альтернативное имя поля: `reasoning`.

**Чанк с usage (последний, с `include_usage: true`):**
```
data: {"id":"...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":45,"completion_tokens":120,"total_tokens":165}}
```

**Сигнал завершения:**
```
data: [DONE]
```

#### Tool calls (OpenAI-формат)

**Запрос с tools:**
```json
{
  "model": "gpt-4",
  "messages": [...],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_chromadb",
        "description": "Поиск в ChromaDB",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {"type": "string"},
            "collection_name": {"type": "string"}
          },
          "required": ["query", "collection_name"]
        }
      }
    }
  ]
}
```

**Ответ с tool_calls:**
```json
{
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [
        {
          "id": "call_abc123",
          "type": "function",
          "function": {
            "name": "search_chromadb",
            "arguments": "{\"query\": \"правила\", \"collection_name\": \"docs\"}"
          }
        }
      ]
    },
    "finish_reason": "tool_calls"
  }]
}
```

**Отличия от Ollama:**
- Есть `id` — уникальный идентификатор вызова
- `type: "function"` — обязательное поле
- `arguments` — строка JSON (не объект)
- `finish_reason: "tool_calls"` — причина завершения

---

### 2.2. Список моделей — `GET /v1/models`

#### Ответ

```json
{
  "object": "list",
  "data": [
    {"id": "gpt-4", "object": "model", "created": 1700000000},
    {"id": "text-embedding-ada-002", "object": "model"}
  ]
}
```

---

### 2.3. Эмбеддинги — `POST /v1/embeddings`

#### Запрос

```json
{
  "model": "text-embedding-ada-002",
  "input": "текст для эмбеддинга"
}
```

#### Ответ

```json
{
  "object": "list",
  "data": [
    {"object": "embedding", "index": 0, "embedding": [0.001, -0.002, ...]}
  ],
  "usage": {"prompt_tokens": 5, "total_tokens": 5}
}
```

---

## 3. LM Studio

LM Studio поддерживает **два режима API**:

| Режим | Эндпоинт | Порт | Формат |
|-------|----------|------|--------|
| **OpenAI-совместимый** (рекомендуется) | `/v1/chat/completions` | 1234 | Стандартный OpenAI (`messages`, `tools`, `reasoning_content`) |
| **Native REST API** (устаревший) | `/api/v1/chat` | 1234 | Кастомный (`input` + SSE events) |

По умолчанию LM Studio сервер слушает на порту **1234** и предоставляет OpenAI-совместимый API.

---

### 3.1. OpenAI-совместимый режим (рекомендуется)

**Базовый URL:** `http://localhost:1234/v1`  
**Эндпоинт:** `POST /v1/chat/completions`  
**Формат:** JSON / SSE (полностью OpenAI-совместимый)

Полная документация: https://lmstudio.ai/docs/developer/openai-compat/chat-completions

#### Запрос

```json
{
  "model": "google/gemma-4-e4b",
  "messages": [
    {"role": "system", "content": "Ты — полезный ассистент."},
    {"role": "user", "content": "Привет"}
  ],
  "temperature": 0.7,
  "max_tokens": 4096,
  "top_p": 0.9,
  "stream": false,
  "stream_options": {"include_usage": true}
}
```

**Поддерживаемые параметры:** `model`, `messages`, `temperature`, `max_tokens`, `top_p`, `top_k`, `stream`, `stop`, `presence_penalty`, `frequency_penalty`, `logit_bias`, `repeat_penalty`, `seed`, `tools`, `tool_choice`.

#### Ответ (stream: false) — с reasoning

```json
{
  "id": "chatcmpl-eyxcho05p2r0jd89z8rv3s",
  "object": "chat.completion",
  "created": 1780673171,
  "model": "google/gemma-4-e4b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Завтра в Пензе ожидается...",
        "reasoning_content": "Пользователь спрашивает о погоде. Нужно ответить..."
      },
      "logprobs": null,
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 45,
    "completion_tokens": 120,
    "total_tokens": 165,
    "completion_tokens_details": {
      "reasoning_tokens": 50
    }
  },
  "system_fingerprint": "google/gemma-4-e4b"
}
```

#### Ответ (stream: true) — SSE

Reasoning идёт токен за токеном в `delta.reasoning_content`:

```
data: {"choices":[{"index":0,"delta":{"role":"assistant","reasoning_content":"\n"},"finish_reason":null}]}
data: {"choices":[{"index":0,"delta":{"reasoning_content":"Пользователь"},"finish_reason":null}]}
data: {"choices":[{"index":0,"delta":{"reasoning_content":" спрашивает"},"finish_reason":null}]}
data: {"choices":[{"index":0,"delta":{"reasoning_content":" о"},"finish_reason":null}]}
data: {"choices":[{"index":0,"delta":{"reasoning_content":" погоде"},"finish_reason":null}]}
...
```

Затем — контент ответа в `delta.content`:

```
data: {"choices":[{"index":0,"delta":{"content":"Завтра"},"finish_reason":null}]}
data: {"choices":[{"index":0,"delta":{"content":" в"},"finish_reason":null}]}
data: {"choices":[{"index":0,"delta":{"content":" Пензе"}]}}
```

При использовании `stream_options: {include_usage: true}` последний чанк содержит `usage`:

```
data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":45,"completion_tokens":120,"total_tokens":165},"system_fingerprint":"google/gemma-4-e4b"}
```

Сигнал завершения:
```
data: [DONE]
```

#### Tool calls

Полностью OpenAI-совместимый формат.

**Запрос с tools:**
```json
{
  "model": "google/gemma-4-e4b",
  "messages": [
    {"role": "user", "content": "Какая погода завтра в Пензе?"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Получить прогноз погоды для указанного города",
        "parameters": {
          "type": "object",
          "properties": {
            "city": {"type": "string", "description": "Название города"},
            "date": {"type": "string", "description": "Дата в формате YYYY-MM-DD"}
          },
          "required": ["city"]
        }
      }
    }
  ]
}
```

**Ответ (stream: false) — модель решила вызвать инструмент:**
```json
{
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "",
      "reasoning_content": "1. **Analyze the user's request:** The user is asking \"What is the weather tomorrow in Penza?\"\n2. **Examine available tools:** I have one tool: `get_weather`.\n...",
      "tool_calls": [
        {
          "type": "function",
          "id": "987776806",
          "function": {
            "name": "get_weather",
            "arguments": "{\"city\":\"Пенза\",\"date\":\"2026-06-06\"}"
          }
        }
      ]
    },
    "finish_reason": "tool_calls"
  }],
  "usage": {
    "completion_tokens_details": {
      "reasoning_tokens": 550
    }
  }
}
```

**Ответ (stream: true) — tool calls в стриме:**

Сначала reasoning (токен за токеном):
```
data: {"delta":{"reasoning_content":"1."}}
data: {"delta":{"reasoning_content":" **"}}  
data: {"delta":{"reasoning_content":"Analyze"}}
...
```

Потом tool_calls (в одном или нескольких чанках):
```
data: {"delta":{"tool_calls":[{"index":0,"id":"519801730","type":"function","function":{"name":"get_weather","arguments":""}}]}}
data: {"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"city\":\"Пенза\"}"}}]}}
data: {"delta":{},"finish_reason":"tool_calls"}}
data: [DONE]
```

**Отличия от OpenAI API:**
- `usage.completion_tokens_details.reasoning_tokens` — количество токенов reasoning (как у OpenAI o-family)
- `system_fingerprint` содержит ID модели
- В стриме tool_calls могут приходить в нескольких чанках (как у OpenAI)

#### Пример полного цикла с инструментом (curl)

**Шаг 1:** Запрос → модель просит вызвать инструмент:
```bash
curl http://26.55.98.240:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-4-e4b",
    "messages": [{"role": "user", "content": "Какая погода завтра в Пензе?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Получить прогноз погоды",
        "parameters": {
          "type": "object",
          "properties": {
            "city": {"type": "string"},
            "date": {"type": "string"}
          },
          "required": ["city"]
        }
      }
    }]
  }'
```

**Шаг 2:** Возвращаем результат инструмента модели:
```bash
curl http://26.55.98.240:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-4-e4b",
    "messages": [
      {"role": "user", "content": "Какая погода завтра в Пензе?"},
      {"role": "assistant", "tool_calls": [{"id":"call_1","type":"function","function":{"name":"get_weather","arguments":"{\"city\":\"Пенза\",\"date\":\"2026-06-06\"}"}}]},
      {"role": "tool", "content": "{\"temperature\": 25, \"condition\": \"солнечно\", \"humidity\": 40}", "tool_call_id": "call_1"}
    ]
  }'
```

---

### 3.2. Native REST API (устаревший)

**Базовый URL:** `http://localhost:1234` (без `/v1`)  
**Эндпоинт:** `POST /api/v1/chat`  
**Формат:** JSON / SSE с кастомными событиями  

> **Важно:** Этот API НЕ совместим с OpenAI-форматом. Использует собственную схему запроса и SSE-событий.
> Рекомендуется использовать OpenAI-совместимый режим (`/v1/chat/completions`).

Документация: https://lmstudio.ai/docs/developer/rest/chat

#### Запрос

```json
{
  "model": "google/gemma-4-e4b",
  "input": "System: Ты — полезный ассистент.\nUser: Привет\nAssistant:",
  "temperature": 0.7,
  "max_output_tokens": 4096,
  "top_p": 0.9,
  "stream": false,
  "system_prompt": "Ты — полезный ассистент."
}
```

**Параметры:**

| Поле | Тип | По умолч. | Описание |
|------|-----|-----------|----------|
| `model` | string | — | Имя модели |
| `input` | string | — | Весь диалог одной строкой `Role: text\n` |
| `temperature` | float | 0.0–2.0 | Температура |
| `max_output_tokens` | int | — | **ВНИМАНИЕ:** не `max_tokens`, а `max_output_tokens` |
| `top_p` | float | — | Top-p sampling |
| `stream` | bool | `false` | Поточный режим (кастомные SSE-события) |
| `system_prompt` | string | — | Системный промпт (дублируется в `input`) |
| `reasoning` | string | `"on"` | `"off"` — отключить reasoning |

**Формат `input`:** каждая строка — `{Role}: {content}`, где Role — `System`, `User`, `Assistant`. Строки разделяются `\n`.

#### Ответ (stream: false)

```json
{
  "model": "google/gemma-4-e4b",
  "output": [
    {"type": "message", "content": "Привет! Чем могу помочь?"}
  ]
}
```

Поле `output` — массив объектов `{type, content}`.

#### Ответ (stream: true) — кастомные SSE-события

```
event: reasoning.delta
data: {"content": "пользователь"}

event: reasoning.delta  
data: {"content": " здоровается"}

event: message.delta
data: {"content": "При"}

event: message.delta
data: {"content": "вет!"}

event: chat.end
data: {"result": {"stats": {"input_tokens": 45, "output_tokens": 120, "tokens_per_second": 26.3}}}
```

**Типы событий:**

| Событие | Описание | Поля data |
|---------|----------|-----------|
| `reasoning.delta` | Фрагмент размышлений | `{"content": "..."}` |
| `message.delta` | Фрагмент ответа | `{"content": "..."}` |
| `chat.end` | Завершение генерации | `{"result": {"stats": {...}}}` |

**Статистика в `chat.end`:**
```json
{
  "result": {
    "stats": {
      "input_tokens": 45,
      "output_tokens": 120,
      "tokens_per_second": 26.3,
      "time_to_first_token": 1.23
    }
  }
}
```

Поля `stats` зависят от версии LM Studio.

#### Список моделей — `GET /api/v1/models`

```json
{
  "data": [
    {"id": "google/gemma-4-e4b"},
    {"id": "text-embedding-nomic-embed-text-v1.5"}
  ]
}
```

Ключ ответа может быть `models` или `data`.

#### Эмбеддинги — `POST /api/v1/embeddings`

```json
{
  "model": "text-embedding-nomic-embed-text-v1.5",
  "input": "текст для эмбеддинга"
}
```

---

## 4. Thinking/Reasoning — форматы по провайдерам

| Провайдер | Поле (не-стриминг) | Поле (стриминг) | Где находится |
|-----------|-------------------|-----------------|---------------|
| **Ollama** | Поле `thinking` в `_post()` → накапливается и вставляется перед контентом как `<think{текст} response` | Поле `thinking` в каждом NDJSON-чанке | Отдельное поле в чанке (`"thinking":"текст"`), `message.content` во время thinking пуст |
| **OpenAI** | `reasoning_content` в `message` | `delta.reasoning_content` (fallback: `delta.reasoning`) | Отдельное поле в `message`/`delta`, не в `content` |
| **LM Studio** (OpenAI-compat) | `reasoning_content` в `message` | `delta.reasoning_content` | Отдельное поле в `message`/`delta`, не в `content` |
| **LM Studio** (Native) | Нет (отдельное поле отсутствует) | Событие `reasoning.delta` | SSE-событие |

**Важно:** Ни один провайдер не вставляет reasoning/thinking в `message.content` или `delta.content` (кроме Ollama `_post()` который оборачивает thinking как `<think{текст} response` и вставляет в `content`). В стриминге все провайдеры используют **отдельные поля** (`reasoning_content`, `thinking`). Парсить `<think>`-теги из `content` в стриме бессмысленно — их там нет.

---

## 5. Статистика токенов — форматы

| Провайдер | Откуда берётся | Поля |
|-----------|---------------|------|
| **Ollama** | Последний NDJSON-чанк (`done: true`) | `input_tokens` (prompt_eval_count), `output_tokens` (eval_count), `tokens_per_second` (eval_duration), `time_to_first_token_seconds` (total_duration) |
| **OpenAI** | Поле `usage` (в ответе или в SSE-чанке с `stream_options.include_usage`) | `input_tokens` (prompt_tokens), `output_tokens` (completion_tokens). `tokens_per_second` отсутствует |
| **LM Studio** (OpenAI-compat) | Поле `usage` в ответе | `input_tokens` (prompt_tokens), `output_tokens` (completion_tokens), `reasoning_tokens` (completion_tokens_details.reasoning_tokens) |
| **LM Studio** (Native) | Событие `chat.end` → `result.stats` | Зависит от версии: `input_tokens`, `output_tokens`, `tokens_per_second`, `time_to_first_token` |

---

## 6. Tool calls — форматы по провайдерам

| Провайдер | Формат `tools` в запросе | `tool_calls` в ответе | `arguments` | `id` / `type` | Особенности стриминга |
|-----------|------------------------|----------------------|-------------|---------------|----------------------|
| **Ollama** | `[{function: {name, description, parameters}}]` (без `type`) | `message.tool_calls: [{id, function: {name, arguments: {...}}}]` | **Объект** JSON | Есть `id`, нет `type` | Thinking идёт в `thinking`-поле каждого чанка, потом `tool_calls` в одном чанке, потом `done: true` |
| **OpenAI** | `[{type: "function", function: {name, description, parameters}}]` | `[{id, type: "function", function: {name, arguments: "..."}}]` | **Строка** JSON | Есть `id`, `type: "function"` | Reasoning в `delta.reasoning_content`, tool_calls могут идти в нескольких чанках |
| **LM Studio** (OpenAI-compat) | `[{type: "function", function: {name, description, parameters}}]` | `[{id, type: "function", function: {name, arguments: "..."}}]` | **Строка** JSON | Есть `id`, `type: "function"` | Как OpenAI |
| **LM Studio** (Native) | Не поддерживается | — | — | — | — |

**Ключевые отличия Ollama от OpenAI:**
1. В запросе `tools` — без `type: "function"`, только `[{function: {...}}]`
2. `arguments` — объект JSON, а не строка (`{"city":"Пенза"}` vs `"{\"city\":\"Пенза\"}"`)
3. В стриме `tool_calls` приходит в одном чанке с `id`, `function.index`, `function.name`, `function.arguments`
4. `finish_reason` отсутствует в стриме — только `done: true` в последнем чанке
