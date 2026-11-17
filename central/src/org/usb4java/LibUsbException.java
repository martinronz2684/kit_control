package org.usb4java;

public final class LibUsbException extends RuntimeException {
    private static final long serialVersionUID = 1L;
    private final int errorCode;

    public LibUsbException(String message, int errorCode) {
        super(message + " (" + errorCode + ")");
        this.errorCode = errorCode;
    }

    public LibUsbException(int errorCode) { this("USB-Fehler", errorCode); }

    public int getErrorCode() { return errorCode; }
}
