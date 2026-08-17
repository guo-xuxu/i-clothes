package com.iclothes.agent;

import java.util.List;
import java.util.Map;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import com.iclothes.exception.AgentUnavailableException;
import com.iclothes.exception.AgentValidationException;

@Component
public class PythonAgentClient {

    private static final Logger log = LoggerFactory.getLogger(PythonAgentClient.class);

    private final RestClient chatClient;
    private final RestClient healthClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

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

    /** 调 Python /api/agent/chat（无状态，不重试）。 */
    public AgentChatResponse chat(String message, List<String> images,
                                  List<AgentChatRequest.HistoryItem> history) {
        try {
            return chatClient.post()
                    .uri("/api/agent/chat")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new AgentChatRequest(message, images, history))
                    .retrieve()
                    .body(AgentChatResponse.class);
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 400) {
                throw new AgentValidationException(extractDetail(e.getResponseBodyAsString()));
            }
            // I2：非 400 响应不再静默吞掉——记录状态码与响应体 detail，保证故障可观测
            log.error("Python agent 返回非 400 状态 {}，响应体 detail={}，按 502 处理",
                    e.getStatusCode().value(), extractDetail(e.getResponseBodyAsString()), e);
            throw new AgentUnavailableException("AI 服务暂不可用，请稍后重试", e);
        } catch (RestClientException e) {
            // I2：连接/超时失败同样落日志（含异常堆栈），避免"故障后日志里查不到原因"
            log.error("Python agent 调用失败（连接/超时）: {}", e.getMessage(), e);
            throw new AgentUnavailableException("AI 服务暂不可用，请稍后重试", e);
        }
    }

    private String extractDetail(String body) {
        try {
            return objectMapper.readTree(body).path("detail").asText("AI 服务暂不可用，请稍后重试");
        } catch (Exception e) {
            return "AI 服务暂不可用，请稍后重试";
        }
    }
}
