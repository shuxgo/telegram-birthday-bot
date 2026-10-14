# Cloudflare Workers deployment

Эта версия бота работает нативно на Cloudflare Workers:

- Telegram webhook принимает команды админа;
- D1 хранит именинников, филиалы, настройки и журнал публикаций;
- Workers KV хранит исходные фотографии и PNG-шаблон;
- Cron Trigger запускает проверку публикаций каждую минуту;
- WebAssembly собирает фотографию и прозрачный PNG в итоговую открытку.

## Секреты

После деплоя добавьте три секрета в **Workers & Pages → telegram-birthday-bot → Settings → Variables and Secrets**:

- `BOT_TOKEN` — токен из BotFather;
- `ADMIN_IDS` — Telegram ID админов через запятую;
- `WEBHOOK_SECRET` — длинная случайная строка.

Затем зарегистрируйте webhook:

```bash
curl -X POST https://telegram-birthday-bot.<your-subdomain>.workers.dev/setup-webhook \
  -H "Authorization: Bearer <WEBHOOK_SECRET>"
```

Пока секреты не добавлены, `/health` отвечает успешно, но Telegram-функции отключены.
