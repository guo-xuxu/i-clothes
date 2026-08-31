package com.iclothes.service;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import com.iclothes.agent.AgentChatRequest;
import com.iclothes.agent.AgentChatResponse;
import com.iclothes.agent.PythonAgentClient;
import com.iclothes.dto.ChatResponse;
import com.iclothes.dto.ConversationDto;
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
    private final TransactionTemplate transactionTemplate;
    private final Executor chatExecutor;

    @Autowired
    public ChatService(ConversationService conversations, PythonAgentClient agentClient,
                       SessionLock sessionLock, TransactionTemplate transactionTemplate) {
        this(conversations, agentClient, sessionLock, transactionTemplate,
                Executors.newVirtualThreadPerTaskExecutor());
    }

    /** 测试用构造：可注入同步执行器，让流式回调确定性地在当前线程执行。 */
    ChatService(ConversationService conversations, PythonAgentClient agentClient,
                SessionLock sessionLock, TransactionTemplate transactionTemplate,
                Executor chatExecutor) {
        this.conversations = conversations;
        this.agentClient = agentClient;
        this.sessionLock = sessionLock;
        this.transactionTemplate = transactionTemplate;
        this.chatExecutor = chatExecutor;
    }

    public ChatResponse chat(String conversationId, String message, List<String> images) {
        // 1. 会话解析：id 无效/不存在 → 新建（消费 create() 落库的 id，不自造随机 id，
        //    否则后续 append/trim/setTitle 全部命中不存在的 conversation，触发 FK 违规）
        UUID parsed = parseOrNull(conversationId);
        boolean isNew = parsed == null || conversations.get(parsed) == null;
        UUID cid = isNew ? UUID.fromString(conversations.create().getId()) : parsed;

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

            // 6. 落库 → 7. 裁剪 → 8. 自动标题：四步写操作同一事务（appendAssistant 失败
            //    时整体回滚，不留孤儿 user 消息）。Python 调用在事务之外。
            String title = transactionTemplate.execute(status -> {
                conversations.appendUser(cid, message, images);
                conversations.appendAssistant(cid, resp.reply(), resp.intent());
                // I3：追加消息即触达 updated_at，会话列表按更新时间倒序（spec §3.1）
                conversations.touch(cid);
                conversations.trim(cid);

                String t = conversations.getTitle(cid);
                if (isNew && message != null && !message.isBlank()) {
                    String clean = message.trim().replace("\n", " ");
                    t = clean.substring(0, Math.min(TITLE_MAX, clean.length()));
                    conversations.setTitle(cid, t);
                }
                return t;
            });

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

    /**
     * 流式聊天：会话/锁/历史与非流式一致；虚拟线程内转发 Python SSE 到 SseEmitter，
     * 收到 done 后按非流式相同事务落库并 complete。校验（400/429/503）在调用方抛错。
     */
    public void chatStream(String conversationId, String message, List<String> images,
                           org.springframework.web.servlet.mvc.method.annotation.SseEmitter emitter) {
        UUID parsed = parseOrNull(conversationId);
        boolean isNew = parsed == null || conversations.get(parsed) == null;
        UUID cid = isNew ? UUID.fromString(conversations.create().getId()) : parsed;

        String lockKey = LOCK_PREFIX + cid + LOCK_SUFFIX;
        if (!sessionLock.tryAcquire(lockKey, LOCK_WAIT_MS)) {
            throw new ApiException(503, "请求过于频繁，请稍后重试");
        }

        List<AgentChatRequest.HistoryItem> historyItems = conversations.lastMessages(cid, HISTORY_LIMIT).stream()
                .map(m -> new AgentChatRequest.HistoryItem(m.getRole(), m.getContent()))
                .toList();

        chatExecutor.execute(() -> {
            try {
                StringBuilder reply = new StringBuilder();
                agentClient.streamChat(message, images, historyItems,
                        new PythonAgentClient.StreamHandler() {
                            @Override
                            public void onDelta(String delta) {
                                reply.append(delta);
                                try {
                                    emitter.send(SseEmitter.event()
                                            .data(Map.of("delta", delta)));
                                } catch (Exception e) {
                                    // 客户端断开等：终止整个流
                                    emitter.completeWithError(e);
                                }
                            }

                            @Override
                            public void onDone(String intent) {
                                String title = persistStream(
                                        cid, message, images, reply.toString(), intent, isNew);
                                try {
                                    // 结束事件必须先转发：前端据此判定流完整结束
                                    // （否则前端抛"流式响应未正常结束"，消息显示为出错）
                                    emitter.send(SseEmitter.event().data(Map.of(
                                            "done", true, "intent", intent)));
                                    // 元数据事件：前端绑定会话 id 与标题（流式接口无独立响应体）
                                    emitter.send(SseEmitter.event().data(Map.of(
                                            "conversation_id", cid.toString(),
                                            "title", title == null ? "新对话" : title)));
                                } catch (Exception e) {
                                    emitter.completeWithError(e);
                                    return;
                                }
                                emitter.complete();
                            }

                            @Override
                            public void onError(Throwable error) {
                                emitter.completeWithError(error);
                            }
                        });
            } finally {
                sessionLock.release(lockKey);
            }
        });
    }

    /** 流式结束后的落库（与非流式 chat 的事务四步一致），返回标题。 */
    private String persistStream(UUID cid, String message, List<String> images,
                                 String reply, String intent, boolean isNew) {
        return transactionTemplate.execute(status -> {
            conversations.appendUser(cid, message, images);
            conversations.appendAssistant(cid, reply, intent);
            conversations.touch(cid);
            conversations.trim(cid);

            String t = conversations.getTitle(cid);
            if (isNew && message != null && !message.isBlank()) {
                String clean = message.trim().replace("\n", " ");
                t = clean.substring(0, Math.min(TITLE_MAX, clean.length()));
                conversations.setTitle(cid, t);
            }
            return t;
        });
    }
}
