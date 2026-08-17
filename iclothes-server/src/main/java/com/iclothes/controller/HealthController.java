package com.iclothes.controller;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import com.iclothes.agent.PythonAgentClient;

@RestController
public class HealthController {

    private final PythonAgentClient agentClient;

    public HealthController(PythonAgentClient agentClient) { this.agentClient = agentClient; }

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        return Map.of("status", "ok", "qianwen_configured", agentClient.healthQianwenConfigured());
    }
}
