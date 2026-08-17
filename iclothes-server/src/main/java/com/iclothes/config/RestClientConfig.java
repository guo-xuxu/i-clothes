package com.iclothes.config;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class RestClientConfig {

    @Bean
    public RestClient pythonChatClient(AppProperties properties) {
        return RestClient.builder()
                .baseUrl(properties.getAgent().getBaseUrl())
                .requestFactory(factory(properties.getAgent().getConnectTimeoutMs(),
                        properties.getAgent().getReadTimeoutMs()))
                .build();
    }

    @Bean
    public RestClient pythonHealthClient(AppProperties properties) {
        return RestClient.builder()
                .baseUrl(properties.getAgent().getBaseUrl())
                .requestFactory(factory(properties.getAgent().getHealthTimeoutMs(),
                        properties.getAgent().getHealthTimeoutMs()))
                .build();
    }

    private SimpleClientHttpRequestFactory factory(int connectMs, int readMs) {
        SimpleClientHttpRequestFactory f = new SimpleClientHttpRequestFactory();
        f.setConnectTimeout(Duration.ofMillis(connectMs));
        f.setReadTimeout(Duration.ofMillis(readMs));
        return f;
    }
}
