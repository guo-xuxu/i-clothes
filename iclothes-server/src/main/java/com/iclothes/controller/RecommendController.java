package com.iclothes.controller;

import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import jakarta.servlet.http.HttpServletRequest;
import com.iclothes.config.AppProperties;
import com.iclothes.exception.ApiException;
import com.iclothes.service.ChatService;
import com.iclothes.service.RateLimiter;

@RestController
public class RecommendController {

    private final ChatService chatService;
    private final RateLimiter rateLimiter;
    private final AppProperties properties;

    public RecommendController(ChatService chatService, RateLimiter rateLimiter, AppProperties properties) {
        this.chatService = chatService;
        this.rateLimiter = rateLimiter;
        this.properties = properties;
    }

    @PostMapping("/api/recommend")
    public Map<String, String> recommend(
            @RequestParam(value = "images", required = false) List<MultipartFile> images,
            @RequestParam(value = "description", defaultValue = "") String description,
            HttpServletRequest http) {
        if (!rateLimiter.allow(clientIp(http))) {
            throw new ApiException(429, "请求过于频繁，请稍后重试");
        }
        if (images == null || images.isEmpty()) {
            throw new ApiException(400, "请至少上传一张照片");
        }
        if (images.size() > properties.getUpload().getMaxCount()) {
            throw new ApiException(400,
                    "最多上传 " + properties.getUpload().getMaxCount() + " 张照片");
        }
        long maxBytes = properties.getUpload().getMaxSizeMb() * 1024L * 1024L;
        List<String> urls = new ArrayList<>();
        for (MultipartFile f : images) {
            if (f.getContentType() == null
                    || !(f.getContentType().equals("image/jpeg") || f.getContentType().equals("image/png"))) {
                throw new ApiException(400,
                        "不支持的图片格式：" + f.getContentType() + "，仅支持 JPG/PNG");
            }
            if (f.getSize() > maxBytes) {
                throw new ApiException(400,
                        "图片 " + f.getOriginalFilename() + " 超过 "
                                + properties.getUpload().getMaxSizeMb() + "MB 限制");
            }
            try {
                urls.add("data:" + f.getContentType() + ";base64,"
                        + Base64.getEncoder().encodeToString(f.getBytes()));
            } catch (java.io.IOException e) {
                throw new ApiException(400, "读取图片失败：" + f.getOriginalFilename());
            }
        }
        var resp = chatService.chat(null, description, urls);
        return Map.of("suggestion", resp.getReply());
    }

    private String clientIp(HttpServletRequest http) {
        // 与 ChatController 统一：默认用 remoteAddr，仅 trust-x-forwarded-for=true 时取 XFF 首值
        if (properties.getRateLimit().isTrustXForwardedFor()) {
            String fwd = http.getHeader("X-Forwarded-For");
            if (fwd != null && !fwd.isBlank()) {
                return fwd.split(",")[0].trim();
            }
        }
        return http.getRemoteAddr();
    }
}
