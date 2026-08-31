package com.iclothes.config;

import java.io.IOException;
import java.util.Set;
import org.springframework.web.filter.OncePerRequestFilter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/**
 * 认证过滤器：解析 JWT，把 userId 放入 request attribute，供 Controller 通过
 * {@code @RequestAttribute("userId")} 读取。
 *
 * 放行规则：
 *   - 非 /api/** 路径（前端静态资源、页面）直接放行；
 *   - 白名单（注册/登录/健康检查）放行；
 *   - 其余 /api/** 必须带有效 Bearer token，否则 401。
 */
public class AuthFilter extends OncePerRequestFilter {

    /** 供 Controller 读取 userId 的 request attribute 名。 */
    public static final String ATTR_USER_ID = "userId";

    private static final Set<String> WHITELIST = Set.of(
            "/api/auth/register",
            "/api/auth/login",
            "/api/health"
    );

    private final JwtUtil jwtUtil;

    public AuthFilter(JwtUtil jwtUtil) {
        this.jwtUtil = jwtUtil;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String path = request.getRequestURI();
        if (!path.startsWith("/api/") || WHITELIST.contains(path)) {
            chain.doFilter(request, response);
            return;
        }

        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ")) {
            send401(response);
            return;
        }
        try {
            Long userId = jwtUtil.parseUserId(header.substring(7));
            request.setAttribute(ATTR_USER_ID, userId);
            chain.doFilter(request, response);
        } catch (Exception e) {
            send401(response);
        }
    }

    private void send401(HttpServletResponse response) throws IOException {
        response.setStatus(401);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"detail\":\"未认证\"}");
    }
}
