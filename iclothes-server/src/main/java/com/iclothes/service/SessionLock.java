// SessionLock.java
package com.iclothes.service;

public interface SessionLock {
    /** 尝试获取锁；waitMillis 内轮询，超时返回 false。 */
    boolean tryAcquire(String key, long waitMillis);

    /** 释放锁（必须与 tryAcquire 成对）。 */
    void release(String key);
}
