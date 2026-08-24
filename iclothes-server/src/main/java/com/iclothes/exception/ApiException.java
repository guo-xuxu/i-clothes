package com.iclothes.exception;

public class ApiException extends RuntimeException {
    private final int status;
    public ApiException(int status, String detail) {
        super(detail);
        this.status = status;
    }
    public int getStatus() { return status; }
}
