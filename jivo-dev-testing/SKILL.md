---
name: jivo-dev-testing
description: Общие инструкции для удаленного тестирования на dev серверах Jivo
---

# Jivo Dev Testing — Инструкции для разработки и тестирования

## Удаленное тестирование

Полное тестирование выполняется на удаленном dev сервере через tmux сессию.

### Посылай команды к серверу этим способом:

```bash
tmux send-keys -t {name}
```

Потом захват вывода например так:
```bash
sleep 1 && tmux capture-pane -t {name}:0 -p | tail -20
```

### Если команда слишком длинная:

Передавай через PHP base64 decode на сервере:
```bash
b64=$(cat /tmp/opencode/file.b64)
tmux send-keys -t dev "php83 -r 'file_put_contents(\"path/to/target/file.php\", base64_decode(\"$b64\"));'"
```

Или записывай во временный файл на сервере через heredoc, потом раскодируй.

### Если нужно проверить синтаксис PHP на сервере:

```bash
php83 -l path/to/file.php
```

## Release-based deployment

Код на dev сервере лежит в `/var/www/api/releases/`, симлинк `current` указывает на активный релиз:
```
/var/www/api/current -> /var/www/api/releases/API_xxx.xxxxxxxxx
```

Файлы проекта — в `/var/www/api/current/api/`. Изменения в локальной директории разработки **не отражаются** на сервере — все правки нужно делать через tmux в release-директории.

## Очистка кеша

```bash
rm -rf var/cache/dev/*
```

После изменения файлов может потребоваться рестарт php-fpm для сброса opcache:
```bash
sudo systemctl restart php83-php-fpm
```

## Debug-логи

Для отладки без Graylog используй `file_put_contents` в `var/tmp/sber_debug.log` (относительный путь от корня проекта). Пример:
```php
file_put_contents('var/tmp/debug.log', sprintf("[%s] ...\n", date('H:i:s')), FILE_APPEND);
```

Директория `var/tmp/` должна существовать и быть доступна для записи.

## Запуск тестов

```bash
cd /var/www/api/current/api && sudo -u apache php83 -d memory_limit=2G vendor/bin/phpunit --group=sberBusiness --testdox
```

## Типовые проблемы

1. **Opcache** — после изменения PHP-файлов старые версии могут быть закешированы. Решение: `sudo systemctl restart php83-php-fpm`
2. **Уникальность данных** — при повторном запуске тестов/запросов могут возникать `Duplicate entry` ошибки. Решение: добавлять timestamp к уникальным полям или очищать данные между тестами.
