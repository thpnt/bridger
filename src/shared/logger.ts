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
    if (process.env.DEBUG === "bridger") {
      console.log(message);
    }
  },
};
