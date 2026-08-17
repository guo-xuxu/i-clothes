package com.iclothes.dto;

import java.time.LocalDateTime;

public class ConversationSummaryDto {
    private String id;
    private String title;
    private String preview;
    private LocalDateTime updatedAt;

    public String getId() { return id; }
    public void setId(String v) { id = v; }
    public String getTitle() { return title; }
    public void setTitle(String v) { title = v; }
    public String getPreview() { return preview; }
    public void setPreview(String v) { preview = v; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime v) { updatedAt = v; }
}
