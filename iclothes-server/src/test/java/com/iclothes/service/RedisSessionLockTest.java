// RedisSessionLockTest.java
package com.iclothes.service;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class RedisSessionLockTest {

    @Mock StringRedisTemplate redis;
    @Mock ValueOperations<String, String> ops;

    @Test
    void acquireSuccessWhenRedisSetsKey() {
        when(redis.opsForValue()).thenReturn(ops);
        when(ops.setIfAbsent(anyString(), anyString(), any(Duration.class))).thenReturn(Boolean.TRUE);

        RedisSessionLock lock = new RedisSessionLock(redis);
        assertThat(lock.tryAcquire("conversation:abc:lock", 1000)).isTrue();
    }

    @Test
    void acquireFailsWhenKeyHeld() {
        when(redis.opsForValue()).thenReturn(ops);
        when(ops.setIfAbsent(anyString(), anyString(), any(Duration.class))).thenReturn(Boolean.FALSE);

        RedisSessionLock lock = new RedisSessionLock(redis);
        assertThat(lock.tryAcquire("conversation:abc:lock", 120)).isFalse();
    }

    @Test
    void acquireFallsBackToJvmLockWhenRedisDown() {
        when(redis.opsForValue()).thenThrow(new RuntimeException("redis down"));

        RedisSessionLock lock = new RedisSessionLock(redis);
        assertThat(lock.tryAcquire("conversation:abc:lock", 100)).isTrue();
        lock.release("conversation:abc:lock");
    }

    @Test
    void releaseDeletesKey() {
        RedisSessionLock lock = new RedisSessionLock(redis);
        lock.release("conversation:abc:lock");
        verify(redis).delete("conversation:abc:lock");
    }
}
