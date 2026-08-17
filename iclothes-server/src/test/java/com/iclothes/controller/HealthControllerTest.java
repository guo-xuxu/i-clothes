package com.iclothes.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import com.iclothes.agent.PythonAgentClient;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(HealthController.class)
class HealthControllerTest {

    @Autowired MockMvc mvc;

    @MockitoBean
    PythonAgentClient agentClient;

    @Test
    void healthReportsQianwenConfiguredWhenPythonUp() throws Exception {
        when(agentClient.healthQianwenConfigured()).thenReturn(true);
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(jsonPath("$.qianwen_configured").value(true));
    }

    @Test
    void healthStillOkWhenPythonDown() throws Exception {
        when(agentClient.healthQianwenConfigured()).thenReturn(false);
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(jsonPath("$.qianwen_configured").value(false));
    }
}
