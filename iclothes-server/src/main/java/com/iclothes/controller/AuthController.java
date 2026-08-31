package com.iclothes.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import com.iclothes.dto.LoginRequest;
import com.iclothes.dto.LoginResponse;
import com.iclothes.dto.RegisterRequest;
import com.iclothes.dto.UserInfo;
import com.iclothes.service.AuthService;

/** 认证接口：注册 / 登录 / 当前用户。 */
@RestController
public class AuthController {

    private final AuthService service;

    public AuthController(AuthService service) {
        this.service = service;
    }

    @PostMapping("/api/auth/register")
    public UserInfo register(@RequestBody RegisterRequest req) {
        return service.register(req);
    }

    @PostMapping("/api/auth/login")
    public LoginResponse login(@RequestBody LoginRequest req) {
        return service.login(req);
    }

    /** 当前用户（userId 由 AuthFilter 解析注入）。 */
    @GetMapping("/api/auth/me")
    public UserInfo me(@RequestAttribute("userId") Long userId) {
        return service.me(userId);
    }
}
