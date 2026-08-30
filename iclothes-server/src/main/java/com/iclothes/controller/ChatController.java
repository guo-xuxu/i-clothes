package com.iclothes.controller;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import jakarta.servlet.http.HttpServletRequest;
import com.iclothes.config.AppProperties;
import com.iclothes.dto.ChatRequest;
import com.iclothes.dto.ChatResponse;
import com.iclothes.exception.ApiException;
import com.iclothes.service.ChatService;
import com.iclothes.service.RateLimiter;

@RestController
public class ChatController {

    private static final Pattern DATA_URL = Pattern.compile("^data:image/(jpeg|png);base64,");

    private final ChatService chatService;
    private final RateLimiter rateLimiter;
    private final AppProperties properties;

    public ChatController(ChatService chatService, RateLimiter rateLimiter, AppProperties properties) {
        this.chatService = chatService;
        this.rateLimiter = rateLimiter;
        this.properties = properties;
    }

    @PostMapping("/api/chat")
    public ChatResponse chat(@RequestBody ChatRequest req, HttpServletRequest http) {
        if (!rateLimiter.allow(clientIp(http))) {
            throw new ApiException(429, "请求过于频繁，请稍后重试");
        }
        List<String> images = validateImages(req.getImages());
        String message = req.getMessage() == null ? "" : req.getMessage().trim();
        if (message.isEmpty() && images.isEmpty()) {
            throw new ApiException(400, "消息内容不能为空");
        }
        return chatService.chat(req.getConversationId(), message, images);
    }

    @PostMapping(value = "/api/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter chatStream(@RequestBody ChatRequest req, HttpServletRequest http) {
        if (!rateLimiter.allow(clientIp(http))) {
            throw new ApiException(429, "请求过于频繁，请稍后重试");
        }
        List<String> images = validateImages(req.getImages());
        String message = req.getMessage() == null ? "" : req.getMessage().trim();
        if (message.isEmpty() && images.isEmpty()) {
            throw new ApiException(400, "消息内容不能为空");
        }
        SseEmitter emitter = new SseEmitter(120_000L);
        chatService.chatStream(req.getConversationId(), message, images, emitter);
        return emitter;
    }

    List<String> validateImages(List<String> images) {
        List<String> list = images == null ? List.of() : images;
        if (list.size() > properties.getUpload().getMaxCount()) {
            throw new ApiException(400,
                    "最多上传 " + properties.getUpload().getMaxCount() + " 张照片");
        }
        long maxBytes = properties.getUpload().getMaxSizeMb() * 1024L * 1024L;
        for (String url : list) {
            Matcher m = DATA_URL.matcher(url);
            if (!m.find()) {
                throw new ApiException(400, "不支持的图片格式，仅支持 JPG/PNG");
            }
            int payloadLen = url.length() - m.end();
            long approxBytes = (long) (payloadLen * 3 / 4.0);
            if (approxBytes > maxBytes) {
                throw new ApiException(400,
                        "图片超过 " + properties.getUpload().getMaxSizeMb() + "MB 限制");
            }
        }
        return list;
    }

    private String clientIp(HttpServletRequest http) {
        // I1：默认不信任 XFF（可伪造，限流 key 形同虚设）；仅 trust-x-forwarded-for=true
        // 且部署在可信代理之后时才取 XFF 首值，与 RecommendController 统一策略
        if (properties.getRateLimit().isTrustXForwardedFor()) {
            String fwd = http.getHeader("X-Forwarded-For");
            if (fwd != null && !fwd.isBlank()) {
                return fwd.split(",")[0].trim();
            }
        }
        return http.getRemoteAddr();
    }
}
