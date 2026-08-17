package com.iclothes.dto;

public class ConversationSummaryDto {
    private String id;
    private String title;
    private String preview;
    private Long updatedAt;

    public String getId() { return id; }
    public void setId(String v) { id = v; }
    public String getTitle() { return title; }
    public void setTitle(String v) { title = v; }
    public String getPreview() { return preview; }
    public void setPreview(String v) { preview = v; }
    public Long getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Long v) { updatedAt = v; }
}
