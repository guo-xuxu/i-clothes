// ConversationServiceTest.java
package com.iclothes.service;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import com.iclothes.dto.ConversationDto;
import com.iclothes.repository.ConversationMapper;
import com.iclothes.repository.MessageMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ConversationServiceTest {

    @Mock ConversationMapper conversations;
    @Mock MessageMapper messages;

    @Test
    void getReturnsNullForMissing() {
        UUID id = UUID.randomUUID();
        when(conversations.selectById(id)).thenReturn(null);
        ConversationService service = new ConversationService(conversations, messages);
        assertThat(service.get(id)).isNull();
    }

    @Test
    void createProducesDto() {
        ConversationService service = new ConversationService(conversations, messages);
        ConversationDto dto = service.create();
        assertThat(dto.getId()).isNotNull();
        assertThat(dto.getTitle()).isEqualTo("新对话");
        assertThat(dto.getMessages()).isEmpty();
    }

    @Test
    void trimOnlyDeletesBeyondLimit() {
        // 裁剪逻辑在 RepositoryIT 中覆盖；此处验证不会误删（total <= 50 时不调用 delete）
        ConversationService service = new ConversationService(conversations, messages);
        UUID id = UUID.randomUUID();
        when(messages.selectCount(org.mockito.ArgumentMatchers.any()))
                .thenReturn(10L);
        service.trim(id);
        org.mockito.Mockito.verify(messages, org.mockito.Mockito.never())
                .delete(org.mockito.ArgumentMatchers.any());
    }
}
