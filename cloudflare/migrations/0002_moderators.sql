CREATE TABLE IF NOT EXISTS moderators (
  user_id INTEGER PRIMARY KEY,
  username TEXT,
  full_name TEXT,
  added_by INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
