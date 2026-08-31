package com.iclothes.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "iclothes")
public class AppProperties {

    private final Upload upload = new Upload();
    private final Agent agent = new Agent();
    private final RateLimit rateLimit = new RateLimit();
    private final Frontend frontend = new Frontend();
    private final Jwt jwt = new Jwt();

    public Upload getUpload() { return upload; }
    public Agent getAgent() { return agent; }
    public RateLimit getRateLimit() { return rateLimit; }
    public Frontend getFrontend() { return frontend; }
    public Jwt getJwt() { return jwt; }

    public static class Upload {
        private int maxCount = 3;
        private int maxSizeMb = 5;
        public int getMaxCount() { return maxCount; }
        public void setMaxCount(int v) { maxCount = v; }
        public int getMaxSizeMb() { return maxSizeMb; }
        public void setMaxSizeMb(int v) { maxSizeMb = v; }
    }

    public static class Agent {
        private String baseUrl = "http://127.0.0.1:8000";
        private int connectTimeoutMs = 3000;
        private int readTimeoutMs = 60000;
        private int healthTimeoutMs = 2000;
        public String getBaseUrl() { return baseUrl; }
        public void setBaseUrl(String v) { baseUrl = v; }
        public int getConnectTimeoutMs() { return connectTimeoutMs; }
        public void setConnectTimeoutMs(int v) { connectTimeoutMs = v; }
        public int getReadTimeoutMs() { return readTimeoutMs; }
        public void setReadTimeoutMs(int v) { readTimeoutMs = v; }
        public int getHealthTimeoutMs() { return healthTimeoutMs; }
        public void setHealthTimeoutMs(int v) { healthTimeoutMs = v; }
    }

    public static class RateLimit {
        private int perMinute = 60;
        /** 是否信任 X-Forwarded-For 首值作为客户端 IP（仅部署在可信反向代理之后时开启，默认 false 防伪造）。 */
        private boolean trustXForwardedFor = false;
        public int getPerMinute() { return perMinute; }
        public void setPerMinute(int v) { perMinute = v; }
        public boolean isTrustXForwardedFor() { return trustXForwardedFor; }
        public void setTrustXForwardedFor(boolean v) { trustXForwardedFor = v; }
    }

    public static class Frontend {
        private String dir = "frontend/dist";
        public String getDir() { return dir; }
        public void setDir(String v) { dir = v; }
    }

    public static class Jwt {
        private String secret = "change-me-change-me-change-me-change-me";
        private long expireDays = 7;
        public String getSecret() { return secret; }
        public void setSecret(String v) { secret = v; }
        public long getExpireDays() { return expireDays; }
        public void setExpireDays(long v) { expireDays = v; }
    }
}
