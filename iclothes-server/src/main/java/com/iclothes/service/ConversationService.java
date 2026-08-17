package com.iclothes.service;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.iclothes.dto.ConversationDto;
import com.iclothes.dto.ConversationSummaryDto;
import com.iclothes.dto.MessageDto;
import com.iclothes.entity.Conversation;
import com.iclothes.entity.Message;
import com.iclothes.repository.ConversationMapper;
import com.iclothes.repository.MessageMapper;

@Service
public class ConversationService {

    static final int MAX_HISTORY = 50;

    private final ConversationMapper conversations;
    private final MessageMapper messages;

    public ConversationService(ConversationMapper conversations, MessageMapper messages) {
        this.conversations = conversations;
        this.messages = messages;
    }

    public ConversationDto create() {
        Conversation c = new Conversation(UUID.randomUUID(), "新对话",
                LocalDateTime.now(), LocalDateTime.now());
        conversations.insert(c);
        return toDto(c, List.of());
    }

    public List<ConversationSummaryDto> listSummaries() {
        return conversations.selectSummaries();
    }

    public ConversationDto get(UUID id) {
        Conversation c = conversations.selectById(id);
        if (c == null) return null;
        List<Message> ms = messages.selectList(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, id)
                .orderByAsc(Message::getId));
        return toDto(c, ms.stream().map(this::toMessageDto).toList());
    }

    public boolean delete(UUID id) {
        return conversations.deleteById(id) > 0;
    }

    public List<Message> lastMessages(UUID id, int limit) {
        // 取"最近 limit 条"（DESC + LIMIT 拿到最新窗口），再 reverse 恢复升序交给下游
        List<Message> msgs = messages.selectList(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, id)
                .orderByDesc(Message::getId)
                .last("LIMIT " + limit));
        Collections.reverse(msgs);
        return msgs;
    }

    public void appendUser(UUID id, String content, List<String> images) {
        Message m = new Message();
        m.setConversationId(id);
        m.setRole("user");
        m.setContent(content == null ? "" : content);
        m.setIntent("");
        m.setImages(images == null ? List.of() : images);
        m.setCreatedAt(LocalDateTime.now());
        messages.insert(m);
    }

    public void appendAssistant(UUID id, String content, String intent) {
        Message m = new Message();
        m.setConversationId(id);
        m.setRole("assistant");
        m.setContent(content);
        m.setIntent(intent == null ? "" : intent);
        m.setImages(List.of());
        m.setCreatedAt(LocalDateTime.now());
        messages.insert(m);
    }

    public void trim(UUID id) {
        long total = messages.selectCount(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, id));
        if (total > MAX_HISTORY) {
            long excess = total - MAX_HISTORY;
            messages.delete(new LambdaQueryWrapper<Message>()
                    .eq(Message::getConversationId, id)
                    .orderByAsc(Message::getId)
                    .last("LIMIT " + excess));
        }
    }

    public void setTitle(UUID id, String title) {
        Conversation c = conversations.selectById(id);
        if (c != null) {
            c.setTitle(title);
            c.setUpdatedAt(LocalDateTime.now());
            conversations.updateById(c);
        }
    }

    public String getTitle(UUID id) {
        Conversation c = conversations.selectById(id);
        return c == null ? "新对话" : c.getTitle();
    }

    MessageDto toMessageDto(Message m) {
        MessageDto d = new MessageDto();
        d.setRole(m.getRole());
        d.setContent(m.getContent());
        d.setIntent(m.getIntent());
        d.setImages(m.getImages());
        d.setCreatedAt(m.getCreatedAt());
        return d;
    }

    private ConversationDto toDto(Conversation c, List<MessageDto> msgs) {
        ConversationDto d = new ConversationDto();
        d.setId(c.getId().toString());
        d.setTitle(c.getTitle());
        d.setCreatedAt(c.getCreatedAt());
        d.setUpdatedAt(c.getUpdatedAt());
        d.setMessages(msgs);
        return d;
    }
}
