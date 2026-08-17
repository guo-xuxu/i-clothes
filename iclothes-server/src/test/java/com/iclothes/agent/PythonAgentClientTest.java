package com.iclothes.agent;

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
        return new PythonAgentClient(chat, health);
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
        PythonAgentClient client = client(builder, props());

        assertThatThrownBy(() -> client.chat("你好", List.of(), List.of()))
                .isInstanceOf(AgentUnavailableException.class);
    }

    /** Task 2 评审遗留：healthQianwenConfigured() 的"调用异常 → 返回 false"catch 分支（契约：Python 不可达仍 200+false 的唯一落点）。 */
    @Test
    void healthReturnsFalseWhenPythonUnreachable() {
        RestClient.Builder healthBuilder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(healthBuilder).build();
        AppProperties p = props();
        RestClient chat = RestClient.builder().baseUrl(p.getAgent().getBaseUrl()).build();
        RestClient health = healthBuilder.baseUrl(p.getAgent().getBaseUrl()).build();
        PythonAgentClient client = new PythonAgentClient(chat, health);

        // HTTP 层抛 I/O 异常（真实连接失败的等价物）→ client 侧包装为 ResourceAccessException → catch 分支 → false
        server.expect(once(), requestTo("http://127.0.0.1:8000/api/health"))
                .andRespond(withException(new java.net.ConnectException("connection refused")));

        // 不抛异常、返回 false（若异常漏出，本断言直接失败）
        assertThat(client.healthQianwenConfigured()).isFalse();
        server.verify();
    }
}
