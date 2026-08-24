package com.iclothes.controller;

import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import com.iclothes.exception.AgentUnavailableException;
import com.iclothes.exception.AgentValidationException;
import com.iclothes.exception.ApiException;

/**
 * 全局异常处理器：统一处理整个应用里抛出的异常，并转成规范的 JSON 错误响应。
 *
 * 为什么要它？
 *  如果没有这个类，任何一个 Controller 抛异常，Spring 都会返回默认的
 *  错误页面/结构（字段是 timestamp、status、error、path...），而且
 *  内部异常细节可能泄露给前端。有了它，我们可以：
 *    1. 统一错误响应格式：{"detail": "错误信息"}
 *    2. 控制每个异常对应什么 HTTP 状态码
 *    3. 记录日志，避免异常被静默吞掉
 *
 * @RestControllerAdvice = @ControllerAdvice + @ResponseBody
 *   意思是：拦截所有 Controller 抛出的异常，并返回 JSON（而不是错误页面）。
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    /**
     * 处理业务异常 ApiException（我们自己主动抛的、已知的错误）。
     * 例：400（参数错误）、404（会话不存在）、429（限流）、503（加锁失败）...
     * 用异常自带的 status 作为 HTTP 状态码，message 作为错误内容返回。
     */
    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, String>> apiError(ApiException e) {
        // 返回 e.getStatus() 状态码 + {"detail": "错误信息"}
        return ResponseEntity.status(e.getStatus()).body(Map.of("detail", e.getMessage()));
    }

    /**
     * 处理 AI 服务不可用异常（AgentUnavailableException）。
     * 例：Python 服务挂了、连接超时、返回非 400 的错误 → 统一按 502（网关错误）返回。
     * 502 的含义：作为网关/中转，调下游（Python）失败了。
     */
    @ExceptionHandler(AgentUnavailableException.class)
    public ResponseEntity<Map<String, String>> agentDown(AgentUnavailableException e) {
        return ResponseEntity.status(502).body(Map.of("detail", e.getMessage()));
    }

    /**
     * 处理 AI 校验异常（AgentValidationException）。
     * 例：Python 返回 400（用户输入不合法，如消息为空）→ 按 400 返回给用户。
     */
    @ExceptionHandler(AgentValidationException.class)
    public ResponseEntity<Map<String, String>> agentValidation(AgentValidationException e) {
        return ResponseEntity.status(400).body(Map.of("detail", e.getMessage()));
    }

    /**
     * 兜底：处理上面没覆盖到的所有其他异常（Exception 是它们的父类）。
     * 例：空指针、数据库错误等未预期的问题。
     * 关键点：
     *   1. 记录完整日志（含堆栈），方便排查——这是"故障可观测"的关键。
     *   2. 返回给前端时只给一句"服务器内部错误"，不泄露内部细节（如 SQL、堆栈）。
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> internal(Exception e) {
        log.error("unhandled error", e);   // 记完整日志，含堆栈
        return ResponseEntity.status(500).body(Map.of("detail", "服务器内部错误"));
    }
}
