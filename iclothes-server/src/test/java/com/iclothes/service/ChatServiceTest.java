// ChatServiceTest.java
package com.iclothes.service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import com.iclothes.agent.AgentChatRequest;
import com.iclothes.agent.AgentChatResponse;
import com.iclothes.agent.PythonAgentClient;
import com.iclothes.dto.ChatResponse;
import com.iclothes.dto.ConversationDto;
import com.iclothes.entity.Conversation;
import com.iclothes.entity.Message;
import com.iclothes.exception.ApiException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ChatServiceTest {

    @Mock ConversationService conversations;
    @Mock PythonAgentClient agentClient;
    @Mock SessionLock sessionLock;
    @Mock PlatformTransactionManager txManager;

    ChatService service;
    UUID cid = UUID.randomUUID();
    String lockKey = "conversation:" + cid + ":lock";

    @BeforeEach
    void setUp() {
        // 共享桩用 lenient：lockTimeoutThrows503AndSkipsAgent 中 tryAcquire 被重写、chat 按断言
        // 必须永不调用；newConversationGetsCreatedAndTitled 中 get(cid) 不触发（cid 为 null），
        // STRICT_STUBS 会误报 UnnecessaryStubbingException（Mockito 官方推荐做法）
        lenient().when(sessionLock.tryAcquire(anyString(), eq(3000L))).thenReturn(true);
        lenient().when(agentClient.chat(anyString(), anyList(), anyList()))
                .thenReturn(new AgentChatResponse("回复", "chat"));
        lenient().when(conversations.get(cid)).thenReturn(new ConversationDto()); // 既有会话路径
        lenient().when(conversations.lastMessages(eq(cid), anyInt())).thenReturn(List.of());
        // 真实 TransactionTemplate + mock 事务管理器：单测内无真实事务，但持久化四步仍走
        // execute 回调（与生产路径一致）
        service = new ChatService(conversations, agentClient, sessionLock,
                new TransactionTemplate(txManager));
    }

    @Test
    void chatOrchestratesLockAgentPersistAndRelease() {
        when(conversations.getTitle(cid)).thenReturn("旧标题");

        ChatResponse resp = service.chat(cid.toString(), "你好", List.of());

        assertThat(resp.getReply()).isEqualTo("回复");
        assertThat(resp.getIntent()).isEqualTo("chat");
        assertThat(resp.getConversationId()).isEqualTo(cid.toString());
        verify(sessionLock).tryAcquire(lockKey, 3000);
        verify(agentClient, times(1)).chat(eq("你好"), anyList(), anyList()); // 恰好一次 = 不重试
        verify(conversations).appendUser(eq(cid), eq("你好"), anyList());
        verify(conversations).appendAssistant(eq(cid), eq("回复"), eq("chat"));
        verify(conversations).touch(cid); // I3：append 同事务内触达 updated_at
        verify(conversations).trim(cid);
        verify(sessionLock).release(lockKey);
    }

    @Test
    void newConversationGetsCreatedAndTitled() {
        String createdId = UUID.randomUUID().toString();
        ConversationDto created = new ConversationDto();
        created.setId(createdId);
        when(conversations.create()).thenReturn(created);
        when(conversations.getTitle(any(UUID.class))).thenReturn("新对话");

        ChatResponse resp = service.chat(null, "帮我推荐一条裙子", List.of());

        // 修复 #1：响应 conversationId 必须等于 create() 落库返回的 id（而非 ChatService 自造）
        assertThat(resp.getConversationId()).isEqualTo(createdId);
        verify(conversations).setTitle(any(UUID.class), eq("帮我推荐一条裙子"));
    }

    @Test
    void lockTimeoutThrows503AndSkipsAgent() {
        when(sessionLock.tryAcquire(anyString(), eq(3000L))).thenReturn(false);

        assertThatThrownBy(() -> service.chat(cid.toString(), "你好", List.of()))
                .isInstanceOf(ApiException.class)
                .satisfies(e -> assertThat(((ApiException) e).getStatus()).isEqualTo(503));
        verify(agentClient, never()).chat(anyString(), anyList(), anyList());
    }

    @Test
    void agentFailurePropagatesWithoutRetry() {
        when(agentClient.chat(anyString(), anyList(), anyList()))
                .thenThrow(new com.iclothes.exception.AgentUnavailableException("AI 服务暂不可用，请稍后重试"));

        assertThatThrownBy(() -> service.chat(cid.toString(), "你好", List.of()))
                .isInstanceOf(com.iclothes.exception.AgentUnavailableException.class);
        verify(agentClient, times(1)).chat(anyString(), anyList(), anyList()); // 不重试
        verify(sessionLock).release(lockKey); // finally 释放锁
    }

    // ------------------------------------------------------------------
    // 流式：chatStream（虚拟线程内转发 + done 后落库）
    // ------------------------------------------------------------------

    @Test
    void chatStreamForwardsDeltasAndPersistsOnDone() throws Exception {
        // 同步执行器：回调在当前线程确定执行，消除异步竞态
        service = new ChatService(conversations, agentClient, sessionLock,
                new TransactionTemplate(txManager), Runnable::run);
        SseEmitter emitter = mock(SseEmitter.class);
        doAnswer(inv -> {
            PythonAgentClient.StreamHandler h = inv.getArgument(3);
            h.onDelta("你");
            h.onDelta("好");
            h.onDone("recommend");
            return null;
        }).when(agentClient).streamChat(anyString(), anyList(), anyList(),
                any(PythonAgentClient.StreamHandler.class));

        service.chatStream(cid.toString(), "你好", List.of(), emitter);

        verify(emitter, times(2)).send(any(SseEmitter.SseEventBuilder.class));
        verify(emitter).complete();
        // done 后落库：累积回复 "你好" 作为 assistant 内容
        verify(conversations).appendUser(eq(cid), eq("你好"), anyList());
        verify(conversations).appendAssistant(eq(cid), eq("你好"), eq("recommend"));
        verify(sessionLock).release(lockKey);
    }

    @Test
    void chatStreamErrorCompletesWithError() throws Exception {
        service = new ChatService(conversations, agentClient, sessionLock,
                new TransactionTemplate(txManager), Runnable::run);
        SseEmitter emitter = mock(SseEmitter.class);
        doAnswer(inv -> {
            PythonAgentClient.StreamHandler h = inv.getArgument(3);
            h.onError(new RuntimeException("LLM 超时"));
            return null;
        }).when(agentClient).streamChat(anyString(), anyList(), anyList(),
                any(PythonAgentClient.StreamHandler.class));

        service.chatStream(cid.toString(), "你好", List.of(), emitter);

        verify(emitter).completeWithError(any());
        verify(conversations, never()).appendAssistant(any(), anyString(), anyString());
        verify(sessionLock).release(lockKey);
    }

    @Test
    void chatStreamThrows503WhenLockBusy() {
        when(sessionLock.tryAcquire(anyString(), eq(3000L))).thenReturn(false);
        SseEmitter emitter = mock(SseEmitter.class);

        assertThatThrownBy(() -> service.chatStream(cid.toString(), "hi", List.of(), emitter))
                .isInstanceOf(ApiException.class)
                .satisfies(e -> assertThat(((ApiException) e).getStatus()).isEqualTo(503));
    }
}
