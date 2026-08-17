package com.iclothes.agent;

import java.util.Map;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PythonAgentClient {

    private final RestClient chatClient;
    private final RestClient healthClient;

    public PythonAgentClient(
            @org.springframework.beans.factory.annotation.Qualifier("pythonChatClient") RestClient chatClient,
            @org.springframework.beans.factory.annotation.Qualifier("pythonHealthClient") RestClient healthClient) {
        this.chatClient = chatClient;
        this.healthClient = healthClient;
    }

    /** 代理 Python /api/health（2s 超时）；不可达/异常一律返回 false。 */
    public boolean healthQianwenConfigured() {
        try {
            Map<?, ?> body = healthClient.get().uri("/api/health").retrieve().body(Map.class);
            return body != null && Boolean.TRUE.equals(body.get("qianwen_configured"));
        } catch (Exception e) {
            return false;
        }
    }
}
