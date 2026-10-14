CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS branches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL COLLATE NOCASE UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS birthdays (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  birth_date TEXT NOT NULL,
  position TEXT NOT NULL,
  branch_id INTEGER NOT NULL REFERENCES branches(id) ON DELETE RESTRICT,
  photo_key TEXT NOT NULL,
  photo_file_id TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS publication_log (
  birthday_id INTEGER NOT NULL REFERENCES birthdays(id) ON DELETE CASCADE,
  publication_year INTEGER NOT NULL,
  channel_id TEXT NOT NULL,
  status TEXT NOT NULL,
  error TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 1,
  last_attempt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  published_at TEXT,
  PRIMARY KEY (birthday_id, publication_year)
);

CREATE TABLE IF NOT EXISTS sessions (
  admin_id INTEGER PRIMARY KEY,
  state TEXT NOT NULL,
  data TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS moderators (
  user_id INTEGER PRIMARY KEY,
  username TEXT,
  full_name TEXT,
  added_by INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO settings(key, value) VALUES
  ('caption_template', '🎉 Поздравляем <b>[ФИО]</b>, [Должность] филиала «[Филиал]», с днём рождения!\n\nЖелаем крепкого здоровья, благополучия, вдохновения и новых успехов! 💙'),
  ('group_caption_template', '🎉 Поздравляем с днём рождения [Список]!\n\nЖелаем крепкого здоровья, благополучия, вдохновения и новых успехов! 💙'),
  ('publish_time', '09:00'),
  ('timezone', 'Asia/Tashkent'),
  ('template_key', 'templates/default.png');

INSERT OR IGNORE INTO branches(name) VALUES
  ('Головной (Ташкент)'), ('Алмалык'), ('Янги Хаёт'), ('Бука'), ('Ангрен'),
  ('Янгиюль'), ('Юнусабад'), ('Гулистан'), ('Ахангаран'), ('Бекабад'),
  ('Янгибозор'), ('Навои'), ('Сырдарья'), ('Ургенч'), ('Бухара'),
  ('Чирчик'), ('Зарафшан'), ('Авиасозлар'), ('Жондор'), ('Каган'),
  ('Нукус'), ('Учкудук'), ('Ромитан'), ('Янгийер'), ('Зафар'),
  ('Гиждувон'), ('Газалкент'), ('Паркент'), ('Ургут'), ('Пахтачи'),
  ('Бувайда'), ('Каттакурган'), ('Мангыт'), ('ТТЗ'), ('Джизак'),
  ('Гурлен'), ('Шават'), ('Сергели'), ('Фергана'), ('Андижан'),
  ('Коканд'), ('Термез'), ('Шахрихон'), ('Алмазар');
