package com.iclothes.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import com.iclothes.service.ChatService;
import com.iclothes.service.RateLimiter;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RecommendController.class)
class RecommendControllerTest {

    @Autowired MockMvc mvc;

    @MockitoBean ChatService chatService;
    @MockitoBean RateLimiter rateLimiter;

    @Test
    void noImagesRejected() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        mvc.perform(multipart("/api/recommend"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("请至少上传一张照片"));
    }

    @Test
    void wrongContentTypeRejected() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        MockMultipartFile file = new MockMultipartFile("images", "a.txt", "text/plain", new byte[]{1});
        mvc.perform(multipart("/api/recommend").file(file))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("不支持的图片格式：text/plain，仅支持 JPG/PNG"));
    }

    @Test
    void happyPath() throws Exception {
        when(rateLimiter.allow(any())).thenReturn(true);
        when(chatService.chat(any(), any(), anyList()))
                .thenReturn(new com.iclothes.dto.ChatResponse("c", "建议", "recommend", "t"));
        MockMultipartFile file = new MockMultipartFile("images", "a.png", "image/png", new byte[]{1, 2, 3});
        mvc.perform(multipart("/api/recommend").file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.suggestion").value("建议"));
    }
}
