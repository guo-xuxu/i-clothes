package com.iclothes.agent;

import java.util.List;

public record AgentChatRequest(String message, List<String> images, List<HistoryItem> history) {

    public record HistoryItem(String role, String content) {}
}
