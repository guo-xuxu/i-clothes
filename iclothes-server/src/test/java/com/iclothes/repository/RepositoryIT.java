package com.iclothes.repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.iclothes.dto.ConversationSummaryDto;
import com.iclothes.entity.Conversation;
import com.iclothes.entity.Message;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class RepositoryIT {

    @Autowired ConversationMapper conversations;
    @Autowired MessageMapper messages;

    @Test
    void conversationCrudAndCascade() {
        UUID cid = UUID.randomUUID();
        conversations.insert(new Conversation(cid, "测试会话", LocalDateTime.now(), LocalDateTime.now()));

        Message m = new Message();
        m.setConversationId(cid);
        m.setRole("user");
        m.setContent("你好");
        m.setIntent("");
        m.setImages(List.of("data:image/png;base64,AAAA"));
        m.setCreatedAt(LocalDateTime.now());
        messages.insert(m);

        assertThat(messages.selectList(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, cid))).hasSize(1);

        conversations.deleteById(cid);
        assertThat(messages.selectList(new LambdaQueryWrapper<Message>()
                .eq(Message::getConversationId, cid))).isEmpty();
    }

    @Test
    void summariesIncludePreview() {
        UUID cid = UUID.randomUUID();
        conversations.insert(new Conversation(cid, "摘要测试", LocalDateTime.now(), LocalDateTime.now()));
        Message m = new Message();
        m.setConversationId(cid);
        m.setRole("assistant");
        m.setContent("这是最后一条消息");
        m.setIntent("chat");
        m.setImages(List.of());
        m.setCreatedAt(LocalDateTime.now());
        messages.insert(m);

        List<ConversationSummaryDto> summaries = conversations.selectSummaries();
        ConversationSummaryDto first = summaries.get(0);
        assertThat(first.getId()).isEqualTo(cid.toString());
        assertThat(first.getTitle()).isEqualTo("摘要测试");
        assertThat(first.getPreview()).isEqualTo("这是最后一条消息");
    }
}
