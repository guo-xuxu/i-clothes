package com.iclothes.dto;

import java.time.LocalDateTime;
import java.util.List;

public class MessageDto {
    private String role;
    private String content;
    private String intent;
    private List<String> images;
    private LocalDateTime createdAt;

    public String getRole() { return role; }
    public void setRole(String v) { role = v; }
    public String getContent() { return content; }
    public void setContent(String v) { content = v; }
    public String getIntent() { return intent; }
    public void setIntent(String v) { intent = v; }
    public List<String> getImages() { return images; }
    public void setImages(List<String> v) { images = v; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime v) { createdAt = v; }
}
