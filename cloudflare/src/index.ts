import {
  PhotonImage,
  SamplingFilter,
  crop,
  resize,
  watermark,
} from "@cf-wasm/photon/workerd";

interface Env {
  DB: D1Database;
  MEDIA: KVNamespace;
  BOT_TOKEN?: string;
  ADMIN_IDS?: string;
  OWNER_ID?: string;
  WEBHOOK_SECRET?: string;
}

type Row = Record<string, string | number | null>;
type InlineButton = { text: string; callback_data: string };
type InlineKeyboard = { inline_keyboard: InlineButton[][] };

interface TgUser { id: number; username?: string; first_name?: string; last_name?: string }
interface TgPhoto { file_id: string; width: number; height: number }
interface TgDocument { file_id: string; file_name?: string; mime_type?: string }
interface TgChat { id: number; title?: string; username?: string; type?: string }
interface TgMessage {
  message_id: number;
  from?: TgUser;
  chat: TgChat;
  text?: string;
  photo?: TgPhoto[];
  document?: TgDocument;
  forward_origin?: { type: string; chat?: TgChat; sender_user?: TgUser };
}
interface TgCallback {
  id: string;
  from: TgUser;
  data?: string;
  message?: TgMessage;
}
interface TgUpdate { message?: TgMessage; callback_query?: TgCallback }

const MONTHS = [
  "января", "февраля", "марта", "апреля", "мая", "июня",
  "июля", "августа", "сентября", "октября", "ноября", "декабря",
];

function mainMenu(owner = false): InlineKeyboard {
  return { inline_keyboard: [
    [{ text: "➕ Добавить именинника", callback_data: "menu:add" }],
    [{ text: "🎂 Именинники", callback_data: "menu:birthdays" }],
    [
      { text: "🏢 Филиалы", callback_data: "menu:branches" },
      { text: "⚙️ Настройки", callback_data: "menu:settings" },
    ],
    ...(owner ? [[{ text: "👥 Модераторы", callback_data: "menu:moderators" }]] : []),
  ] };
}
const cancelKeyboard: InlineKeyboard = {
  inline_keyboard: [[{ text: "✖️ Отмена", callback_data: "cancel" }]],
};
const menuBack: InlineKeyboard = {
  inline_keyboard: [[{ text: "⬅️ В главное меню", callback_data: "menu:main" }]],
};

function html(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function ownerIds(env: Env): Set<number> {
  const configured = [env.OWNER_ID ?? "", env.ADMIN_IDS ?? ""].join(",");
  return new Set(configured.split(",").map((v) => Number(v.trim())).filter((v) => Number.isSafeInteger(v) && v > 0));
}

function isOwner(env: Env, userId: number): boolean {
  return ownerIds(env).has(userId);
}

async function hasAccess(env: Env, userId: number): Promise<boolean> {
  if (isOwner(env, userId)) return true;
  const row = await env.DB.prepare("SELECT 1 allowed FROM moderators WHERE user_id=?").bind(userId).first<{ allowed: number }>();
  return Boolean(row?.allowed);
}

function validBotToken(token?: string): boolean {
  return /^\d{6,12}:[A-Za-z0-9_-]{30,}$/.test(token ?? "");
}

async function tg<T = unknown>(env: Env, method: string, payload: Record<string, unknown>): Promise<T> {
  if (!env.BOT_TOKEN) throw new Error("BOT_TOKEN is not configured");
  const response = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json<{ ok: boolean; result: T; description?: string }>();
  if (!body.ok) throw new Error(body.description ?? `Telegram ${method} failed`);
  return body.result;
}

async function sendMessage(env: Env, chatId: number | string, text: string, keyboard?: InlineKeyboard): Promise<void> {
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    ...(keyboard ? { reply_markup: keyboard } : {}),
  });
}

async function sendPhotoFile(env: Env, chatId: number | string, fileId: string, caption: string, keyboard?: InlineKeyboard): Promise<void> {
  await tg(env, "sendPhoto", {
    chat_id: chatId,
    photo: fileId,
    caption,
    parse_mode: "HTML",
    ...(keyboard ? { reply_markup: keyboard } : {}),
  });
}

async function sendPhotoBytes(env: Env, chatId: number | string, bytes: Uint8Array, caption: string, keyboard?: InlineKeyboard): Promise<void> {
  if (!env.BOT_TOKEN) throw new Error("BOT_TOKEN is not configured");
  const form = new FormData();
  form.set("chat_id", String(chatId));
  form.set("caption", caption);
  form.set("parse_mode", "HTML");
  if (keyboard) form.set("reply_markup", JSON.stringify(keyboard));
  const arrayBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
  form.set("photo", new Blob([arrayBuffer], { type: "image/jpeg" }), "birthday.jpg");
  const response = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/sendPhoto`, {
    method: "POST",
    body: form,
  });
  const body = await response.json<{ ok: boolean; description?: string }>();
  if (!body.ok) throw new Error(body.description ?? "Telegram sendPhoto failed");
}

async function answerCallback(env: Env, callbackId: string, text?: string, alert = false): Promise<void> {
  await tg(env, "answerCallbackQuery", {
    callback_query_id: callbackId,
    ...(text ? { text } : {}),
    show_alert: alert,
  });
}

async function settings(env: Env): Promise<Record<string, string>> {
  const result = await env.DB.prepare("SELECT key, value FROM settings").all<{ key: string; value: string }>();
  return Object.fromEntries(result.results.map((row) => [row.key, row.value]));
}

async function setSetting(env: Env, key: string, value: string): Promise<void> {
  await env.DB.prepare(
    "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
  ).bind(key, value).run();
}

async function getSession(env: Env, adminId: number): Promise<{ state: string; data: Record<string, unknown> } | null> {
  const row = await env.DB.prepare("SELECT state, data FROM sessions WHERE admin_id=?")
    .bind(adminId).first<{ state: string; data: string }>();
  return row ? { state: row.state, data: JSON.parse(row.data) as Record<string, unknown> } : null;
}

async function setSession(env: Env, adminId: number, state: string, data: Record<string, unknown> = {}): Promise<void> {
  await env.DB.prepare(
    "INSERT INTO sessions(admin_id,state,data) VALUES(?,?,?) " +
    "ON CONFLICT(admin_id) DO UPDATE SET state=excluded.state,data=excluded.data,updated_at=CURRENT_TIMESTAMP",
  ).bind(adminId, state, JSON.stringify(data)).run();
}

async function clearSession(env: Env, adminId: number): Promise<void> {
  await env.DB.prepare("DELETE FROM sessions WHERE admin_id=?").bind(adminId).run();
}

function parseDate(input: string): string | null {
  const match = input.trim().replaceAll("/", ".").replaceAll("-", ".")
    .match(/^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?$/);
  if (!match) return null;
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3] ?? 2000);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  return `${year.toString().padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function displayDate(iso: string): string {
  const [, month, day] = iso.split("-").map(Number);
  return `${day} ${MONTHS[month - 1]}`;
}

function renderCaption(template: string, row: Row): string {
  return template
    .replaceAll("{name}", html(row.name))
    .replaceAll("{position}", html(row.position))
    .replaceAll("{branch}", html(row.branch_name))
    .replaceAll("{date}", displayDate(String(row.birth_date)));
}

function birthdaySummary(row: Row): string {
  return `<b>${html(row.name)}</b>\n📅 ${displayDate(String(row.birth_date))}\n💼 ${html(row.position)}\n🏢 ${html(row.branch_name)}`;
}

async function downloadTelegramFile(env: Env, fileId: string): Promise<Uint8Array> {
  const file = await tg<{ file_path: string }>(env, "getFile", { file_id: fileId });
  const response = await fetch(`https://api.telegram.org/file/bot${env.BOT_TOKEN}/${file.file_path}`);
  if (!response.ok) throw new Error("Could not download Telegram file");
  return new Uint8Array(await response.arrayBuffer());
}

async function composeCard(env: Env, photoKey: string, templateKey: string): Promise<Uint8Array> {
  const [photoBytes, templateBytes] = await Promise.all([
    env.MEDIA.get(photoKey, "arrayBuffer"), env.MEDIA.get(templateKey, "arrayBuffer"),
  ]);
  if (!photoBytes) throw new Error("Source photo is missing in KV");
  if (!templateBytes) return new Uint8Array(photoBytes);
  const source = PhotonImage.new_from_byteslice(new Uint8Array(photoBytes));
  const overlay = PhotonImage.new_from_byteslice(new Uint8Array(templateBytes));
  let scaled: PhotonImage | undefined;
  let base: PhotonImage | undefined;
  try {
    const targetWidth = overlay.get_width();
    const targetHeight = overlay.get_height();
    const ratio = Math.max(targetWidth / source.get_width(), targetHeight / source.get_height());
    const width = Math.ceil(source.get_width() * ratio);
    const height = Math.ceil(source.get_height() * ratio);
    scaled = resize(source, width, height, SamplingFilter.Lanczos3);
    const left = Math.floor((width - targetWidth) / 2);
    const top = Math.floor((height - targetHeight) / 2);
    base = crop(scaled, left, top, left + targetWidth, top + targetHeight);
    watermark(base, overlay, 0n, 0n);
    return base.get_bytes_jpeg(92);
  } finally {
    base?.free();
    scaled?.free();
    overlay.free();
    source.free();
  }
}

async function showMain(env: Env, chatId: number, userId: number): Promise<void> {
  const role = isOwner(env, userId) ? "главный администратор" : "модератор";
  await sendMessage(
    env,
    chatId,
    `🎉 <b>Бот поздравлений</b>\n\nРоль: <b>${role}</b>. Добавляйте именинников, управляйте филиалами и публикациями.`,
    mainMenu(isOwner(env, userId)),
  );
}

async function showModerators(env: Env, chatId: number): Promise<void> {
  const result = await env.DB.prepare(
    "SELECT user_id,username,full_name FROM moderators ORDER BY COALESCE(full_name,username,CAST(user_id AS TEXT)) COLLATE NOCASE",
  ).all<{ user_id: number; username: string | null; full_name: string | null }>();
  const owner = [...ownerIds(env)][0];
  const lines = result.results.map((row) => {
    const name = row.full_name || (row.username ? `@${row.username}` : String(row.user_id));
    return `• <b>${html(name)}</b> — <code>${row.user_id}</code>`;
  });
  const keyboard: InlineKeyboard = { inline_keyboard: [
    [{ text: "➕ Назначить модератора", callback_data: "moderator:add" }],
    ...result.results.map((row) => [{ text: `🗑 Снять ${row.full_name || row.username || row.user_id}`, callback_data: `moderator:remove:${row.user_id}` }]),
    [{ text: "⬅️ Назад", callback_data: "menu:main" }],
  ] };
  await sendMessage(
    env,
    chatId,
    `👥 <b>Модераторы</b>\n\nГлавный администратор: <code>${owner ?? "не настроен"}</code>\n\n${lines.length ? lines.join("\n") : "Модераторов пока нет."}`,
    keyboard,
  );
}

async function branchKeyboard(env: Env, prefix: string): Promise<InlineKeyboard> {
  const result = await env.DB.prepare("SELECT id,name FROM branches ORDER BY name COLLATE NOCASE").all<Row>();
  return {
    inline_keyboard: [
      ...result.results.map((row) => [{ text: `🏢 ${row.name}`, callback_data: `${prefix}:${row.id}` }]),
      [{ text: "✖️ Отмена", callback_data: "cancel" }],
    ],
  };
}

async function birthdayRow(env: Env, id: number): Promise<Row | null> {
  return env.DB.prepare(
    "SELECT bd.*, b.name branch_name FROM birthdays bd JOIN branches b ON b.id=bd.branch_id WHERE bd.id=?",
  ).bind(id).first<Row>();
}

async function showBirthday(env: Env, chatId: number, id: number): Promise<void> {
  const row = await birthdayRow(env, id);
  if (!row) return sendMessage(env, chatId, "Запись не найдена.", menuBack);
  const keyboard: InlineKeyboard = { inline_keyboard: [
    [{ text: "✏️ Редактировать", callback_data: `birthday:edit:${id}` }, { text: "🗑 Удалить", callback_data: `birthday:delete:${id}` }],
    [{ text: "⬅️ К спискам", callback_data: "menu:birthdays" }],
  ] };
  const config = await settings(env);
  try {
    const card = await composeCard(env, String(row.photo_key), config.template_key);
    await sendPhotoBytes(env, chatId, card, birthdaySummary(row), keyboard);
  } catch {
    await sendPhotoFile(env, chatId, String(row.photo_file_id), birthdaySummary(row), keyboard);
  }
  await sendMessage(env, chatId, "<b>Текст будущего поста:</b>\n" + renderCaption(config.caption_template, row));
}

async function handleStateMessage(env: Env, message: TgMessage, state: { state: string; data: Record<string, unknown> }): Promise<boolean> {
  const adminId = message.from!.id;
  const chatId = message.chat.id;
  const text = message.text?.trim();
  const next = async (name: string, data = state.data) => setSession(env, adminId, name, data);

  if (state.state === "add_photo") {
    if (!message.photo?.length) { await sendMessage(env, chatId, "Пришлите изображение как фото.", cancelKeyboard); return true; }
    const photo = message.photo.at(-1)!;
    const bytes = await downloadTelegramFile(env, photo.file_id);
    const key = `photos/${crypto.randomUUID()}.jpg`;
    await env.MEDIA.put(key, bytes);
    await next("add_name", { photo_key: key, photo_file_id: photo.file_id });
    await sendMessage(env, chatId, "Шаг 2 из 5. Введите имя и фамилию.", cancelKeyboard);
    return true;
  }
  if (state.state === "add_name") {
    if (!text || text.length < 2 || text.length > 120) { await sendMessage(env, chatId, "Введите имя длиной от 2 до 120 символов."); return true; }
    await next("add_date", { ...state.data, name: text });
    await sendMessage(env, chatId, "Шаг 3 из 5. Введите дату: <b>ДД.ММ</b> или <b>ДД.ММ.ГГГГ</b>.", cancelKeyboard);
    return true;
  }
  if (state.state === "add_date") {
    const date = text ? parseDate(text) : null;
    if (!date) { await sendMessage(env, chatId, "Некорректная дата. Используйте ДД.ММ или ДД.ММ.ГГГГ."); return true; }
    await next("add_position", { ...state.data, birth_date: date });
    await sendMessage(env, chatId, "Шаг 4 из 5. Введите должность или специализацию.", cancelKeyboard);
    return true;
  }
  if (state.state === "add_position") {
    if (!text || text.length < 2 || text.length > 160) { await sendMessage(env, chatId, "Введите должность длиной от 2 до 160 символов."); return true; }
    await next("add_branch", { ...state.data, position: text });
    await sendMessage(env, chatId, "Шаг 5 из 5. Выберите филиал:", await branchKeyboard(env, "addbranch"));
    return true;
  }
  if (state.state === "branch_name") {
    if (!text || text.length < 2 || text.length > 100) { await sendMessage(env, chatId, "Название должно содержать от 2 до 100 символов."); return true; }
    try {
      await env.DB.prepare("INSERT INTO branches(name) VALUES(?)").bind(text).run();
      await clearSession(env, adminId);
      await sendMessage(env, chatId, "✅ Филиал добавлен.", mainMenu(isOwner(env, adminId)));
    } catch { await sendMessage(env, chatId, "Такой филиал уже существует."); }
    return true;
  }
  if (state.state === "moderator_add") {
    if (!isOwner(env, adminId)) {
      await clearSession(env, adminId);
      await sendMessage(env, chatId, "Только главный администратор может назначать модераторов.");
      return true;
    }
    const forwarded = message.forward_origin?.type === "user" ? message.forward_origin.sender_user : undefined;
    const targetId = forwarded?.id ?? (text && /^\d{5,15}$/.test(text) ? Number(text) : undefined);
    if (!targetId || !Number.isSafeInteger(targetId)) {
      await sendMessage(env, chatId, "Перешлите сообщение пользователя или отправьте его числовой Telegram ID.", cancelKeyboard);
      return true;
    }
    if (isOwner(env, targetId)) {
      await sendMessage(env, chatId, "Этот пользователь уже является главным администратором.");
      return true;
    }
    const fullName = forwarded ? [forwarded.first_name, forwarded.last_name].filter(Boolean).join(" ") || null : null;
    await env.DB.prepare(
      "INSERT INTO moderators(user_id,username,full_name,added_by) VALUES(?,?,?,?) " +
      "ON CONFLICT(user_id) DO UPDATE SET username=COALESCE(excluded.username,moderators.username),full_name=COALESCE(excluded.full_name,moderators.full_name),added_by=excluded.added_by",
    ).bind(targetId, forwarded?.username ?? null, fullName, adminId).run();
    await clearSession(env, adminId);
    await sendMessage(env, chatId, `✅ Пользователь <code>${targetId}</code> назначен модератором.`);
    await showModerators(env, chatId);
    return true;
  }
  if (state.state.startsWith("edit_")) {
    const id = Number(state.data.birthday_id);
    const field = state.state.slice(5);
    if (field === "photo") {
      if (!message.photo?.length) { await sendMessage(env, chatId, "Пришлите новое изображение как фото."); return true; }
      const photo = message.photo.at(-1)!;
      const bytes = await downloadTelegramFile(env, photo.file_id);
      const key = `photos/${crypto.randomUUID()}.jpg`;
      await env.MEDIA.put(key, bytes);
      await env.DB.prepare("UPDATE birthdays SET photo_key=?,photo_file_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?")
        .bind(key, photo.file_id, id).run();
    } else {
      if (!text) { await sendMessage(env, chatId, "Пришлите значение текстом."); return true; }
      let value = text;
      if (field === "birth_date") {
        const parsed = parseDate(text);
        if (!parsed) { await sendMessage(env, chatId, "Некорректная дата."); return true; }
        value = parsed;
      }
      const allowed: Record<string, string> = { name: "name", birth_date: "birth_date", position: "position" };
      if (!allowed[field]) return true;
      await env.DB.prepare(`UPDATE birthdays SET ${allowed[field]}=?,updated_at=CURRENT_TIMESTAMP WHERE id=?`).bind(value, id).run();
    }
    await clearSession(env, adminId);
    await sendMessage(env, chatId, "✅ Данные обновлены.");
    await showBirthday(env, chatId, id);
    return true;
  }
  if (state.state === "settings_channel") {
    let channel: string | number | undefined = message.forward_origin?.type === "channel" ? message.forward_origin.chat?.id : undefined;
    if (!channel && text && (text.startsWith("@") || /^-?\d+$/.test(text))) channel = /^-?\d+$/.test(text) ? Number(text) : text;
    if (!channel) { await sendMessage(env, chatId, "Перешлите сообщение из канала или укажите @username / -100…"); return true; }
    try {
      const target = await tg<TgChat>(env, "getChat", { chat_id: channel });
      const me = await tg<TgUser>(env, "getMe", {});
      const member = await tg<{ status: string; can_post_messages?: boolean }>(env, "getChatMember", { chat_id: target.id, user_id: me.id });
      if (target.type !== "channel" || !["administrator", "creator"].includes(member.status) || (member.status === "administrator" && !member.can_post_messages)) {
        await sendMessage(env, chatId, "Бот должен быть администратором канала с правом публикации."); return true;
      }
      await setSetting(env, "channel_id", String(target.id));
      await setSetting(env, "channel_title", target.title ?? target.username ?? String(target.id));
      await clearSession(env, adminId);
      await sendMessage(env, chatId, `✅ Канал «<b>${html(target.title ?? target.username ?? target.id)}</b>» сохранён.`, mainMenu(isOwner(env, adminId)));
    } catch (error) { await sendMessage(env, chatId, `Не удалось проверить канал: ${html(error)}`); }
    return true;
  }
  if (state.state === "settings_template") {
    const document = message.document;
    if (!document || !document.file_name?.toLowerCase().endsWith(".png")) { await sendMessage(env, chatId, "Пришлите PNG как документ, чтобы сохранить прозрачность."); return true; }
    const bytes = await downloadTelegramFile(env, document.file_id);
    try {
      const image = PhotonImage.new_from_byteslice(bytes);
      const valid = image.get_width() >= 300 && image.get_height() >= 300;
      image.free();
      if (!valid) throw new Error("минимальный размер 300×300");
      const key = `templates/${crypto.randomUUID()}.png`;
      await env.MEDIA.put(key, bytes);
      await setSetting(env, "template_key", key);
      await clearSession(env, adminId);
      await sendMessage(env, chatId, "✅ PNG-шаблон сохранён и будет применён к будущим публикациям.", mainMenu(isOwner(env, adminId)));
    } catch (error) { await sendMessage(env, chatId, `Шаблон не принят: ${html(error)}`); }
    return true;
  }
  if (state.state === "settings_caption") {
    if (!text || text.length > 900 || /\{(?!name\}|position\}|branch\}|date\})/.test(text)) { await sendMessage(env, chatId, "Текст некорректен или содержит неизвестные переменные."); return true; }
    await setSetting(env, "caption_template", text);
    await clearSession(env, adminId);
    await sendMessage(env, chatId, "✅ Текст поздравления сохранён.", mainMenu(isOwner(env, adminId)));
    return true;
  }
  if (state.state === "settings_time") {
    const match = text?.match(/^(\d{1,2}):(\d{2})$/);
    if (!match || Number(match[1]) > 23 || Number(match[2]) > 59) { await sendMessage(env, chatId, "Введите время в формате ЧЧ:ММ."); return true; }
    const value = `${match[1].padStart(2, "0")}:${match[2]}`;
    await setSetting(env, "publish_time", value);
    await clearSession(env, adminId);
    await sendMessage(env, chatId, `✅ Время публикации изменено на ${value}.`, mainMenu(isOwner(env, adminId)));
    return true;
  }
  return false;
}

async function handleMessage(env: Env, message: TgMessage): Promise<void> {
  if (!message.from || !await hasAccess(env, message.from.id)) {
    await sendMessage(env, message.chat.id, "⛔️ У вас нет доступа к этому боту.");
    return;
  }
  if (message.text === "/start" || message.text === "/menu") {
    await clearSession(env, message.from.id);
    await showMain(env, message.chat.id, message.from.id);
    return;
  }
  const session = await getSession(env, message.from.id);
  if (session && await handleStateMessage(env, message, session)) return;
  await sendMessage(env, message.chat.id, "Используйте меню управления:", mainMenu(isOwner(env, message.from.id)));
}

async function showBranches(env: Env, chatId: number): Promise<void> {
  const result = await env.DB.prepare(
    "SELECT b.id,b.name,COUNT(bd.id) count FROM branches b LEFT JOIN birthdays bd ON bd.branch_id=b.id GROUP BY b.id ORDER BY b.name",
  ).all<Row>();
  const keyboard: InlineKeyboard = { inline_keyboard: [
    [{ text: "➕ Добавить филиал", callback_data: "branch:add" }],
    ...result.results.map((r) => [{ text: `🗑 ${r.name} (${r.count})`, callback_data: `branch:delete:${r.id}` }]),
    [{ text: "⬅️ Назад", callback_data: "menu:main" }],
  ] };
  await sendMessage(env, chatId, "🏢 <b>Филиалы</b>\n\nФилиал с именинниками удалить нельзя.", keyboard);
}

async function showMonth(env: Env, chatId: number, offset: number): Promise<void> {
  const config = await settings(env);
  const nowParts = zonedParts(new Date(), config.timezone);
  const date = new Date(Date.UTC(nowParts.year, nowParts.month - 1 + offset, 1));
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth() + 1;
  const result = await env.DB.prepare(
    "SELECT bd.*,b.name branch_name FROM birthdays bd JOIN branches b ON b.id=bd.branch_id WHERE CAST(substr(birth_date,6,2) AS INTEGER)=? ORDER BY substr(birth_date,9,2),bd.name",
  ).bind(month).all<Row>();
  const text = result.results.length
    ? [`📅 <b>Именинники — ${MONTHS[month - 1]} ${year}</b>`, ...result.results.map((r) => `${displayDate(String(r.birth_date))} — <b>${html(r.name)}</b>, ${html(r.position)}, ${html(r.branch_name)}`)].join("\n\n")
    : `📅 <b>Именинники — ${MONTHS[month - 1]} ${year}</b>\n\nЗаписей нет.`;
  const keyboard: InlineKeyboard = { inline_keyboard: [
    ...result.results.slice(0, 90).map((r) => [{ text: `${String(r.birth_date).slice(8)} · ${r.name}`, callback_data: `birthday:view:${r.id}` }]),
    [{ text: "⬅️ К разделу", callback_data: "menu:birthdays" }],
  ] };
  await sendMessage(env, chatId, text.slice(0, 4000), keyboard);
}

async function showAll(env: Env, chatId: number): Promise<void> {
  const result = await env.DB.prepare("SELECT id,name,birth_date FROM birthdays ORDER BY substr(birth_date,6),name LIMIT 90").all<Row>();
  const keyboard: InlineKeyboard = { inline_keyboard: [
    ...result.results.map((r) => [{ text: `${String(r.birth_date).slice(5).split("-").reverse().join(".")} · ${r.name}`, callback_data: `birthday:view:${r.id}` }]),
    [{ text: "⬅️ К разделу", callback_data: "menu:birthdays" }],
  ] };
  await sendMessage(env, chatId, result.results.length ? "🔎 <b>Все именинники</b>" : "Именинников пока нет.", keyboard);
}

async function handleCallback(env: Env, callback: TgCallback): Promise<void> {
  const chatId = callback.message?.chat.id;
  const data = callback.data ?? "";
  if (!chatId) return;
  if (!await hasAccess(env, callback.from.id)) { await answerCallback(env, callback.id, "Нет доступа", true); return; }
  const ownerOnly = data === "menu:moderators" || data === "moderator:add" || data.startsWith("moderator:remove:");
  if (ownerOnly && !isOwner(env, callback.from.id)) { await answerCallback(env, callback.id, "Только для главного администратора", true); return; }
  await answerCallback(env, callback.id);
  if (data === "cancel" || data === "menu:main") { await clearSession(env, callback.from.id); await showMain(env, chatId, callback.from.id); return; }
  if (data === "menu:moderators") { await clearSession(env, callback.from.id); await showModerators(env, chatId); return; }
  if (data === "moderator:add") {
    await setSession(env, callback.from.id, "moderator_add");
    await sendMessage(env, chatId, "Перешлите сообщение будущего модератора или отправьте его числовой Telegram ID.", cancelKeyboard);
    return;
  }
  if (data.startsWith("moderator:remove:")) {
    const targetId = Number(data.split(":")[2]);
    await env.DB.prepare("DELETE FROM moderators WHERE user_id=?").bind(targetId).run();
    await sendMessage(env, chatId, `✅ Доступ пользователя <code>${targetId}</code> отозван.`);
    await showModerators(env, chatId);
    return;
  }
  if (data === "menu:add") { await setSession(env, callback.from.id, "add_photo"); await sendMessage(env, chatId, "Шаг 1 из 5. Пришлите фотографию именинника.", cancelKeyboard); return; }
  if (data === "menu:birthdays") { await clearSession(env, callback.from.id); await sendMessage(env, chatId, "🎂 <b>Именинники</b>", { inline_keyboard: [
    [{ text: "📅 Текущий месяц", callback_data: "month:0" }],
    [{ text: "🗓 Следующий месяц", callback_data: "month:1" }],
    [{ text: "🔎 Все / редактировать", callback_data: "birthdays:all" }],
    [{ text: "⬅️ Назад", callback_data: "menu:main" }],
  ] }); return; }
  if (data.startsWith("month:")) { await showMonth(env, chatId, Number(data.split(":")[1])); return; }
  if (data === "birthdays:all") { await showAll(env, chatId); return; }
  if (data.startsWith("birthday:view:")) { await showBirthday(env, chatId, Number(data.split(":")[2])); return; }
  if (data.startsWith("birthday:edit:")) {
    const id = Number(data.split(":")[2]);
    await sendMessage(env, chatId, "Что изменить?", { inline_keyboard: [
      [{ text: "📷 Фото", callback_data: `birthday:field:${id}:photo` }, { text: "👤 Имя", callback_data: `birthday:field:${id}:name` }],
      [{ text: "📅 Дата", callback_data: `birthday:field:${id}:birth_date` }, { text: "💼 Должность", callback_data: `birthday:field:${id}:position` }],
      [{ text: "🏢 Филиал", callback_data: `birthday:field:${id}:branch` }],
      [{ text: "⬅️ Назад", callback_data: `birthday:view:${id}` }],
    ] }); return;
  }
  if (data.startsWith("birthday:field:")) {
    const [, , idText, field] = data.split(":");
    if (field === "branch") { await sendMessage(env, chatId, "Выберите новый филиал:", await branchKeyboard(env, `editbranch:${idText}`)); return; }
    await setSession(env, callback.from.id, `edit_${field}`, { birthday_id: Number(idText) });
    const prompts: Record<string, string> = { photo: "Пришлите новое фото.", name: "Введите новое имя.", birth_date: "Введите новую дату.", position: "Введите новую должность." };
    await sendMessage(env, chatId, prompts[field] ?? "Введите новое значение.", cancelKeyboard); return;
  }
  if (data.startsWith("editbranch:")) {
    const [, id, branchId] = data.split(":");
    await env.DB.prepare("UPDATE birthdays SET branch_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?").bind(Number(branchId), Number(id)).run();
    await showBirthday(env, chatId, Number(id)); return;
  }
  if (data.startsWith("birthday:delete:")) {
    const id = Number(data.split(":")[2]);
    await sendMessage(env, chatId, "Удалить эту запись? Действие нельзя отменить.", { inline_keyboard: [[
      { text: "Да, удалить", callback_data: `birthday:confirm_delete:${id}` },
      { text: "Нет", callback_data: `birthday:view:${id}` },
    ]] }); return;
  }
  if (data.startsWith("birthday:confirm_delete:")) {
    const id = Number(data.split(":")[2]);
    await env.DB.prepare("DELETE FROM birthdays WHERE id=?").bind(id).run();
    await sendMessage(env, chatId, "🗑 Запись удалена.", mainMenu(isOwner(env, callback.from.id))); return;
  }
  if (data.startsWith("addbranch:")) {
    const session = await getSession(env, callback.from.id);
    if (!session || session.state !== "add_branch") return;
    const id = Number(data.split(":")[1]);
    const d = session.data;
    const inserted = await env.DB.prepare("INSERT INTO birthdays(name,birth_date,position,branch_id,photo_key,photo_file_id) VALUES(?,?,?,?,?,?)")
      .bind(d.name, d.birth_date, d.position, id, d.photo_key, d.photo_file_id).run();
    await clearSession(env, callback.from.id);
    await sendMessage(env, chatId, "✅ Именинник сохранён.");
    await showBirthday(env, chatId, Number(inserted.meta.last_row_id)); return;
  }
  if (data === "menu:branches") { await clearSession(env, callback.from.id); await showBranches(env, chatId); return; }
  if (data === "branch:add") { await setSession(env, callback.from.id, "branch_name"); await sendMessage(env, chatId, "Введите название филиала.", cancelKeyboard); return; }
  if (data.startsWith("branch:delete:")) {
    const id = Number(data.split(":")[2]);
    const used = await env.DB.prepare("SELECT COUNT(*) count FROM birthdays WHERE branch_id=?").bind(id).first<{ count: number }>();
    if (used?.count) { await sendMessage(env, chatId, "Филиал нельзя удалить: в нём есть именинники."); return; }
    await env.DB.prepare("DELETE FROM branches WHERE id=?").bind(id).run();
    await showBranches(env, chatId); return;
  }
  if (data === "menu:settings") {
    await clearSession(env, callback.from.id);
    const config = await settings(env);
    await sendMessage(env, chatId, `⚙️ <b>Настройки</b>\n\n📣 Канал: <b>${html(config.channel_title ?? "не настроен")}</b>\n⏰ Время: <b>${config.publish_time}</b> (${html(config.timezone)})`, { inline_keyboard: [
      [{ text: "📣 Канал публикации", callback_data: "settings:channel" }],
      [{ text: "🖼 PNG-шаблон", callback_data: "settings:template" }],
      [{ text: "📝 Текст поздравления", callback_data: "settings:caption" }],
      [{ text: "⏰ Время публикации", callback_data: "settings:time" }],
      [{ text: "⬅️ Назад", callback_data: "menu:main" }],
    ] }); return;
  }
  if (data.startsWith("settings:")) {
    const kind = data.split(":")[1];
    await setSession(env, callback.from.id, `settings_${kind}`);
    const prompts: Record<string, string> = {
      channel: "Перешлите пост из канала или отправьте @username / -100… Бот должен быть администратором.",
      template: "Пришлите прозрачный PNG <b>как документ</b>. Рекомендуемый размер 1080×1080.",
      caption: "Отправьте текст. Переменные: <code>{name}</code>, <code>{position}</code>, <code>{branch}</code>, <code>{date}</code>.",
      time: "Введите время публикации в формате ЧЧ:ММ.",
    };
    await sendMessage(env, chatId, prompts[kind], cancelKeyboard);
  }
}

function zonedParts(date: Date, timeZone: string): { year: number; month: number; day: number; hour: number; minute: number } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date);
  const value = (type: string) => Number(parts.find((part) => part.type === type)?.value);
  return { year: value("year"), month: value("month"), day: value("day"), hour: value("hour"), minute: value("minute") };
}

async function publishDue(env: Env): Promise<void> {
  if (!env.BOT_TOKEN) return;
  const config = await settings(env);
  if (!config.channel_id) return;
  const now = zonedParts(new Date(), config.timezone ?? "Asia/Tashkent");
  const [publishHour, publishMinute] = (config.publish_time ?? "09:00").split(":").map(Number);
  if (now.hour * 60 + now.minute < publishHour * 60 + publishMinute) return;
  const result = await env.DB.prepare(
    "SELECT bd.*,b.name branch_name,pl.status,COALESCE(pl.attempt_count,0) attempts FROM birthdays bd JOIN branches b ON b.id=bd.branch_id " +
    "LEFT JOIN publication_log pl ON pl.birthday_id=bd.id AND pl.publication_year=? " +
    "WHERE CAST(substr(bd.birth_date,6,2) AS INTEGER)=? AND CAST(substr(bd.birth_date,9,2) AS INTEGER)=? " +
    "AND (pl.birthday_id IS NULL OR (pl.status='failed' AND pl.attempt_count<10 AND datetime(pl.last_attempt)<=datetime('now','-15 minutes')))",
  ).bind(now.year, now.month, now.day).all<Row>();
  for (const row of result.results) {
    try {
      const card = await composeCard(env, String(row.photo_key), config.template_key);
      await sendPhotoBytes(env, config.channel_id, card, renderCaption(config.caption_template, row));
      await env.DB.prepare(
        "INSERT INTO publication_log(birthday_id,publication_year,channel_id,status,published_at) VALUES(?,?,?,'published',CURRENT_TIMESTAMP) " +
        "ON CONFLICT(birthday_id,publication_year) DO UPDATE SET status='published',published_at=CURRENT_TIMESTAMP,error=NULL,last_attempt=CURRENT_TIMESTAMP,attempt_count=publication_log.attempt_count+1",
      ).bind(row.id, now.year, config.channel_id).run();
    } catch (error) {
      await env.DB.prepare(
        "INSERT INTO publication_log(birthday_id,publication_year,channel_id,status,error) VALUES(?,?,?,'failed',?) " +
        "ON CONFLICT(birthday_id,publication_year) DO UPDATE SET status='failed',error=excluded.error,last_attempt=CURRENT_TIMESTAMP,attempt_count=publication_log.attempt_count+1",
      ).bind(row.id, now.year, config.channel_id, String(error).slice(0, 1000)).run();
    }
  }
}

async function setupWebhook(request: Request, env: Env): Promise<Response> {
  if (!validBotToken(env.BOT_TOKEN) || !env.WEBHOOK_SECRET) return Response.json({ ok: false, error: "Configure a valid BOT_TOKEN and WEBHOOK_SECRET first" }, { status: 503 });
  if (request.headers.get("authorization") !== `Bearer ${env.WEBHOOK_SECRET}`) return new Response("Unauthorized", { status: 401 });
  const url = new URL(request.url);
  const result = await tg(env, "setWebhook", {
    url: `${url.origin}/telegram`,
    secret_token: env.WEBHOOK_SECRET,
    allowed_updates: ["message", "callback_query"],
    drop_pending_updates: false,
  });
  return Response.json({ ok: true, webhook: `${url.origin}/telegram`, telegram: result });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      return Response.json({ ok: true, service: "telegram-birthday-bot", configured: Boolean(validBotToken(env.BOT_TOKEN) && ownerIds(env).size && env.WEBHOOK_SECRET) });
    }
    if (url.pathname === "/setup-webhook" && request.method === "POST") return setupWebhook(request, env);
    if (url.pathname === "/telegram" && request.method === "POST") {
      if (!env.WEBHOOK_SECRET || request.headers.get("x-telegram-bot-api-secret-token") !== env.WEBHOOK_SECRET) return new Response("Forbidden", { status: 403 });
      const update = await request.json<TgUpdate>();
      ctx.waitUntil(update.callback_query ? handleCallback(env, update.callback_query) : update.message ? handleMessage(env, update.message) : Promise.resolve());
      return new Response("OK");
    }
    return new Response("Not found", { status: 404 });
  },
  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(publishDue(env));
  },
} satisfies ExportedHandler<Env>;
