-- 用户体系（V2）：users 表 + 会话归属用户

CREATE TABLE users (
    id         BIGSERIAL PRIMARY KEY,
    username   VARCHAR(64) NOT NULL UNIQUE,
    password   VARCHAR(100) NOT NULL,          -- BCrypt 加密结果
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 存量会话清空（少数人内部用，不迁移历史数据）
DELETE FROM conversations;

ALTER TABLE conversations ADD COLUMN user_id BIGINT NOT NULL REFERENCES users(id);

CREATE INDEX idx_conversations_user ON conversations(user_id, updated_at DESC);
