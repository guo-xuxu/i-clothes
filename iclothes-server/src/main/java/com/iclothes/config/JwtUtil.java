package com.iclothes.config;

import java.nio.charset.StandardCharsets;
import java.util.Date;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Component;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;

/** JWT 工具：生成/解析 token（HS256，payload 存 userId + username）。 */
@Component
public class JwtUtil {

    private final SecretKey key;
    private final long expireDays;

    public JwtUtil(AppProperties props) {
        this.key = Keys.hmacShaKeyFor(props.getJwt().getSecret().getBytes(StandardCharsets.UTF_8));
        this.expireDays = props.getJwt().getExpireDays();
    }

    /** 生成 token：sub=userId，claim username，有效期 expireDays 天。 */
    public String generate(Long userId, String username) {
        long now = System.currentTimeMillis();
        return Jwts.builder()
                .subject(String.valueOf(userId))
                .claim("username", username)
                .issuedAt(new Date(now))
                .expiration(new Date(now + expireDays * 24 * 3600 * 1000L))
                .signWith(key)
                .compact();
    }

    /** 解析 token 返回 userId；token 无效/过期抛 JwtException。 */
    public Long parseUserId(String token) {
        Claims claims = Jwts.parser()
                .verifyWith(key)
                .build()
                .parseSignedClaims(token)
                .getPayload();
        return Long.valueOf(claims.getSubject());
    }
}
