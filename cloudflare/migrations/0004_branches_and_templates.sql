INSERT OR IGNORE INTO branches(name) VALUES
  ('Головной (Ташкент)'),
  ('Алмалык'),
  ('Янги Хаёт'),
  ('Бука'),
  ('Ангрен'),
  ('Янгиюль'),
  ('Юнусабад'),
  ('Гулистан'),
  ('Ахангаран'),
  ('Бекабад'),
  ('Янгибозор'),
  ('Навои'),
  ('Сырдарья'),
  ('Ургенч'),
  ('Бухара'),
  ('Чирчик'),
  ('Зарафшан'),
  ('Авиасозлар'),
  ('Жондор'),
  ('Каган'),
  ('Нукус'),
  ('Учкудук'),
  ('Ромитан'),
  ('Янгийер'),
  ('Зафар'),
  ('Гиждувон'),
  ('Газалкент'),
  ('Паркент'),
  ('Ургут'),
  ('Пахтачи'),
  ('Бувайда'),
  ('Каттакурган'),
  ('Мангыт'),
  ('ТТЗ'),
  ('Джизак'),
  ('Гурлен'),
  ('Шават'),
  ('Сергели'),
  ('Фергана'),
  ('Андижан'),
  ('Коканд'),
  ('Термез'),
  ('Шахрихон'),
  ('Алмазар');

UPDATE birthdays
SET branch_id = (SELECT id FROM branches WHERE name = 'Головной (Ташкент)' LIMIT 1)
WHERE branch_id IN (SELECT id FROM branches WHERE name = 'Главный филиал');

DELETE FROM branches
WHERE name = 'Главный филиал'
  AND NOT EXISTS (SELECT 1 FROM birthdays WHERE birthdays.branch_id = branches.id);

INSERT INTO settings(key, value) VALUES
  ('caption_template', '🎉 Поздравляем <b>[ФИО]</b>, [Должность] филиала «[Филиал]», с днём рождения!\n\nЖелаем крепкого здоровья, благополучия, вдохновения и новых успехов! 💙')
ON CONFLICT(key) DO UPDATE SET value = excluded.value;

INSERT INTO settings(key, value) VALUES
  ('group_caption_template', '🎉 Поздравляем с днём рождения [Список]!\n\nЖелаем крепкого здоровья, благополучия, вдохновения и новых успехов! 💙')
ON CONFLICT(key) DO UPDATE SET value = excluded.value;
