package com.iclothes.service;

import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import com.iclothes.agent.AgentChatRequest;
import com.iclothes.agent.AgentChatResponse;
import com.iclothes.agent.PythonAgentClient;
import com.iclothes.dto.ChatResponse;
import com.iclothes.entity.Message;
import com.iclothes.exception.ApiException;

@Service
public class ChatService {

    static final int HISTORY_LIMIT = 20;
    static final int TITLE_MAX = 20;
    static final long LOCK_WAIT_MS = 3000;
    static final String LOCK_PREFIX = "conversation:";
    static final String LOCK_SUFFIX = ":lock";

    private final ConversationService conversations;
    private final PythonAgentClient agentClient;
    private final SessionLock sessionLock;

    public ChatService(ConversationService conversations, PythonAgentClient agentClient,
                       SessionLock sessionLock) {
        this.conversations = conversations;
        this.agentClient = agentClient;
        this.sessionLock = sessionLock;
    }

    public ChatResponse chat(String conversationId, String message, List<String> images) {
        // 1. 会话解析：id 无效/不存在 → 新建
        UUID cid = parseOrNull(conversationId);
        boolean isNew = false;
        if (cid == null) {
            isNew = true;
            cid = UUID.randomUUID();
            conversations.create(); // 空会话落库
        } else if (conversations.get(cid) == null) {
            isNew = true;
            conversations.create();
        }

        String lockKey = LOCK_PREFIX + cid + LOCK_SUFFIX;

        // 4. Redis 会话写锁（等待 ≤3s，失败 503）；Redis 故障时内部降级
        boolean locked = sessionLock.tryAcquire(lockKey, LOCK_WAIT_MS);
        if (!locked) {
            throw new ApiException(503, "请求过于频繁，请稍后重试");
        }

        try {
            // 3. 取历史（最近 20 条）→ 5. 调 Python（不重试）
            List<Message> history = conversations.lastMessages(cid, HISTORY_LIMIT);
            List<AgentChatRequest.HistoryItem> historyItems = history.stream()
                    .map(m -> new AgentChatRequest.HistoryItem(m.getRole(), m.getContent()))
                    .toList();
            AgentChatResponse resp = agentClient.chat(message, images, historyItems);

            // 6. 落库 → 7. 裁剪 → 8. 自动标题
            conversations.appendUser(cid, message, images);
            conversations.appendAssistant(cid, resp.reply(), resp.intent());
            conversations.trim(cid);

            String title = conversations.getTitle(cid);
            if (isNew && message != null && !message.isBlank()) {
                String clean = message.trim().replace("\n", " ");
                title = clean.substring(0, Math.min(TITLE_MAX, clean.length()));
                conversations.setTitle(cid, title);
            }

            return new ChatResponse(cid.toString(), resp.reply(), resp.intent(), title);
        } finally {
            sessionLock.release(lockKey);
        }
    }

    private UUID parseOrNull(String id) {
        if (id == null || id.isBlank()) return null;
        try {
            return UUID.fromString(id);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }
}
