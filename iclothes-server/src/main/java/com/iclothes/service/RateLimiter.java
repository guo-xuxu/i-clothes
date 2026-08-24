// RateLimiter.java
package com.iclothes.service;

import java.time.Duration;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import com.iclothes.config.AppProperties;

@Component
public class RateLimiter {

    private static final Logger log = LoggerFactory.getLogger(RateLimiter.class);
    private static final DateTimeFormatter MINUTE = DateTimeFormatter.ofPattern("yyyyMMddHHmm");

    private final StringRedisTemplate redis;
    private final AppProperties properties;

    public RateLimiter(StringRedisTemplate redis, AppProperties properties) {
        this.redis = redis;
        this.properties = properties;
    }

    /** 按客户端标识限流；Redis 故障 fail-open（放行 + 告警）。 */
    public boolean allow(String clientKey) {
        try {
            String key = "rate:" + clientKey + ":" + MINUTE.format(LocalDateTime.now());
            Long count = redis.opsForValue().increment(key);
            if (count != null && count == 1) {
                redis.expire(key, Duration.ofSeconds(61));
            }
            return count == null || count <= properties.getRateLimit().getPerMinute();
        } catch (Exception e) {
            log.warn("Redis 不可用，限流 fail-open: {}", e.getMessage());
            return true;
        }
    }
}
