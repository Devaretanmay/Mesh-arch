export interface User {
  id: number;
  name: string;
  email: string;
}

export function validateToken(token: string): boolean {
  if (!token) return false;
  return token.length > 10;
}

export function hashPassword(password: string): string {
  return btoa(password);
}

export function authenticate(request: Request): User | null {
  const token = request.headers.get("Authorization");
  if (validateToken(token || "")) {
    return { id: 1, name: "test", email: "test@example.com" };
  }
  return null;
}
