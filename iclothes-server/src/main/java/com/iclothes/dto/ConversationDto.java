package com.iclothes.dto;

import java.util.List;

public class ConversationDto {
    private String id;
    private String title;
    private Long createdAt;
    private Long updatedAt;
    private List<MessageDto> messages;

    public String getId() { return id; }
    public void setId(String v) { id = v; }
    public String getTitle() { return title; }
    public void setTitle(String v) { title = v; }
    public Long getCreatedAt() { return createdAt; }
    public void setCreatedAt(Long v) { createdAt = v; }
    public Long getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Long v) { updatedAt = v; }
    public List<MessageDto> getMessages() { return messages; }
    public void setMessages(List<MessageDto> v) { messages = v; }
}
