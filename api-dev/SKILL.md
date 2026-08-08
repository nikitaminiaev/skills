---
name: api-dev
description: Инструкции для разработки и тестирования API (SberBusiness, PHP/Symfony)
---

# API Dev — Инструкции для разработки и тестирования

При активации также загрузи навык jivo-dev-testing — там общие инструкции по удаленному тестированию через tmux.

## Путь проекта на dev сервере

```
/var/www/api/current/api/
```

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

## Типовые проблемы и решения

1. **"Пожалуйста, попробуйте ещё раз"** — ошибка в `ProcessSignUpService::process()`. Проверь debug-лог в `var/tmp/sber_debug.log`.
2. **Duplicate entry** — уникальные поля (`inn`, `sub`). Добавь timestamp к значению.
3. **Opcache** — после изменения файлов перезапусти php-fpm.
4. **Симлинк current** — релизы деплоятся в `/var/www/api/releases/`, `current` — это symlink. Правки нужно делать через него.
