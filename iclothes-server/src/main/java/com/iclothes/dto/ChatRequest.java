package com.iclothes.dto;

import java.util.List;

public class ChatRequest {
    private String conversationId;
    private String message = "";
    private List<String> images = List.of();

    public String getConversationId() { return conversationId; }
    public void setConversationId(String v) { conversationId = v; }
    public String getMessage() { return message; }
    public void setMessage(String v) { message = v; }
    public List<String> getImages() { return images; }
    public void setImages(List<String> v) { images = v; }
}
