package com.iclothes.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import com.iclothes.dto.ChatResponse;
import com.iclothes.exception.AgentUnavailableException;
import com.iclothes.exception.AgentValidationException;
import com.iclothes.service.ChatService;
import com.iclothes.service.RateLimiter;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ChatController.class)
class ChatControllerTest {

    @Autowired MockMvc mvc;

    @MockitoBean
    ChatService chatService;

    @MockitoBean
    RateLimiter rateLimiter;

    @Test
    void emptyMessageAndImagesRejected() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"\",\"images\":[]}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("消息内容不能为空"));
    }

    @Test
    void invalidImageFormatRejected() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hi\",\"images\":[\"data:image/gif;base64,AAAA\"]}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("不支持的图片格式，仅支持 JPG/PNG"));
    }

    @Test
    void tooManyImagesRejected() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        String images = "["
                + "\"data:image/png;base64,AAAA\",\"data:image/png;base64,BBBB\","
                + "\"data:image/png;base64,CCCC\",\"data:image/png;base64,DDDD\"]";
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hi\",\"images\":" + images + "}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("最多上传 3 张照片"));
    }

    @Test
    void rateLimitedReturns429() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(false);
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"你好\",\"images\":[]}"))
                .andExpect(status().isTooManyRequests())
                .andExpect(jsonPath("$.detail").value("请求过于频繁，请稍后重试"));
    }

    @Test
    void happyPathReturnsChatResponse() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        when(chatService.chat(any(), any(), anyList()))
                .thenReturn(new ChatResponse("abc", "回复", "chat", "新对话"));
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"你好\",\"images\":[]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.conversation_id").value("abc"))
                .andExpect(jsonPath("$.reply").value("回复"))
                .andExpect(jsonPath("$.intent").value("chat"));
    }

    @Test
    void agentValidationErrorReturns400WithDetail() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        when(chatService.chat(any(), any(), anyList()))
                .thenThrow(new AgentValidationException("校验失败"));
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"你好\",\"images\":[]}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("校验失败"));
    }

    @Test
    void agentUnavailableReturns502WithDetail() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        when(chatService.chat(any(), any(), anyList()))
                .thenThrow(new AgentUnavailableException("AI 服务暂不可用，请稍后重试"));
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"你好\",\"images\":[]}"))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.detail").value("AI 服务暂不可用，请稍后重试"));
    }

    @Test
    void unexpectedErrorReturns500WithoutStacktrace() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        when(chatService.chat(any(), any(), anyList()))
                .thenThrow(new RuntimeException("boom"));
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"你好\",\"images\":[]}"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.detail").value("服务器内部错误"))
                .andExpect(content().string(not(containsString("Exception"))));
    }
}
