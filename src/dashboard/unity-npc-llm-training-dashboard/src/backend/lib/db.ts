import pg from "pg";
import { logger } from "./logger";

/**
 * Reads database config from environment variables, falling back
 * to local Supabase defaults (matching docker-compose or supabase start).
 */
function readDbConfig(): pg.PoolConfig {
  const url = process.env.DATABASE_URL || process.env.SUPABASE_DB_URL || "";
  if (url) {
    return { connectionString: url };
  }

  return {
    host: process.env.PGHOST || "127.0.0.1",
    port: Number(process.env.PGPORT || 15434),
    user: process.env.PGUSER || "postgres",
    password: process.env.PGPASSWORD || "postgres",
    database: process.env.PGDATABASE || "postgres",
  };
}

let pool: pg.Pool | null = null;

function getPool(): pg.Pool {
  if (!pool) {
    const config = readDbConfig();
    pool = new pg.Pool(config);

    pool.on("error", (err) => {
      logger.error("Unexpected PostgreSQL pool error", { error: err.message });
    });
  }
  return pool;
}

/**
 * Execute a query against the PostgreSQL pool.
 * Returns rows from the result, or throws on error.
 */
export async function query<T extends Record<string, unknown> = Record<string, unknown>>(
  text: string,
  params?: unknown[],
): Promise<T[]> {
  const client = await getPool().connect();
  try {
    const result = await client.query<T>(text, params);
    return result.rows;
  } finally {
    client.release();
  }
}

/**
 * Health check: test the database connection.
 * Returns true if the pool can acquire a client and run a simple query.
 */
export async function healthCheck(): Promise<boolean> {
  try {
    const client = await getPool().connect();
    try {
      await client.query("SELECT 1");
      return true;
    } finally {
      client.release();
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    logger.warn("Database health check failed", { error: message });
    return false;
  }
}

/**
 * Gracefully shut down the pool (e.g. on server close).
 */
export async function closePool(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = null;
  }
}

export { getPool };
