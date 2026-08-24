package com.iclothes.dto;

public class ChatResponse {
    private String conversationId;
    private String reply;
    private String intent;
    private String title;

    public ChatResponse() {}
    public ChatResponse(String conversationId, String reply, String intent, String title) {
        this.conversationId = conversationId; this.reply = reply;
        this.intent = intent; this.title = title;
    }
    public String getConversationId() { return conversationId; }
    public void setConversationId(String v) { conversationId = v; }
    public String getReply() { return reply; }
    public void setReply(String v) { reply = v; }
    public String getIntent() { return intent; }
    public void setIntent(String v) { intent = v; }
    public String getTitle() { return title; }
    public void setTitle(String v) { title = v; }
}
