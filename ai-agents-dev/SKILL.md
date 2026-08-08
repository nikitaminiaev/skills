---
name: ai-agents-dev
description: Инструкции для тестирования AI агентов — API эндпоинты, логирование, отладка
---

# AI Agents Dev — Инструкции для разработки и тестирования

При активации также загрузи навык jivo-dev-testing — там общие инструкции по удаленному тестированию через tmux.

**ВАЖНО:** Полное тестирование с MySQL и Milvus выполняется на удаленном dev сервере через tmux сессию.
проект всегда лежит в /var/www/ai_agents

## Основные API эндпоинты

### Agents (Ассистенты)

#### Создание ассистента
```bash
curl -X POST "http://localhost:8000/assistants" \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": 123,
    "ai_provider_name": "SberAi",
    "model": "gpt-4.1-mini",
    "temperature": 0.7,
    "instructions": "You are a helpful assistant"
  }'
```

#### Получение информации об ассистенте
```bash
curl -X GET "http://localhost:8000/assistants/{assistant_id}"
```

#### Обновление ассистента
```bash
curl -X POST "http://localhost:8000/assistants/{assistant_id}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Assistant",
    "instructions": "You are an updated helpful assistant"
  }'
```

#### Удаление ассистента
```bash
curl -X DELETE "http://localhost:8000/assistants/{assistant_id}"
```

### Threads (Потоки сообщений)

#### Создание потока
```bash
curl -X POST "http://localhost:8000/threads" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "Hello, world!"
      }
    ]
  }'
```

#### Получение информации о потоке
```bash
curl -X GET "http://localhost:8000/threads/{thread_id}"
```

#### Добавление сообщения в поток
```bash
curl -X POST "http://localhost:8000/threads/{thread_id}/messages" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "user",
    "content": "What is the weather today?"
  }'
```

#### Получение сообщений потока
```bash
curl -X GET "http://localhost:8000/threads/{thread_id}/messages"
```

### Runs (Запуски)

#### Создание и запуск выполнения
```bash
curl -X POST "http://localhost:8000/threads/{thread_id}/runs" \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "456",
    "model": "gpt-4.1-mini",
    "instructions": "Please answer the user question"
  }'
```

#### Получение информации о запуске
```bash
curl -X GET "http://localhost:8000/runs/{run_id}"
```

#### Отмена запуска
```bash
curl -X POST "http://localhost:8000/runs/{run_id}/cancel"
```

#### Отправка результатов инструментов
```bash
curl -X POST "http://localhost:8000/runs/{run_id}/submit_tool_outputs" \
  -H "Content-Type: application/json" \
  -d '{
    "tool_outputs": [
      {
        "tool_call_id": "call_123",
        "output": "Result from tool execution"
      }
    ]
  }'
```

### Vector Stores (Векторные хранилища)

#### Создание векторного хранилища
```bash
curl -X POST "http://localhost:8000/vector_stores" \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": 1,
    "site_id": 123,
    "vector_dimension": 1536
  }'
```

#### Получение информации о хранилище
```bash
curl -X GET "http://localhost:8000/vector_stores/{vector_store_id}"
```

#### Загрузка файла в хранилище
```bash
curl -X POST "http://localhost:8000/vector_stores/{vector_store_id}/files" \
  -F "file=@/path/to/document.pdf" \
  -F "chunking_strategy=auto" 
```

#### Удаление файла из хранилища
```bash
curl -X DELETE "http://localhost:8000/vector_stores/{vector_store_id}/files/{file_id}"
```

### System (Системные эндпоинты)

#### Проверка здоровья системы
```bash
curl -X GET "http://localhost:8000/health"
```

**Пример ответа:**
```json
{
  "ok": true,
  "statuses": {
    "openai": "ok",
    "deepseek": "ok"
  }
}
```

#### Получение информации о приложении
```bash
curl -X GET "http://localhost:8000/info"
```

## Логирование и отладка

### Просмотр логов контейнера

```bash
# Просмотр логов ai-agents-server контейнера
docker compose logs --tail=100 ai-agents-server

# Просмотр логов в реальном времени
docker compose logs -f ai-agents-server

# Просмотр логов всех сервисов
docker compose logs -f

# Просмотр логов за последние 100 строк
docker compose logs --tail=100 ai-agents-server
```

### Структура логов

Логи содержат следующую информацию:
- **Создание/обновление агентов**: `site_id`, `ai_agent_id`
- **Операции с потоками**: `thread_id`, `message_id`
- **Запуски и статусы**: `run_id`, `status`
- **Ошибки**: полный стек вызовов
- **Здоровье LLM провайдеров**: OpenAI, DeepSeek статусы
- **Метаданные**: контекстные данные операций

### Примеры логов

```
2024-01-15 10:30:15 - ai.src.api.presentation.controller.agent.create_agent - INFO - Creating agent - {"site_id": 123, "ai_provider_name": "SberAi"}
2024-01-15 10:30:16 - ai.src.api.application.agent_service - INFO - Agent created successfully - {"ai_agent_id": "asst_456", "site_id": 123}
2024-01-15 10:30:20 - ai.src.llm_agents.openai_client - ERROR - OpenAI API error - {"error": "rate_limit", "retry_after": 60}
```

## Частые сценарии тестирования

### 1. Тестирование создания ассистента

```bash
# 1. Создаем ассистента
curl -X POST "http://localhost:8000/assistants" \
  -H "Content-Type: application/json" \
  -d '{"site_id": 123, "ai_provider_name": "SberAi", "model": "gpt-4"}'

# 2. Проверяем логи
docker compose logs --tail=10 ai-agents-server

# 3. Проверяем в БД
docker exec mysql mysql -u root -p -e "SELECT * FROM ai_agents WHERE site_id = 123;"
```

### 2. Тестирование RAG функциональности

```bash
# 1. Создаем векторное хранилище
curl -X POST "http://localhost:8000/vector_stores" \
  -H "Content-Type: application/json" \
  -d '{"assistant_id": 1, "site_id": 123, "vector_dimension": 1536}'

# 2. Загружаем файл
curl -X POST "http://localhost:8000/vector_stores/vs_1_123/files" \
  -F "file=@test_document.pdf"

# 3. Проверяем обработку файла
docker compose logs --tail=20 ai-agents-server | grep "file"
```

### 3. Тестирование полного цикла

```bash
# 1. Создаем ассистент
ASSISTANT_ID=$(curl -s -X POST "http://localhost:8000/assistants" \
  -H "Content-Type: application/json" \
  -d '{"site_id": 123, "ai_provider_name": "SberAi", "model": "gpt-4"}' | \
  jq -r '.id')

# 2. Создаем поток
THREAD_ID=$(curl -s -X POST "http://localhost:8000/threads" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello!"}]}' | \
  jq -r '.id')

# 3. Запускаем выполнение
curl -X POST "http://localhost:8000/threads/$THREAD_ID/runs" \
  -H "Content-Type: application/json" \
  -d "{\"assistant_id\": \"$ASSISTANT_ID\"}"

# 4. Наблюдаем за логами
docker compose logs -f ai-agents-server
```

## Полезные команды

### Работа с Docker

```bash
# Перезапуск конкретного сервиса
docker compose restart ai-agents-server

# Пересборка образа
docker compose up --build ai-agents-server

# Вход в контейнер
docker exec -it ai-agents-server bash

# Просмотр ресурсов
docker stats
```

### Мониторинг

```bash
# Просмотр состояния всех сервисов
docker compose ps
```

## Отладка проблем

### Проблема: API не отвечает
```bash
# 1. Проверяем статус контейнера
docker compose ps

# 2. Смотрим логи ошибок
docker compose logs ai-agents-server | grep ERROR

# 3. Проверяем порт
netstat -tlnp | grep 8000
```

### Проблема: Milvus не работает
```bash
# 1. Проверяем статус Milvus
docker compose ps milvus

# 2. Проверяем подключение
docker exec milvus python -c "
from pymilvus import connections
connections.connect('default', host='localhost', port='19530')
print('Milvus connection OK')
"

# 3. Смотрим логи Milvus
docker compose logs milvus
```

---

При возникновении проблем сначала проверьте логи, затем статус контейнеров, и только потом перезапускайте сервисы.
