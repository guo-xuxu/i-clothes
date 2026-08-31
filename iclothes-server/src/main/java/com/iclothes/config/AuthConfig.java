package com.iclothes.config;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 认证过滤器注册。放在独立 @Configuration 里（而非 @Component/@WebFilter），
 * 这样 {@code @WebMvcTest} 的 MockMvcConfiguration 不会扫描到 AuthFilter，
 * 避免其依赖 JwtUtil 在 web 切片测试上下文缺失导致启动失败。
 */
@Configuration
public class AuthConfig {

    @Bean
    public AuthFilter authFilter(JwtUtil jwtUtil) {
        return new AuthFilter(jwtUtil);
    }

    @Bean
    public FilterRegistrationBean<AuthFilter> authFilterRegistration(AuthFilter filter) {
        FilterRegistrationBean<AuthFilter> reg = new FilterRegistrationBean<>(filter);
        reg.addUrlPatterns("/*");
        reg.setOrder(1);
        return reg;
    }
}
