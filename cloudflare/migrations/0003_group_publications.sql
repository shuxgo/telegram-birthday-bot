INSERT OR IGNORE INTO settings(key, value) VALUES (
  'group_caption_template',
  '🎉 <b>Поздравляем наших именинников!</b>\n\nСегодня день рождения отмечают:\n\n{people}\n\nЖелаем крепкого здоровья, счастья, вдохновения и ярких профессиональных побед! 🎂'
);

UPDATE settings
SET value = '🎉 <b>Поздравляем с днём рождения!</b>\n\nСегодня свой день рождения отмечает:\n\n<b>{name}</b>\n💼 {position}\n🏢 Филиал «{branch}»\n\nЖелаем крепкого здоровья, счастья, вдохновения и ярких профессиональных побед! 🎂'
WHERE key = 'caption_template'
;
