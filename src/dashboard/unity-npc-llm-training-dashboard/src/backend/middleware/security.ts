import express from "express";
import rateLimit from "express-rate-limit";
import type { Request, Response, NextFunction } from "express";

/**
 * Path traversal protection middleware.
 * Blocks requests containing `..` or URL-encoded `%2e` in the URL.
 */
export function pathTraversalMiddleware(req: Request, res: Response, next: NextFunction): void {
  const url = req.originalUrl ?? req.url;
  if (url.includes("..") || url.toLowerCase().includes("%2e")) {
    res.status(400).json({ error: "Invalid path" });
    return;
  }
  next();
}

/**
 * Rate limiting middleware factory.
 * Creates a rate limiter with configurable window and max requests.
 */
export function rateLimitMiddleware(windowMs: number = 60_000, max: number = 100) {
  return rateLimit({
    windowMs,
    max,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: "Too many requests, please try again later." },
  });
}

/**
 * JSON body parser — standard express.json() with size limit.
 */
export const jsonBodyParser = express.json({ limit: "1mb" });
