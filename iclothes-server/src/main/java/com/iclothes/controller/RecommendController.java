package com.iclothes.controller;

import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import jakarta.servlet.http.HttpServletRequest;
import com.iclothes.config.AppProperties;
import com.iclothes.exception.ApiException;
import com.iclothes.service.ChatService;
import com.iclothes.service.RateLimiter;

/**
 * 「拍照推荐」接口：用户上传衣服照片，让 AI 给出穿搭建议。
 *
 * 与 ChatController 的区别：
 *   - ChatController：文字/图片聊天，有会话概念（多轮对话）
 *   - RecommendController：一次性推荐，无会话概念（conversationId 传 null）
 *
 * 接收的是 multipart/form-data 格式（文件上传），不是 JSON。
 */
@RestController
public class RecommendController {

    private final ChatService chatService;   // 复用聊天的业务逻辑（调 Python）
    private final RateLimiter rateLimiter;   // 限流
    private final AppProperties properties;  // 读取上传限制等配置

    // 构造器注入（Spring 自动传入依赖）
    public RecommendController(ChatService chatService, RateLimiter rateLimiter, AppProperties properties) {
        this.chatService = chatService;
        this.rateLimiter = rateLimiter;
        this.properties = properties;
    }

    /**
     * 推荐接口
     * 请求：POST /api/recommend （multipart/form-data）
     * 参数：
     *   - images：上传的照片文件（可多张），required=false 表示可选
     *   - description：用户补充的文字描述（可选，默认空串）
     * 返回：{"suggestion": "AI 给出的穿搭建议"}
     *
     * 完整流程：限流 → 校验图片 → 图片转 base64 → 调 ChatService（进而调 Python）→ 返回建议
     */
    @PostMapping("/api/recommend")
    public Map<String, String> recommend(
            // @RequestParam 从表单里取参数；MultipartFile 表示上传的文件
            @RequestParam(value = "images", required = false) List<MultipartFile> images,
            @RequestParam(value = "description", defaultValue = "") String description,
            @RequestAttribute("userId") Long userId,
            HttpServletRequest http) {

        // ① 限流：同一 IP 太频繁直接拒绝（429）
        if (!rateLimiter.allow(clientIp(http))) {
            throw new ApiException(429, "请求过于频繁，请稍后重试");
        }

        // ② 校验：至少要有一张照片
        if (images == null || images.isEmpty()) {
            throw new ApiException(400, "请至少上传一张照片");
        }

        // ③ 校验：照片数量不能超过上限（配置里的 maxCount，默认 3）
        if (images.size() > properties.getUpload().getMaxCount()) {
            throw new ApiException(400,
                    "最多上传 " + properties.getUpload().getMaxCount() + " 张照片");
        }

        // ④ 计算单张图片最大字节数（配置里的 maxSizeMb，默认 5MB）
        long maxBytes = properties.getUpload().getMaxSizeMb() * 1024L * 1024L;
        List<String> urls = new ArrayList<>();

        // ⑤ 逐张校验并转换
        for (MultipartFile f : images) {
            // 校验图片格式：只允许 JPG/PNG
            if (f.getContentType() == null
                    || !(f.getContentType().equals("image/jpeg") || f.getContentType().equals("image/png"))) {
                throw new ApiException(400,
                        "不支持的图片格式：" + f.getContentType() + "，仅支持 JPG/PNG");
            }
            // 校验图片大小
            if (f.getSize() > maxBytes) {
                throw new ApiException(400,
                        "图片 " + f.getOriginalFilename() + " 超过 "
                                + properties.getUpload().getMaxSizeMb() + "MB 限制");
            }
            // 把图片二进制转成 base64 字符串，拼成 data URL：
            //   格式：data:image/jpeg;base64,xxxxxx
            // 这样就能把图片塞进 JSON 发给 Python（Python 端需要这种格式）
            try {
                urls.add("data:" + f.getContentType() + ";base64,"
                        + Base64.getEncoder().encodeToString(f.getBytes()));
            } catch (java.io.IOException e) {
                throw new ApiException(400, "读取图片失败：" + f.getOriginalFilename());
            }
        }

        // ⑥ 调 ChatService（conversationId 传 null，表示一次性推荐、无会话）
        var resp = chatService.chat(userId, null, description, urls);
        // ⑦ 只返回 AI 的回复，包装成 {"suggestion": "..."}
        return Map.of("suggestion", resp.getReply());
    }

    /**
     * 获取客户端 IP（用于限流统计）。
     * 与 ChatController 统一策略：
     *   - 默认用 request.getRemoteAddr()（直接连接的 IP）
     *   - 只有当配置 trust-x-forwarded-for=true（部署在可信反向代理后）时，
     *     才取 X-Forwarded-For 头部的第一个值。
     *   默认不信任 XFF，防止伪造 IP 绕过限流。
     */
    private String clientIp(HttpServletRequest http) {
        if (properties.getRateLimit().isTrustXForwardedFor()) {
            String fwd = http.getHeader("X-Forwarded-For");
            if (fwd != null && !fwd.isBlank()) {
                return fwd.split(",")[0].trim();   // 取第一个（真实客户端 IP）
            }
        }
        return http.getRemoteAddr();
    }
}
