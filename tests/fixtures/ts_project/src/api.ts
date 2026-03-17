import { User, authenticate } from "./auth";

export interface Order {
  id: number;
  user_id: number;
  items: string[];
}

export function createOrder(userId: number, items: string[]): Order {
  return {
    id: Math.random(),
    user_id: userId,
    items,
  };
}

export function getUser(userId: number): User | null {
  return { id: userId, name: "test", email: "test@example.com" };
}

export function handleRequest(request: Request): any {
  const user = authenticate(request);
  if (!user) {
    return { error: "Unauthorized" };
  }

  const order = createOrder(user.id, ["item1", "item2"]);
  return { status: "success", order };
}
