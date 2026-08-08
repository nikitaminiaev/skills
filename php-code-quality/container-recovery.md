# Восстановление docker-контейнера для PHPStan (аварийный сценарий)

Читать ТОЛЬКО когда `phpstan` (или `bin/console cache:clear`) в контейнере падает. В обычном потоке не применяется.

## Симптом

- `Container /app/jivo/api/var/cache/dev/AppKernelDevDebugContainer.xml does not exist`
- `bin/console`: `Symfony Runtime is missing`
- `composer install` сыпется на платформенных проверках

Пояснение: phpstan-symfony требует дамп `var/cache/dev/AppKernelDevDebugContainer.xml`
(см. `container_xml_path` в `phpstan.neon`); его генерирует `bin/console cache:clear --env=dev` (как в CI).
В контейнере это ломается, потому что:
- vendor устарел и не соответствует `composer.lock` (нет `symfony/runtime`, поэтому `bin/console` падает);
- `composer.lock` собран под **PHP 8.5**, а в контейнере **PHP 8.3** (поэтому `composer install` начисто не проходит).

## Восстановление

### 1. Установить vendor с обходом платформенных проверок (в контейнере)

```bash
docker exec dockerforjivo-php8.3-1 bash -lc 'cd api && composer install --no-interaction --no-progress --ignore-platform-req=php --ignore-platform-req=ext-gd'
```

Упадёт на `post-install-cmd` (`bin/console cache:clear`) — это ожидаемо, но vendor уже обновится.
Если composer упадёт на других пакетах — добавлять `--ignore-platform-req=<пакет/php>`.

### 2. Временно отключить `doctrine.orm.enable_native_lazy_objects`

В `app/config/config_dev.yml` (требует PHP 8.4, в контейнере 8.3). Добавить в конец файла:

```yaml
doctrine:
    orm:
        enable_native_lazy_objects: false
```

### 3. Временно заменить `src/Shared/TracerBundle/TracedRedis.php` заглушкой

Его сигнатуры несовместимы с phpredis 5.3.4 в контейнере (`fatal: must be compatible with Redis::bitpos`).
Файл и так в `excludePaths` phpstan, так что заглушка не влияет на анализ:

```php
<?php

namespace Shared\TracerBundle;

use Redis;
use Shared\TracerBundle\Service\TraceService;

class TracedRedis extends Redis
{
    public function __construct(private readonly Redis $redis, private readonly TraceService $traceService)
    {
        parent::__construct();
    }
}
```

Конструктор обязателен — сервис декларируется с named-аргументом `$redis` (декоратор `snc_redis.sharxy`).

### 4. Залить временные файлы и сгенерировать кеш

```bash
docker cp app/config/config_dev.yml dockerforjivo-php8.3-1:/app/jivo/api/app/config/config_dev.yml
docker cp src/Shared/TracerBundle/TracedRedis.php dockerforjivo-php8.3-1:/app/jivo/api/src/Shared/TracerBundle/TracedRedis.php
docker exec dockerforjivo-php8.3-1 bash -lc 'cd api && php -d memory_limit=2G bin/console cache:clear --env=dev'
```

После успеха в `var/cache/dev/` появится `AppKernelDevDebugContainer.xml` (~6.5 MB).

### 5. Откатить временные правки (на хосте и в контейнере)

```bash
git checkout app/config/config_dev.yml
# вернуть оригинал TracedRedis.php (если был бэкап — cp из него)
docker cp app/config/config_dev.yml dockerforjivo-php8.3-1:/app/jivo/api/app/config/config_dev.yml
docker cp src/Shared/TracerBundle/TracedRedis.php dockerforjivo-php8.3-1:/app/jivo/api/src/Shared/TracerBundle/TracedRedis.php
```

Убедиться, что `git status` показывает только легитимные изменения (фиксы phpcbf и т.п.).

### 6. Повторить phpstan

```bash
docker exec dockerforjivo-php8.3-1 bash -lc 'cd api && php vendor/bin/phpstan analyse --memory-limit=8G $(git diff --name-only --diff-filter=d master...)'
```