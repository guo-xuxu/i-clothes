// RateLimiterTest.java
package com.iclothes.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import com.iclothes.config.AppProperties;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class RateLimiterTest {

    @Mock StringRedisTemplate redis;
    @Mock ValueOperations<String, String> ops;

    private AppProperties props() {
        AppProperties p = new AppProperties();
        p.getRateLimit().setPerMinute(60);
        return p;
    }

    @Test
    void allowWithinThreshold() {
        when(redis.opsForValue()).thenReturn(ops);
        when(ops.increment(anyString())).thenReturn(5L);

        RateLimiter limiter = new RateLimiter(redis, props());
        assertThat(limiter.allow("127.0.0.1")).isTrue();
    }

    @Test
    void denyAboveThreshold() {
        when(redis.opsForValue()).thenReturn(ops);
        when(ops.increment(anyString())).thenReturn(61L);

        RateLimiter limiter = new RateLimiter(redis, props());
        assertThat(limiter.allow("127.0.0.1")).isFalse();
    }

    @Test
    void failOpenWhenRedisDown() {
        when(redis.opsForValue()).thenThrow(new RuntimeException("redis down"));

        RateLimiter limiter = new RateLimiter(redis, props());
        assertThat(limiter.allow("127.0.0.1")).isTrue();
    }
}
