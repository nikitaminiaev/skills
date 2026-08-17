---
name: api-dev
description: Инструкции для разработки и тестирования API (SberBusiness, PHP/Symfony): пути на dev-сервере, запуск тестов, release-деплой, кеш/opcache, debug-логи, типовые проблемы.
---

# API Dev — Инструкции для разработки и тестирования

При активации также загрузи навык jivo-dev-testing — там общая tmux-механика
для удаленного тестирования на dev-серверах Jivo.

## Путь проекта на dev сервере

```
/var/www/api/current/api/
```

## Release-based deployment

Код на dev сервере лежит в `/var/www/api/releases/`, симлинк `current` указывает на активный релиз:
```
/var/www/api/current -> /var/www/api/releases/API_xxx.xxxxxxxxx
```

Файлы проекта — в `/var/www/api/current/api/`. Изменения в локальной директории разработки **не отражаются** на сервере — все правки нужно делать через tmux в release-директории.

## Команды

### Запуск тестов SberBusiness

```bash
cd /var/www/api/current/api && sudo -u apache php85 -d memory_limit=2G vendor/bin/phpunit --group=sberBusiness --testdox
```

### Запуск конкретного теста

```bash
cd /var/www/api/current/api && sudo -u apache php85 -d memory_limit=2G vendor/bin/phpunit --filter=TestName --group=sberBusiness
```

### Проверка синтаксиса PHP

```bash
php85 -l src/Path/To/File.php
```

### Очистка кеша Symfony

```bash
rm -rf var/cache/dev/*
```

### Рестарт php-fpm (сброс opcache)

```bash
sudo systemctl restart php85-php-fpm
```

## Структура тестов

- `tests/Sber/Application/Service/SberBusiness/` — сервисные тесты
- `tests/Sber/Presentation/Controller/SberBusiness/` — контроллер тесты
- Аннотация `@group functional` + `@group sberBusiness`
- Базовый класс: `Shared\TestBundle\Utils\AbstractFunctionalTestCase`

## Dev моки для SberBusiness

Для замены внешних Sber API вызовов используется `CreateSberBusinessMock`:
- Регистрируется в `services_dev.yml` через оверрайд интерфейса `CreateSberBusinessInterface`
- Мок загружается только в dev-окружении (`SberExtension.php`, проверка `Environment::isDev`)
- Поле `inn` должно быть уникальным — используй timestamp

## Debug-логи

Для отладки без Graylog используй `file_put_contents` в `var/tmp/sber_debug.log` (относительный путь от корня проекта). Пример:
```php
file_put_contents('var/tmp/debug.log', sprintf("[%s] ...\n", date('H:i:s')), FILE_APPEND);
```

Директория `var/tmp/` должна существовать и быть доступна для записи.
Детальные правила записи логов — в скилле `file-log-debug`.

## Типовые проблемы и решения

1. **"Пожалуйста, попробуйте ещё раз"** — ошибка в `ProcessSignUpService::process()`. Проверь debug-лог в `var/tmp/sber_debug.log`.
2. **Duplicate entry** — уникальные поля (`inn`, `sub`). Добавь timestamp к значению.
3. **Opcache** — после изменения PHP-файлов старые версии могут быть закешированы. Решение: `sudo systemctl restart php85-php-fpm`.
4. **Симлинк current** — релизы деплоятся в `/var/www/api/releases/`, `current` — это symlink. Правки нужно делать через него.