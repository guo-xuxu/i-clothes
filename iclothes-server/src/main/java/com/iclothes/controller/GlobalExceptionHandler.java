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

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, String>> apiError(ApiException e) {
        return ResponseEntity.status(e.getStatus()).body(Map.of("detail", e.getMessage()));
    }

    @ExceptionHandler(AgentUnavailableException.class)
    public ResponseEntity<Map<String, String>> agentDown(AgentUnavailableException e) {
        return ResponseEntity.status(502).body(Map.of("detail", e.getMessage()));
    }

    @ExceptionHandler(AgentValidationException.class)
    public ResponseEntity<Map<String, String>> agentValidation(AgentValidationException e) {
        return ResponseEntity.status(400).body(Map.of("detail", e.getMessage()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> internal(Exception e) {
        log.error("unhandled error", e);
        return ResponseEntity.status(500).body(Map.of("detail", "服务器内部错误"));
    }
}
