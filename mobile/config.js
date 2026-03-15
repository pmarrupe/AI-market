// Set this to your backend URL (EC2 or local). No trailing slash.
// For local dev: "http://localhost:8000" (use your machine's IP for device: "http://192.168.x.x:8000")
export const API_BASE =
  typeof process !== "undefined" && process.env?.EXPO_PUBLIC_API_URL
    ? process.env.EXPO_PUBLIC_API_URL
    : "http://98.84.157.50:8000";
