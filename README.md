# Pythia

Личный Telegram-бот для анализа до трёх Reels публичного Instagram-профиля или отдельного Reel по ссылке. Он получает лайки и комментарии, скачивает видео через yt-dlp, извлекает аудио и 8 кадров через ffmpeg, а затем использует OpenAI для транскрипции и смыслового анализа. Бот отправляет ключевой кадр и отчёт в Telegram; видео, аудио и кадры не хранятся после выполнения задачи.

## Возможности MVP

- `/analyze <ссылка на профиль или Reel>` или просто ссылка в личном чате.
- Только один заранее заданный Telegram ID может запускать обработку.
- До трёх свежих публичных Reels: лайки, комментарии, речь, текст на экране, темы, hook и CTA.
- История запусков, метаданные и текстовый анализ в Supabase Postgres.
- Один анализ за раз; активная задача не восстанавливается после рестарта, но помечается прерванной.

## Режимы запуска

Есть два независимых профиля — выбирайте один:

- **Raspberry Pi + Supabase** — контейнер бота на Pi, управляемая PostgreSQL в Supabase. Использует [docker-compose.yml](docker-compose.yml) и `.env`.
- **Полностью локальный** — контейнеры бота и PostgreSQL на одной машине. Использует [docker-compose.local.yml](docker-compose.local.yml) и `.env.local`.

Для профиля список Reels пока получает Instaloader; скачивание каждого видео выполняет yt-dlp. Прямая ссылка `https://www.instagram.com/reel/<код>/` обрабатывается без Instaloader и session-файла. Просмотры и рейтинг по ним отключены, в базе просмотры сохраняются как NULL.

В обоих случаях нужны Telegram Bot Token и OpenAI API key. Instagram session — опциональна: без неё бот пытается обработать только публичные данные без авторизации.

Для поиска Reels по профилю можно создать session-файл на доверенной машине командой Instaloader с интерактивным логином, затем скопируйте созданный файл в `secrets/instagram.session`. Не добавляйте пароль или session-файл в Git. Контейнер читает каталог `secrets/` только в режиме read-only; при правах `600` передайте файлу владельца UID `10001` (`sudo chown 10001:10001 secrets/instagram.session`).

Если session не нужна, оставьте `INSTAGRAM_USERNAME` и `INSTAGRAM_SESSION_FILE` пустыми. В таком режиме закрытые профили недоступны, а Instagram может чаще ограничивать запросы или не отдавать часть метрик.

### Raspberry Pi + Supabase

```sh
cp .env.example .env
mkdir -p secrets
# заполните .env: укажите строку подключения Supabase
docker compose build
docker compose run --rm bot alembic upgrade head
docker compose up -d
```

В этом режиме локальный контейнер PostgreSQL не создаётся. `.env.example` содержит обычный Supabase URL; приложение преобразует его для asyncpg.

### Полностью локальный Docker-стенд

```sh
cp .env.local.example .env.local
mkdir -p secrets
# заполните токены и модели в .env.local
docker compose -f docker-compose.local.yml up --build
```

Compose сам запускает PostgreSQL, ждёт его healthcheck, применяет Alembic-миграции сервисом `migrate`, и только затем запускает бот. Локальная база доступна на `localhost:5432` и сохраняет данные в Docker volume `pythia-local-postgres`. Для удаления вместе с данными: `docker compose -f docker-compose.local.yml down -v`.

Логи в любом режиме: `docker compose … logs -f bot`.

## Локальная разработка

```sh
uv sync --all-groups
# сначала поднимите только локальную БД командой выше
set -a; source .env.local; set +a
uv run alembic upgrade head
uv run pytest
uv run pythia
```

При прямом локальном запуске `.env.local` указывает на `localhost`; внутри локального Docker-стенда Compose заменяет адрес на сервис `db`. `DATABASE_URL` может быть стандартным Supabase PostgreSQL URL; приложение само адаптирует его для async SQLAlchemy. Миграции — единственный механизм изменения схемы базы данных.

В приложении и миграциях параметр URL `sslmode` автоматически преобразуется в `ssl` для asyncpg с сохранением режима (например, `sslmode=require` → `ssl=require`). Если указаны оба параметра, их значения должны совпадать; конфликт приводит к ошибке конфигурации. Для локального URL без SSL-параметров настройки SSL не добавляются.

## Ограничения

Используйте только публичные профили и соблюдайте правила Instagram и применимое законодательство. Поиск по профилю всё ещё зависит от Instaloader и может завершаться `feedback_required`; переход на yt-dlp исправляет только этап скачивания. В этом случае можно отправить прямую ссылку на Reel. yt-dlp также не гарантирует доступ к любому ролику. Максимальный размер загрузки — 100 MiB для файлов с известным размером. Instagram может ограничить запросы; бот сообщит об этом вместо бесконечных повторов. Этот MVP не подписывается на аккаунты и не выполняет анализ по расписанию.
