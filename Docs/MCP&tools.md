# Архитектура и спецификация MCP-сервера для ChromaDB

По современным стандартам Anthropic MCP, код работы с базой данных ChromaDB должен быть полностью изолирован внутри **MCP Server**. Ваш бэкенд (FastAPI) будет выступать в роли **MCP Host**, который запускает этот сервер как подпроцесс (через `stdio`) и ничего не знает о внутреннем устройстве ChromaDB.

---

## 1. Структура проекта (Модуль ChromaDB MCP)

Рекомендуется выделить логику работы с базой в отдельную директорию со следующей структурой:

```text
chromadb_mcp/
├── __init__.py
├── server.py          # Основной код MCP-сервера и регистрация инструментов
└── db_manager.py      # Чистая логика инициализации ChromaDB и поиска
```

---

## 2. Реализация компонентов (Код)

Для работы вам понадобятся официальные библиотеки:
```bash
pip install mcp chromadb
```

### 2.1. Менеджер базы данных (`db_manager.py`)
Этот модуль инкапсулирует работу с коллекциями ChromaDB, чтобы не смешивать её с кодом самого протокола MCP.

```python
import os
import chromadb
from typing import Dict, List, Any

class ChromaManager:
    def __init__(self, db_path: str = "./chroma_db"):
        # Инициализируем локальную персистентную БД
        self.client = chromadb.PersistentClient(path=db_path)

    def list_existing_collections(self) -> List[str]:
        """Возвращает список имен всех доступных коллекций."""
        collections = self.client.list_collections()
        return [col.name for col in collections]

    def query_collection(self, collection_name: str, query_text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Ищет релевантные документы в указанной коллекции."""
        try:
            collection = self.client.get_collection(name=collection_name)
            results = collection.query(
                query_texts=[query_text],
                n_results=n_results
            )
            
            # Форматируем сырой ответ ChromaDB в плоский список словарей
            formatted_results = []
            if results and results.get("documents"):
                docs = results["documents"]
                metadatas = results.get("metadatas", [[]])
                ids = results.get("ids", [[]])
                
                for idx, doc in enumerate(docs):
                    formatted_results.append({
                        "id": ids[idx] if idx < len(ids) else None,
                        "content": doc,
                        "metadata": metadatas[idx] if idx < len(metadatas) else {}
                    })
            return formatted_results
        except Exception as e:
            raise ValueError(f"Ошибка при поиске в коллекции '{collection_name}': {str(e)}")
```

### 2.2. MCP Сервер (`server.py`)
Этот модуль регистрирует инструменты (Tools) и ресурсы (Resources). Модель `gemma4-e4b` будет видеть именно эти декларации. Используется стандартный транспорт `stdio`.

```python
import asyncio
import os
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server

from db_manager import ChromaManager

# 1. Инициализируем сервер и менеджер БД
server = Server("chromadb-mcp-server")
db = ChromaManager(db_path=os.getenv("CHROMA_DB_PATH", "./chroma_db"))

# 2. Декларируем РЕСУРСЫ: показываем модели, какие коллекции существуют в системе
@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """Предоставляет модели список коллекций в виде доступных ресурсов."""
    collections = db.list_existing_collections()
    return [
        types.Resource(
            uri=f"chromadb://collections/{name}",
            name=f"Коллекция ChromaDB: {name}",
            description=f"Локальные векторные данные из коллекции {name}",
            mimeType="text/plain"
        )
        for name in collections
    ]

# 3. Декларируем ИНСТРУМЕНТЫ: даем модели возможность искать по коллекциям
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Описывает доступные инструменты для модели (схемы аргументов)."""
    return [
        types.Tool(
            name="search_chromadb_collection",
            description="Поиск релевантной информации, документов или контекста в конкретной коллекции ChromaDB.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_name": {
                        "type": "string",
                        "description": "Имя коллекции в ChromaDB, в которой нужно произвести поиск."
                    },
                    "query": {
                        "type": "string",
                        "description": "Смысловой (семантический) поисковый запрос пользователя."
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Количество возвращаемых документов (по умолчанию 3).",
                        "default": 3
                    }
                },
                "required": ["collection_name", "query"]
            }
        )
    ]

# 4. Обработчик вызова инструмента (Исполнение логики)
@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """Выполняет поиск в ChromaDB, когда модель запрашивает инструмент."""
    if name != "search_chromadb_collection":
        raise ValueError(f"Неизвестный инструмент: {name}")
        
    if not arguments:
        raise ValueError("Отсутствуют аргументы для вызова инструмента")

    collection_name = arguments.get("collection_name")
    query = arguments.get("query")
    n_results = arguments.get("n_results", 3)

    try:
        search_results = db.query_collection(
            collection_name=collection_name, 
            query_text=query, 
            n_results=n_results
        )
        
        if not search_results:
            return [types.TextContent(type="text", text="В данной коллекции ничего не найдено по вашему запросу.")]

        # Формируем текстовый ответ, который вернется в контекст модели
        response_lines = [f"Результаты поиска в коллекции '{collection_name}':"]
        for item in search_results:
            response_lines.append(f"\n--- Документ ID: {item['id']} ---")
            response_lines.append(f"Контент: {item['content']}")
            if item['metadata']:
                response_lines.append(f"Метаданные: {item['metadata']}")
                
        return [types.TextContent(type="text", text="\n".join(response_lines))]

    except Exception as e:
        return [types.TextContent(type="text", text=f"Ошибка выполнения инструмента: {str(e)}")]

# 5. Точка входа для запуска сервера через stdio транспорт
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="chromadb-mcp-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 3. Как это работает в связке с вашим FastAPI Host

Когда ваш FastAPI бэкенд (Host) запускается, он инициализирует этот MCP-сервер как подпроцесс:

1. **Host** отправляет системную команду запуска: `python chromadb_mcp/server.py`.
2. **Host** запрашивает `list_tools()` через stdio-поток и получает JSON-схему инструмента `search_chromadb_collection`.
3. При отправке запроса в Ollama/LM Studio ваш FastAPI прикрепляет эту схему в массив `tools`.
4. Если `gemma4-e4b` решает, что ей нужны данные из базы, она возвращает структуру:
   ```json
   {
     "name": "search_chromadb_collection", 
     "arguments": {"collection_name": "users_docs", "query": "правила отпуска"}
   }
   ```
5. FastAPI перенаправляет этот JSON в поток `stdin` нашего запущенного MCP-сервера. Сервер отрабатывает функцию `handle_call_tool`, делает запрос в ChromaDB и отдает чистый текст обратно в FastAPI (`stdout`), который затем досылается в модель.
