package com.iclothes.exception;

public class AgentUnavailableException extends RuntimeException {
    public AgentUnavailableException(String message) { super(message); }
    public AgentUnavailableException(String message, Throwable cause) { super(message, cause); }
}
