package com.iclothes.agent;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import com.iclothes.config.AppProperties;
import com.iclothes.exception.AgentUnavailableException;
import com.iclothes.exception.AgentValidationException;

@Component
public class PythonAgentClient {

    private static final Logger log = LoggerFactory.getLogger(PythonAgentClient.class);

    private final RestClient chatClient;
    private final RestClient healthClient;
    private final String baseUrl;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public PythonAgentClient(
            @org.springframework.beans.factory.annotation.Qualifier("pythonChatClient") RestClient chatClient,
            @org.springframework.beans.factory.annotation.Qualifier("pythonHealthClient") RestClient healthClient,
            AppProperties properties) {
        this.chatClient = chatClient;
        this.healthClient = healthClient;
        this.baseUrl = properties.getAgent().getBaseUrl();
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

    /** 流式聊天事件的回调（由 ChatService 驱动持久化与 SseEmitter 转发）。 */
    public interface StreamHandler {
        void onDelta(String delta);
        void onDone(String intent);
        void onError(Throwable error);
    }

    /**
     * 流式调 Python /api/agent/chat/stream（SSE，JDK HttpClient 逐行读取）。
     * 事件逐条回调 handler；非 200 或 IO 异常 → onError。阻塞调用，需在虚拟线程中执行。
     */
    public void streamChat(String message, List<String> images,
                           List<AgentChatRequest.HistoryItem> history,
                           StreamHandler handler) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
        HttpRequest request;
        try {
            request = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/api/agent/chat/stream"))
                    .timeout(Duration.ofSeconds(120))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            objectMapper.writeValueAsString(
                                    new AgentChatRequest(message, images, history))))
                    .build();
        } catch (JsonProcessingException e) {
            handler.onError(e);
            return;
        }
        try {
            HttpResponse<Stream<String>> resp = client.send(
                    request, HttpResponse.BodyHandlers.ofLines());
            if (resp.statusCode() != 200) {
                handler.onError(new IllegalStateException(
                        "Python 流式接口返回 " + resp.statusCode()));
                return;
            }
            try (Stream<String> lines = resp.body()) {
                lines.forEach(line -> handleSseLine(line, handler));
            }
        } catch (Exception e) {
            handler.onError(e);
        }
    }

    private void handleSseLine(String line, StreamHandler handler) {
        if (line == null || !line.startsWith("data: ")) {
            return;
        }
        try {
            JsonNode node = objectMapper.readTree(line.substring(6));
            if (node.has("delta")) {
                handler.onDelta(node.get("delta").asText());
            } else if (node.has("done")) {
                handler.onDone(node.path("intent").asText("chat"));
            } else if (node.has("error")) {
                handler.onError(new RuntimeException(node.get("error").asText()));
            }
        } catch (JsonProcessingException e) {
            handler.onError(e);
        }
    }
}
