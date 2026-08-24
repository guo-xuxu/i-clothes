package com.iclothes.entity;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler;

@TableName(value = "messages", autoResultMap = true)
public class Message {

    @TableId(type = IdType.AUTO)
    private Long id;
    private UUID conversationId;
    private String role;
    private String content;
    private String intent;
    @TableField(typeHandler = JacksonTypeHandler.class)
    private List<String> images;
    private LocalDateTime createdAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public UUID getConversationId() { return conversationId; }
    public void setConversationId(UUID v) { conversationId = v; }
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
