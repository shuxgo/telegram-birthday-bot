# Cloudflare Workers deployment

Эта версия бота работает нативно на Cloudflare Workers:

- Telegram webhook принимает команды админа;
- D1 хранит именинников, филиалы, настройки и журнал публикаций;
- Workers KV хранит исходные фотографии и PNG-шаблон;
- Cron Trigger запускает проверку публикаций каждую минуту;
- WebAssembly собирает фотографию и прозрачный PNG в итоговую открытку.

## Администратор и секреты

Главный администратор уже указан в `wrangler.jsonc`:

- `OWNER_ID=426250217`;
- `ADMIN_IDS=426250217` — оставлен для обратной совместимости.

Главный администратор может назначать и снимать модераторов через кнопку **Модераторы**. Модераторы имеют тот же доступ к именинникам, филиалам и настройкам публикации, но не могут управлять другими модераторами.

В **Workers & Pages → telegram-birthday-bot → Settings → Variables and Secrets** используются:

- `BOT_TOKEN` — редактируемый секрет; замените заглушку токеном из BotFather;
- `WEBHOOK_SECRET` — сгенерированный случайный секрет для проверки запросов Telegram.

Затем зарегистрируйте webhook:

```bash
curl -X POST https://telegram-birthday-bot.<your-subdomain>.workers.dev/setup-webhook \
  -H "Authorization: Bearer <WEBHOOK_SECRET>"
```

Пока настоящий токен не добавлен, `/health` отвечает успешно с `configured: false`, а Telegram-функции отключены.
