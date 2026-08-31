package com.iclothes.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import com.iclothes.agent.PythonAgentClient;
import com.iclothes.controller.AuthController;
import com.iclothes.controller.HealthController;
import com.iclothes.dto.UserInfo;
import com.iclothes.service.AuthService;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** 认证过滤器测试：白名单放行、未认证 401、有效 token 注入 userId。 */
@WebMvcTest({HealthController.class, AuthController.class})
@Import({JwtUtil.class, AuthFilterTest.FilterConfig.class})
class AuthFilterTest {

    @Autowired MockMvc mvc;
    @Autowired JwtUtil jwtUtil;

    @MockitoBean PythonAgentClient agentClient;
    @MockitoBean AuthService authService;

    @TestConfiguration
    static class FilterConfig {
        @Bean
        AuthFilter authFilter(JwtUtil jwtUtil) {
            return new AuthFilter(jwtUtil);
        }

        @Bean
        FilterRegistrationBean<AuthFilter> authFilterRegistration(AuthFilter filter) {
            FilterRegistrationBean<AuthFilter> reg = new FilterRegistrationBean<>(filter);
            reg.addUrlPatterns("/*");
            return reg;
        }
    }

    @Test
    void healthWhitelistedWithoutToken() throws Exception {
        when(agentClient.healthQianwenConfigured()).thenReturn(true);
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void protectedPathWithoutTokenReturns401() throws Exception {
        mvc.perform(get("/api/auth/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("未认证"));
    }

    @Test
    void protectedPathWithInvalidTokenReturns401() throws Exception {
        mvc.perform(get("/api/auth/me").header("Authorization", "Bearer invalid"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("未认证"));
    }

    @Test
    void protectedPathWithValidTokenPassesAndInjectsUserId() throws Exception {
        String token = jwtUtil.generate(1L, "alice");
        when(authService.me(1L)).thenReturn(new UserInfo(1L, "alice"));
        mvc.perform(get("/api/auth/me").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.username").value("alice"));
    }
}
