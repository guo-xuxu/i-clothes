package com.iclothes.controller;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import com.iclothes.dto.ConversationDto;
import com.iclothes.service.ConversationService;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ConversationController.class)
class ConversationControllerTest {

    @Autowired MockMvc mvc;

    @MockitoBean
    ConversationService service;

    @Test
    void missingConversationReturns404() throws Exception {
        mvc.perform(get("/api/conversations/00000000-0000-0000-0000-000000000001"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.detail").value("会话不存在"));
    }

    @Test
    void deleteMissingReturns404() throws Exception {
        mvc.perform(delete("/api/conversations/00000000-0000-0000-0000-000000000001"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.detail").value("会话不存在"));
    }

    @Test
    void createReturnsDto() throws Exception {
        ConversationDto dto = new ConversationDto();
        dto.setId(UUID.randomUUID().toString());
        dto.setTitle("新对话");
        dto.setMessages(List.of());
        when(service.create()).thenReturn(dto);
        mvc.perform(post("/api/conversations"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("新对话"));
    }
}
