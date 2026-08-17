package com.iclothes.controller;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import com.iclothes.dto.ConversationDto;
import com.iclothes.dto.ConversationSummaryDto;
import com.iclothes.exception.ApiException;
import com.iclothes.service.ConversationService;

@RestController
public class ConversationController {

    private final ConversationService service;

    public ConversationController(ConversationService service) { this.service = service; }

    @PostMapping("/api/conversations")
    public ConversationDto create() {
        return service.create();
    }

    @GetMapping("/api/conversations")
    public List<ConversationSummaryDto> list() {
        return service.listSummaries();
    }

    @GetMapping("/api/conversations/{id}")
    public ConversationDto get(@PathVariable String id) {
        ConversationDto dto = service.get(parseUuid(id));
        if (dto == null) throw new ApiException(404, "会话不存在");
        return dto;
    }

    @DeleteMapping("/api/conversations/{id}")
    public Map<String, Boolean> delete(@PathVariable String id) {
        if (!service.delete(parseUuid(id))) throw new ApiException(404, "会话不存在");
        return Map.of("ok", true);
    }

    private UUID parseUuid(String id) {
        try {
            return UUID.fromString(id);
        } catch (IllegalArgumentException e) {
            throw new ApiException(404, "会话不存在");
        }
    }
}
