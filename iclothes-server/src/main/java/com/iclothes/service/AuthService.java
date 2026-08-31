package com.iclothes.service;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.iclothes.config.JwtUtil;
import com.iclothes.dto.LoginRequest;
import com.iclothes.dto.LoginResponse;
import com.iclothes.dto.RegisterRequest;
import com.iclothes.dto.UserInfo;
import com.iclothes.entity.User;
import com.iclothes.exception.ApiException;
import com.iclothes.repository.UserMapper;

/** 认证服务：注册 / 登录 / 当前用户。密码 BCrypt，登录签发 JWT。 */
@Service
public class AuthService {

    private final UserMapper users;
    private final JwtUtil jwtUtil;
    private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();

    public AuthService(UserMapper users, JwtUtil jwtUtil) {
        this.users = users;
        this.jwtUtil = jwtUtil;
    }

    public UserInfo register(RegisterRequest req) {
        String username = req.username() == null ? "" : req.username().trim();
        String password = req.password() == null ? "" : req.password();
        if (username.length() < 3 || username.length() > 64) {
            throw new ApiException(400, "用户名长度需在 3-64 之间");
        }
        if (password.length() < 6 || password.length() > 72) {
            throw new ApiException(400, "密码长度需在 6-72 之间");
        }
        Long count = users.selectCount(new LambdaQueryWrapper<User>().eq(User::getUsername, username));
        if (count > 0) {
            throw new ApiException(409, "用户名已存在");
        }
        User u = new User(username, encoder.encode(password));
        users.insert(u);
        return new UserInfo(u.getId(), u.getUsername());
    }

    public LoginResponse login(LoginRequest req) {
        String username = req.username() == null ? "" : req.username().trim();
        String password = req.password() == null ? "" : req.password();
        User u = users.selectOne(new LambdaQueryWrapper<User>().eq(User::getUsername, username));
        if (u == null || !encoder.matches(password, u.getPassword())) {
            throw new ApiException(401, "用户名或密码错误");
        }
        String token = jwtUtil.generate(u.getId(), u.getUsername());
        return new LoginResponse(token, new UserInfo(u.getId(), u.getUsername()));
    }

    public UserInfo me(Long userId) {
        User u = users.selectById(userId);
        if (u == null) {
            throw new ApiException(401, "未认证");
        }
        return new UserInfo(u.getId(), u.getUsername());
    }
}
