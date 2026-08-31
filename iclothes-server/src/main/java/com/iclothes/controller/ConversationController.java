package com.iclothes.controller;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;
import com.iclothes.dto.ConversationDto;
import com.iclothes.dto.ConversationSummaryDto;
import com.iclothes.exception.ApiException;
import com.iclothes.service.ConversationService;

/**
 * 会话管理接口：负责「会话（对话）」的新建、列表、查看、删除。
 *
 * 注意：这个 Controller 只管「会话」这个对象本身的 CRUD，
 * 不做 AI 聊天逻辑（聊天在 ChatController）。可以理解为：
 *   - ConversationController = 管理「对话框」（有几个对话、标题、删哪个）
 *   - ChatController          = 在某个对话框里「发消息、得回复」
 *
 * 请求路径都以 /api/conversations 开头。
 */
@RestController   // 标记这是一个 REST 接口控制器（返回 JSON，不是页面）
public class ConversationController {

    // 依赖注入：业务逻辑在 ConversationService 里，Controller 只负责转发
    private final ConversationService service;

    // 构造器注入（Spring 会自动把 ConversationService 传进来）
    public ConversationController(ConversationService service) { this.service = service; }

    /**
     * ① 新建会话
     * 请求：POST /api/conversations
     * 作用：创建一个空的新对话，返回它的 id、标题、时间等信息。
     */
    @PostMapping("/api/conversations")
    public ConversationDto create(@RequestAttribute("userId") Long userId) {
        return service.create(userId);
    }

    /**
     * ② 列出所有会话
     * 请求：GET /api/conversations
     * 作用：返回所有会话的「摘要」（id + 标题 + 时间），
     *       不含消息内容——因为列表页（侧边栏）只需要显示标题，不需要加载全部消息。
     * 返回类型是 ConversationSummaryDto（摘要），不是 ConversationDto（详情）。
     */
    @GetMapping("/api/conversations")
    public List<ConversationSummaryDto> list(@RequestAttribute("userId") Long userId) {
        return service.listSummaries(userId);
    }

    /**
     * ③ 查看某个会话的详情
     * 请求：GET /api/conversations/{id}
     * 作用：返回指定会话的完整信息，包含它下面所有的消息。
     * @PathVariable 会提取 URL 路径里的 {id}，
     * 例如 GET /api/conversations/abc123 → id = "abc123"
     */
    @GetMapping("/api/conversations/{id}")
    public ConversationDto get(@PathVariable String id, @RequestAttribute("userId") Long userId) {
        // 先把字符串 id 转成 UUID，再查库；查不到就返回 404
        ConversationDto dto = service.get(userId, parseUuid(id));
        if (dto == null) throw new ApiException(404, "会话不存在");
        return dto;
    }

    /**
     * ④ 删除某个会话
     * 请求：DELETE /api/conversations/{id}
     * 作用：删除指定会话（及其消息）。
     * 删除成功返回 {"ok": true}，失败（不存在）返回 404。
     */
    @DeleteMapping("/api/conversations/{id}")
    public Map<String, Boolean> delete(@PathVariable String id, @RequestAttribute("userId") Long userId) {
        if (!service.delete(userId, parseUuid(id))) throw new ApiException(404, "会话不存在");
        return Map.of("ok", true);
    }

    /**
     * 工具方法：把字符串 id 安全地转成 UUID。
     *
     * 为什么要转？
     *  - URL 里的 {id} 永远是字符串，但数据库里存的是 UUID 类型，所以要先转换。
     *  - 如果传入的不是合法 UUID（比如用户乱填 "hello"），UUID.fromString 会抛异常，
     *    这里捕获后统一当成「会话不存在」返回 404，避免报 500 暴露内部错误。
     */
    private UUID parseUuid(String id) {
        try {
            return UUID.fromString(id);
        } catch (IllegalArgumentException e) {
            throw new ApiException(404, "会话不存在");
        }
    }
}
