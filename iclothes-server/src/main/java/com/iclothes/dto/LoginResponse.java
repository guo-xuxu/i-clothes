package com.iclothes.dto;

/** 登录响应体。 */
public record LoginResponse(String token, UserInfo user) {}
