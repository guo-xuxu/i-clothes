// RedisSessionLock.java
package com.iclothes.service;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisSessionLock implements SessionLock {

    private static final Logger log = LoggerFactory.getLogger(RedisSessionLock.class);
    private static final long TTL_SECONDS = 5;
    private static final long POLL_MS = 50;

    private final StringRedisTemplate redis;
    private final Map<String, ReentrantLock> fallbackLocks = new ConcurrentHashMap<>();

    public RedisSessionLock(StringRedisTemplate redis) { this.redis = redis; }

    @Override
    public boolean tryAcquire(String key, long waitMillis) {
        long deadline = System.currentTimeMillis() + waitMillis;
        try {
            do {
                Boolean ok = redis.opsForValue().setIfAbsent(key, "1", Duration.ofSeconds(TTL_SECONDS));
                if (Boolean.TRUE.equals(ok)) {
                    return true;
                }
                Thread.sleep(POLL_MS);
            } while (System.currentTimeMillis() < deadline);
            return false;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        } catch (Exception e) {
            // Redis 故障 → JVM 内锁降级（单实例有效）
            log.warn("Redis 不可用，会话锁降级为 JVM 内锁: {}", e.getMessage());
            return fallbackLocks.computeIfAbsent(key, k -> new ReentrantLock()).tryLock();
        }
    }

    @Override
    public void release(String key) {
        try {
            redis.delete(key);
        } catch (Exception e) {
            ReentrantLock lock = fallbackLocks.get(key);
            if (lock != null && lock.isHeldByCurrentThread()) {
                lock.unlock();
            }
        }
    }
}
