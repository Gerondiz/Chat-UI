# Актуальные проблемы

## RESOLVED

### ✓ 1. Thinking-теги: конфликт форматов между провайдерами, бэкендом и фронтендом

**Статус:** Исправлено

**Файлы:** `backend/providers/ollama.py`, `backend/main.py`

**Что было:** Провайдеры использовали разные форматы тегов думания, бэкенд и фронтенд искали разные паттерны. Thinking никогда не отделялся от контента в стриминге.

**Что сделано:**
- Ollama `chat_stream()` теперь отдаёт каждый thinking-токен отдельно (не накапливает), обёрнутый в `<think>`/`</think>` маркеры
- `_extract_thinking()` использует regex `<think[\s\S]*?</think>` в первую очередь
- Фронтенд парсит `<think>`/`</think>` state machine корректно
- `emit_agent()` стримит `<think>` → слова думания → `</think>` перед контентом

---

### ✓ 2. Ollama `chat_stream()` не читает поле `thinking` из чанков

**Статус:** Исправлено

**Файл:** `backend/providers/ollama.py`

**Что было:** В стриминговом режиме Ollama присылает `thinking` в чанках, но `chat_stream()` читала только `message.content`.

**Что сделано:** `chat_stream()` теперь читает `chunk.get("thinking")` или `msg.get("thinking")`, и если есть думание — отдаёт его как `<think>`... токены прогрессивно, без аккумулирования.

---

### ✓ 3. Метрики токенов: неконсистентная структура `__LMSTATS__`

**Статус:** Исправлено

**Файлы:** `backend/providers/ollama.py`, `backend/providers/openai.py`, `backend/providers/lmstudio.py`, `backend/main.py`, `frontend/src/pages/ChatPage.tsx`

**Что было:** Каждый провайдер отдаёт разный набор полей в `__LMSTATS__`. `lm_tokens_per_sec` есть только у Ollama, но `generate()` всегда устанавливал его (в 0 для OpenAI/LMStudio). Фронтенд через truthy-check `lm_tokens_per_sec ?` падал на вторую ветку при 0.

**Что сделано:**
- `generate()` устанавливает `lm_tokens_per_sec` и `ttft` только когда провайдер их прислал
- Фронтенд проверяет `typeof === 'number'` вместо truthy
- Если провайдер не прислал `lm_tokens_per_sec` — показывается `output_tokens / output_time_sec / tokens_per_sec` из backend-тайминга

---

### ✓ 4. Agent mode: опечатки и путаница форматов

**Статус:** Исправлено

**Файл:** `backend/main.py`

**Что было:** Опечатки в `emit_agent()` (`" thinking"` вместо `"<think"`), несоответствие форматов в `stream_agent()`.

**Что сделано:**
- `_extract_thinking()` полностью переписан: regex на первом месте, хрупкая эвристика " response" отодвинута
- `emit_agent()` использует `_extract_thinking()` корректно
- `asyncio.sleep(0.03)` между словами для ненулевых метрик

---

### ✓ 5. Фронтенд парсит thinking дублирующе

**Статус:** Исправлено

**Файл:** `frontend/src/api.ts`

**Что было:** Фронтенд парсил `<think>`/`</think>` вручную с dead-кодом (`raw`, `isFirstContent`).

**Что сделано:** Удалены мёртвые переменные (`raw`, `isFirstContent`), упрощена логика state machine. Фронтенд по-прежнему парсит маркеры для прогрессивного отображения думания во время стриминга, но код чище.

---

### ✓ 6. Agent mode: метрики считаются по словам, не по токенам

**Статус:** Исправлено

**Файл:** `backend/main.py`

**Что было:** В `emit_agent()` метрики `time_sec` = 0 (все слова за один чанк), `tokens_per_sec` = 0.

**Что сделано:** `asyncio.sleep(0.03)` между словами — `elapsed > 0`, метрики ненулевые.

---

### ✓ 7. Non-streaming chat в agent mode не разделяет thinking

**Статус:** Исправлено

**Файл:** `backend/main.py`

**Что было:** В агентском режиме при отсутствии контента думание не попадало в ответ.

**Что сделано:** Fallback во всех трёх путях (`generate()`, `pass_through()`, `emit_agent()`):
```python
if not content_only.strip() and thinking_full:
    content_only = thinking_full.replace("<think>", "").replace("</think>", "")
    thinking_full = ""
```

---

### ✓ 8. Состояние гонки: `current_provider` и `current_config`

**Статус:** Исправлено

**Файл:** `backend/main.py` → `backend/state.py`, `backend/routes/`

**Что было:** Глобальные переменные `current_provider` и `current_config` на уровне модуля. Потенциальная гонка между переключением провайдера и запросами чата.

**Что сделано:** Состояние вынесено в `AppState` (`state.py`), хранится в `app.state.state`. Provider routes используют async lock. Chat routes не блокируются на каждый токен — показывают last-known-good провайдера (атомарная замена через `state.set()`).

---

### ✓ 9. `mcp_host.is_ready` не сбрасывается при ошибке

**Статус:** Исправлено

**Файл:** `backend/mcp_host.py`

**Что было:** При ошибке старта `start()` вызывал `self._ready.set()`, из-за чего `is_ready` возвращал `True` даже при падении MCP.

**Что сделано:** Убран вызов `self._ready.set()` в обработчике исключения `start()`. При ошибке `_ready` остаётся невзведённым → `wait_ready(20)` таймаутит → `is_ready = False` → агентный режим корректно переходит на fallback.

---

## HIGH

### 10. Отсутствует `.env` — провайдеры работают с дефолтами

**Файл:** `backend/config.py`

**Проблема:** `load_dotenv()` загружает `backend/.env`, которого нет. Есть только `.env.example`. Бэкенд работает с дефолтными значениями `os.getenv()`, которые могут не соответствовать реальной инфраструктуре.

---

### 11. Ollama `chat()` (не-стриминг) всегда использует stream внутри

**Файл:** `backend/providers/ollama.py:72`

**Проблема:** В `chat()` тело запроса содержит `"stream": True`, и парсинг идёт через NDJSON в `_post()`. Это избыточно для не-стримингового вызова — можно было бы отправить `stream: False` и получить обычный JSON.

---

### 12. ChatPage.tsx: `cleanThinking` для русских моделей

**Файл:** `frontend/src/pages/ChatPage.tsx`

**Проблема:** `cleanThinking()` использует `text.replace(/^<think\s*/i, '')` — предполагает латинский `<think`. Для моделей, которые могут использовать кириллические теги (или их отсутствие), очистка может не сработать.

---

## MEDIUM

### 13. Нет проверки работающего ChromaDB при старте

**Файл:** `backend/main.py`

**Проблема:** При старте нет проверки, доступна ли ChromaDB. Ошибки RAG проявляются только при первом поиске. Пользователь видит ошибку в рантайме, а не при запуске.

---

### 14. LMStudio: нестандартный API `/api/v1/chat`

**Файл:** `backend/providers/lmstudio.py`

**Проблема:** LMStudio Native API использует нестандартный формат:
- Не `messages`/OpenAI format, а `"input": "System: ...\nUser: ...\nAssistant: ..."`
- Не `max_tokens`, а `max_output_tokens`
- Не `stream: True` в теле, а SSE с кастомными событиями (`reasoning.delta`, `message.delta`, `chat.end`)
- API endpoint — `/api/v1/chat`, а не `/v1/chat/completions`

При переключении с OpenAI-совместимого на Native API у пользователей с LMStudio часто ломается подключение, если указан неверный `base_url`.

---

### 15. Ошибки стриминга не доходят до фронтенда

**Файл:** `frontend/src/api.ts`

**Проблема:** Если стриминг прерывается середине (обрыв соединения, таймаут прокси), фронтенд получает `done: true` от ReadableStream, но событие `done` так и не приходит. `loading` остаётся `true`, интерфейс застывает. Нет таймаута на стриминг.
