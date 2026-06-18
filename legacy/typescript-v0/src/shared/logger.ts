function isDebugLoggingEnabled(): boolean {
  if (process.env.DEBUG === "bridger") {
    return true;
  }

  return process.env.npm_lifecycle_event === "dev";
}

export const logger = {
  info(message: string): void {
    console.log(message);
  },

  warn(message: string): void {
    console.warn(`Warning: ${message}`);
  },

  error(message: string): void {
    console.error(`Error: ${message}`);
  },

  debug(message: string): void {
    if (isDebugLoggingEnabled()) {
      console.log(message);
    }
  },
};
