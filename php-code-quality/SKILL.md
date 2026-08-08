---
name: php-code-quality
description: Прогон PHPCS (phpcs/phpcbf) и PHPStan по изменённым файлам ветки относительно master через docker-контейнер dockerforjivo-php8.3-1. git — на хосте, проверки — в контейнере.
---
# PHP Code Quality — проверка кода через docker-контейнер (phpcs / phpcbf / phpstan)

Назначение: прогнать PHPCS и PHPStan по изменённым файлам ветки относительно `master`.
PHP есть **только в docker-контейнере** `dockerforjivo-php8.3-1`, поэтому проверки выполняются в нём.
Все git-операции — **снаружи, на хосте**, из каталога проекта `api`.

## Пути и окружение

- Контейнер: `dockerforjivo-php8.3-1`; путь к проекту в нём: `/app/jivo/api` (внутри `cd api`)
- Рабочие файлы проекта синхронизируются с хостом в контейнер автоматически
- PHP в контейнере: 8.3.30 (внимание: `composer.lock` собран под PHP 8.5)

## Порядок действий

### 1. Обновить master (на хосте, вне контейнера)

Проверки завязаны на свежий `master`.

```bash
git fetch origin && git checkout master && git pull origin master
git checkout <своя-ветка>
```

> Проверки работают только на feature-ветке. На `master` `git diff master...` пуст.

### 2. PHPCS — проверка стиля (в контейнере)

```bash
docker exec dockerforjivo-php8.3-1 bash -lc 'cd api && php vendor/bin/phpcs $(git diff --name-only --diff-filter=d master...)'
```

### 3. PHPCBF — автофикс стиля (в контейнере)

Если phpcs нашёл ошибки с меткой `[x]` (автоисправимые) — исправить и повторить phpcs до чистого результата:

```bash
docker exec dockerforjivo-php8.3-1 bash -lc 'cd api && php vendor/bin/phpcbf $(git diff --name-only --diff-filter=d master...)'
```

> Файлы после phpcbf — легитимные правки, коммитятся в свою ветку.

### 4. PHPStan — статический анализ (в контейнере)

```bash
docker exec dockerforjivo-php8.3-1 bash -lc 'cd api && php vendor/bin/phpstan analyse --memory-limit=8G $(git diff --name-only --diff-filter=d master...)'
```

### 5. Финальная проверка

После любых правок кода — повторно прогнать phpcs и phpstan по изменённым файлам.

## Сбой контейнера (только при падении)

Если phpstan падает на отсутствии `var/cache/dev/AppKernelDevDebugContainer.xml`,
либо `bin/console` на «Symfony Runtime is missing», либо `composer install` сыпется на платформенных проверках —
читать и выполнять **`container-recovery.md` в этой же папке скилла**. В обычном потоке он не нужен.

## Важные правила

- **Git — только снаружи, с хоста.** В контейнере git-операции с remote не работают (нет ssh-ключей).
- **phpcs/phpcbf/phpstan — только в контейнере** (php есть только там).
- Если всплывает **конфликт** (git merge/rebase) — **не решать самостоятельно, эскалировать пользователю**.
- Проверки запускать на **feature-ветке**, master должен быть свежим (шаг 1).