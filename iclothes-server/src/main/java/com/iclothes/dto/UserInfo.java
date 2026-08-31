package com.iclothes.dto;

/** 用户公开信息（不含密码），用于注册响应 / me / 登录响应内嵌。 */
public record UserInfo(Long id, String username) {}
