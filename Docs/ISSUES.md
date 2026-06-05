# Актуальные проблемы

## CRITICAL

### 1. Thinking-теги: конфликт форматов между провайдерами, бэкендом и фронтендом

**Файлы:** `backend/providers/ollama.py`, `backend/providers/openai.py`, `backend/providers/lmstudio.py`, `backend/main.py`, `frontend/src/api.ts`

**Проблема:** Используются 3 разных формата тегов, которые несовместимы:

| Формат | Кто отдаёт | Бэкенд `generate()` ищет | Фронтенд `chatStream()` ищет |
|--------|-----------|--------------------------|------------------------------|
| `<think{text} response` (без закрывающего тега) | ollama `_post()`, openai `chat_stream()`/`chat()`, lmstudio `chat_stream()` | `re.findall(r"<think[\s\S]*?</think>")` — **НЕ НАХОДИТ** | `<think` / `</think>` — **НЕ НАХОДИТ** |
| `<think>...</think>` | Никто не генерирует (только парсится) | Бэкенд ищет (regex) | Фронтенд ищет (state machine) |
| Без тегов | ollama `chat_stream()` (нет вывода thinking) | — | — |

**Следствие:** Thinking никогда не отделяется от контента в стриминговом режиме. Текст размышлений попадает в ответ модели как обычный текст. На фронтенде не показывается блок "Размышления модели".

**Пример:** OpenAI стримит `<think reasoning text response`, бэкенд ищет `</think>` → `thinking_full` пуст → фронтенд показывает всё как контент.

---

### 2. Ollama `chat_stream()` не читает поле `thinking` из чанков

**Файл:** `backend/providers/ollama.py:166`

**Проблема:** В стриминговом режиме Ollama присылает поле `thinking` в каждом чанке NDJSON, но `chat_stream()` читает только `message.content`:

```python
delta = chunk.get("message", {}).get("content", "")  # thinking игнорируется
yield delta
```

При этом не-стриминговый метод `_post()` (строка 41-43) thinking захватывает:

```python
t = chunk.get("thinking", "") or parsed.get("thinking", "") or ""
if t:
    thinking_parts.append(t)
```

**Следствие:** В стриминговом режиме Ollama thinking полностью отсутствует. В не-стриминговом — работает (через `_post()`).

---

### 3. Метрики токенов: неконсистентная структура `__LMSTATS__`

**Файлы:** `backend/providers/ollama.py:168-180`, `backend/providers/openai.py:91-96`, `backend/providers/lmstudio.py:90-95`

**Проблема:** Каждый провайдер отдаёт разный набор полей в `__LMSTATS__`:

| Поле | Ollama | OpenAI | LMStudio |
|------|--------|--------|----------|
| `input_tokens` | `prompt_eval_count` | `prompt_tokens` | ? |
| `output_tokens` | `eval_count` | `completion_tokens` | ? |
| `tokens_per_second` | вычисляется из `eval_duration` | отсутствует | ? |
| `time_to_first_token_seconds` | из `total_duration` | отсутствует | ? |

В `generate()` (строка 551-559) эти поля смешиваются:
- `reasoning_tokens` берётся как `reasoning_output_tokens` — есть только у OpenAI (и называется иначе)
- `lm_tokens_per_sec` — есть только у Ollama
- `ttft` — есть только у Ollama

Фронтенд использует `lm_tokens_per_sec` как флаг "показать расширенную статистику" — для OpenAI/LMStudio детали не отображаются, даже если провайдер прислал бы данные.

---

### 4. Agent mode: опечатки и путаница форматов

**Файл:** `backend/main.py:421, 461-462`

**Проблема:**

**`emit_agent()` (строка 421):**
```python
content_only = thinking_full.replace(" thinking", "").replace(" response", "")
```
Опечатка: `" thinking"` вместо `"<think"`. Ничего не заменяет.

**`stream_agent()` (строка 461):**
```python
content_only = thinking_full.replace("<think>", "").replace("</think>", "")
```
Заменяет формат 2 (`<think>...</think>`), но `_extract_thinking()` (строка 459) использует формат 1 (`<think... response`). Несоответствие форматов.

---

## HIGH

### 5. Фронтенд парсит thinking дублирующе (и неверно)

**Файл:** `frontend/src/api.ts:119-181`

**Проблема:** Фронтенд самостоятельно парсит `<think>`/`</think>` во время стриминга (state machine), хотя бэкенд в `done`-событии уже присылает готовые `full` и `thinking` поля.

Парсинг на фронтенде:
- Ищет `<think` → `</think>` (формат 2)
- Провайдеры отдают `<think... response` (формат 1)
- Фронтенд входит в режим thinking на `<think` и никогда не выходит (нет `</think>`)

**Следствие:** Весь последующий стриминг уходит в `onThinking`, реальный контент не отображается до `done`.

---

### 6. Отсутствует `.env` — провайдеры работают с дефолтами

**Файл:** `backend/config.py`

**Проблема:** `load_dotenv()` загружает `backend/.env`, которого нет. Есть только `.env.example`. Бэкенд работает с дефолтными значениями `os.getenv()`, которые могут не соответствовать реальной инфраструктуре.

---

### 7. Ollama `chat()` (не-стриминг) всегда использует stream внутри

**Файл:** `backend/providers/ollama.py:72`

**Проблема:** В `chat()` тело запроса содержит `"stream": True`, и парсинг идёт через NDJSON в `_post()`. Это избыточно для не-стримингового вызова — можно было бы отправить `stream: False` и получить обычный JSON.

---

### 8. Agent mode: метрики считаются по словам, не по токенам

**Файл:** `backend/main.py:424, 433`

**Проблема:** В `emit_agent()` и `stream_agent()` метрики `tokens` и `output_tokens` считаются как `len(words)` или `token_count` (количество чанков от провайдера), а не реальные токены. Нет `input_tokens`, `lm_tokens_per_sec` и т.д.

---

### 9. ChatPage.tsx: `cleanThinking` для русских моделей

**Файл:** `frontend/src/pages/ChatPage.tsx:429, 500`

**Проблема:** `cleanThinking()` использует `text.replace(/^<think\s*/i, '')` — предполагает латинский `<think`. Для моделей, которые могут использовать кириллические теги (или их отсутствие), очистка может не сработать.

---

## MEDIUM

### 10. Нет проверки работающего ChromaDB при старте

**Файл:** `backend/main.py`

**Проблема:** При старте нет проверки, доступна ли ChromaDB. Ошибки RAG проявляются только при первом поиске. Пользователь видит ошибку в рантайме, а не при запуске.

---

### 11. Состояние гонки: `current_provider` и `current_config`

**Файл:** `backend/main.py:39-41`

**Проблема:** `current_provider` и `current_config` — глобальные переменные. Несмотря на `_provider_lock` для endpoint-ов провайдера, запросы на `/api/chat` и `/api/chat/stream` не используют этот лок, и могут прочитать провайдера в момент переключения.

---

### 12. LMStudio: нестандартный API `/api/v1/chat`

**Файл:** `backend/providers/lmstudio.py`

**Проблема:** LMStudio Native API использует нестандартный формат:
- Не `messages`/OpenAI format, а `"input": "System: ...\nUser: ...\nAssistant: ..."`
- Не `max_tokens`, а `max_output_tokens`
- Не `stream: True` в теле, а SSE с кастомными событиями (`reasoning.delta`, `message.delta`, `chat.end`)
- API endpoint — `/api/v1/chat`, а не `/v1/chat/completions`

При переключении с OpenAI-совместимого на Native API у пользователей с LMStudio часто ломается подключение, если указан неверный `base_url`.

---

### 13. Non-streaming chat в agent mode не разделяет thinking

**Файл:** `backend/main.py:330-343`

**Проблема:** В agent mode при `content is None and msgs` вызывается `chat()`, и результат проходит `_extract_thinking()`. Но если после `_run_agent_loop` контент уже есть (строка 338), thinking извлекается повторно — и может быть уже пуст, если был извлечён внутри `_run_agent_loop`.

---

### 14. Ошибки стриминга не доходят до фронтенда

**Файл:** `frontend/src/api.ts:112-114`

**Проблема:** Если стриминг прерывается середине (обрыв соединения, таймаут прокси), фронтенд получает `done: true` от ReadableStream, но событие `done` так и не приходит. `loading` остаётся `true`, интерфейс застывает. Нет таймаута на стриминг.

---

### 15. `mcp_host.is_ready` не сбрасывается при ошибке

**Файл:** `backend/mcp_host.py`

**Проблема:** Если MCP-сервер упал после того, как стал ready, `is_ready` остаётся `True`. Агентный режим продолжает пытаться вызывать `_run_agent_loop`, который падает с исключением, и падает на fallback chat без уведомления.
