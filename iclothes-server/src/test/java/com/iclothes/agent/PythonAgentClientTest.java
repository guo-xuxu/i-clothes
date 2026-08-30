package com.iclothes.agent;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import com.iclothes.config.AppProperties;
import com.iclothes.exception.AgentUnavailableException;
import com.iclothes.exception.AgentValidationException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class PythonAgentClientTest {

    private AppProperties props() {
        AppProperties p = new AppProperties();
        p.getAgent().setBaseUrl("http://127.0.0.1:8000");
        return p;
    }

    private PythonAgentClient client(RestClient.Builder builder, AppProperties p) {
        RestClient chat = builder.baseUrl(p.getAgent().getBaseUrl()).build();
        RestClient health = RestClient.builder().baseUrl(p.getAgent().getBaseUrl()).build();
        return new PythonAgentClient(chat, health, p);
    }

    @Test
    void chatSendsContractBodyAndParsesResponse() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        PythonAgentClient client = client(builder, props());

        server.expect(once(), requestTo("http://127.0.0.1:8000/api/agent/chat"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("你好"))
                .andExpect(jsonPath("$.history[0].role").value("user"))
                .andRespond(withSuccess("{\"reply\":\"你好！\",\"intent\":\"chat\"}",
                        MediaType.APPLICATION_JSON));

        AgentChatResponse resp = client.chat("你好", List.of(),
                List.of(new AgentChatRequest.HistoryItem("user", "之前的话题")));

        assertThat(resp.reply()).isEqualTo("你好！");
        assertThat(resp.intent()).isEqualTo("chat");
        server.verify();
    }

    @Test
    void chatPropagatesValidationError() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        PythonAgentClient client = client(builder, props());

        server.expect(once(), requestTo("http://127.0.0.1:8000/api/agent/chat"))
                .andRespond(withStatus(org.springframework.http.HttpStatus.BAD_REQUEST)
                        .body("{\"detail\":\"消息内容不能为空\"}").contentType(MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> client.chat("", List.of(), List.of()))
                .isInstanceOf(AgentValidationException.class)
                .hasMessage("消息内容不能为空");
    }

    @Test
    void chatWrapsServerErrorAsUnavailable() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        PythonAgentClient client = client(builder, props());

        server.expect(once(), requestTo("http://127.0.0.1:8000/api/agent/chat"))
                .andRespond(withServerError());

        assertThatThrownBy(() -> client.chat("你好", List.of(), List.of()))
                .isInstanceOf(AgentUnavailableException.class)
                .hasMessageContaining("AI 服务暂不可用");
    }

    @Test
    void chatWrapsConnectFailureAsUnavailable() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        PythonAgentClient client = client(builder, props());

        // HTTP 层抛 I/O 异常（真实连接失败的等价物）→ client 侧包装为 ResourceAccessException → AgentUnavailableException。
        // once() + verify()：钉死"不重试"——若 chat() 重试，请求次数会超过 1 次，verify() 失败。
        server.expect(once(), requestTo("http://127.0.0.1:8000/api/agent/chat"))
                .andRespond(withException(new java.net.ConnectException("connection refused")));

        assertThatThrownBy(() -> client.chat("你好", List.of(), List.of()))
                .isInstanceOf(AgentUnavailableException.class);
        server.verify();
    }

    /** Task 2 评审遗留：healthQianwenConfigured() 的"调用异常 → 返回 false"catch 分支（契约：Python 不可达仍 200+false 的唯一落点）。 */
    @Test
    void healthReturnsFalseWhenPythonUnreachable() {
        RestClient.Builder healthBuilder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(healthBuilder).build();
        AppProperties p = props();
        RestClient chat = RestClient.builder().baseUrl(p.getAgent().getBaseUrl()).build();
        RestClient health = healthBuilder.baseUrl(p.getAgent().getBaseUrl()).build();
        PythonAgentClient client = new PythonAgentClient(chat, health, p);

        // HTTP 层抛 I/O 异常（真实连接失败的等价物）→ client 侧包装为 ResourceAccessException → catch 分支 → false
        server.expect(once(), requestTo("http://127.0.0.1:8000/api/health"))
                .andRespond(withException(new java.net.ConnectException("connection refused")));

        // 不抛异常、返回 false（若异常漏出，本断言直接失败）
        assertThat(client.healthQianwenConfigured()).isFalse();
        server.verify();
    }

    // ------------------------------------------------------------------
    // 流式（SSE）：本地 JDK HttpServer 供脚本化事件
    // ------------------------------------------------------------------

    private static com.sun.net.httpserver.HttpServer sseServer(
            String sseBody, int status) throws Exception {
        com.sun.net.httpserver.HttpServer server = com.sun.net.httpserver.HttpServer.create(
                new InetSocketAddress(0), 0);
        server.createContext("/api/agent/chat/stream", exchange -> {
            byte[] body = sseBody.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "text/event-stream");
            exchange.sendResponseHeaders(status, status == 200 ? body.length : -1);
            if (status == 200) {
                exchange.getResponseBody().write(body);
            }
            exchange.close();
        });
        server.start();
        return server;
    }

    private record StreamCapture(java.util.List<String> deltas, java.util.List<String> intents,
                                 java.util.List<Throwable> errors) {}

    private StreamCapture runStream(String sseBody, int status) throws Exception {
        com.sun.net.httpserver.HttpServer server = sseServer(sseBody, status);
        try {
            AppProperties p = props();
            p.getAgent().setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
            PythonAgentClient c = client(RestClient.builder(), p);
            StreamCapture cap = new StreamCapture(new java.util.ArrayList<>(),
                    new java.util.ArrayList<>(), new java.util.ArrayList<>());
            c.streamChat("hi", List.of(), List.of(), new PythonAgentClient.StreamHandler() {
                @Override public void onDelta(String d) { cap.deltas().add(d); }
                @Override public void onDone(String i) { cap.intents().add(i); }
                @Override public void onError(Throwable t) { cap.errors().add(t); }
            });
            return cap;
        } finally {
            server.stop(0);
        }
    }

    @Test
    void streamChatForwardsDeltasAndDone() throws Exception {
        java.util.concurrent.atomic.AtomicReference<String> bodyRef = new java.util.concurrent.atomic.AtomicReference<>();
        com.sun.net.httpserver.HttpServer server = com.sun.net.httpserver.HttpServer.create(
                new InetSocketAddress(0), 0);
        server.createContext("/api/agent/chat/stream", exchange -> {
            bodyRef.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] body = ("data: {\"delta\":\"你\"}\n\n"
                    + "data: {\"delta\":\"好\"}\n\n"
                    + "data: {\"done\":true,\"intent\":\"recommend\"}\n\n").getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "text/event-stream");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            AppProperties p = props();
            p.getAgent().setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
            PythonAgentClient c = client(RestClient.builder(), p);
            StreamCapture cap = new StreamCapture(new java.util.ArrayList<>(),
                    new java.util.ArrayList<>(), new java.util.ArrayList<>());
            c.streamChat("hi", List.of(), List.of(), new PythonAgentClient.StreamHandler() {
                @Override public void onDelta(String d) { cap.deltas().add(d); }
                @Override public void onDone(String i) { cap.intents().add(i); }
                @Override public void onError(Throwable t) { cap.errors().add(t); }
            });
            System.out.println("STREAM_BODY=" + bodyRef.get());
            assertThat(bodyRef.get()).isEqualTo("{\"message\":\"hi\",\"images\":[],\"history\":[]}");
            assertThat(cap.deltas()).containsExactly("你", "好");
            assertThat(cap.intents()).containsExactly("recommend");
            assertThat(cap.errors()).isEmpty();
        } finally {
            server.stop(0);
        }
    }

    @Test
    void streamChatErrorEventInvokesOnError() throws Exception {
        StreamCapture cap = runStream("data: {\"error\":\"LLM 超时\"}\n\n", 200);
        assertThat(cap.deltas()).isEmpty();
        assertThat(cap.errors()).hasSize(1);
        assertThat(cap.errors().get(0).getMessage()).isEqualTo("LLM 超时");
    }

    @Test
    void streamChatNon200InvokesOnError() throws Exception {
        StreamCapture cap = runStream("", 500);
        assertThat(cap.errors()).hasSize(1);
    }
}
