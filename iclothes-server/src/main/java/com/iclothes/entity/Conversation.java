package com.iclothes.entity;

import java.time.LocalDateTime;
import java.util.UUID;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

@TableName("conversations")
public class Conversation {

    @TableId(type = IdType.INPUT)
    private UUID id;
    private String title;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Conversation() {}
    public Conversation(UUID id, String title, LocalDateTime createdAt, LocalDateTime updatedAt) {
        this.id = id; this.title = title; this.createdAt = createdAt; this.updatedAt = updatedAt;
    }

    public UUID getId() { return id; }
    public void setId(UUID id) { this.id = id; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime v) { createdAt = v; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime v) { updatedAt = v; }
}
