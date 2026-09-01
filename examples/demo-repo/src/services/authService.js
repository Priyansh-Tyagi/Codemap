import { findUser } from "./userService";

export function issueToken(user) {
  return `token-for-${user.id ?? "new"}`;
}

export function verifyToken(token) {
  const id = token.replace("token-for-", "");
  return findUser(id);
}

export function authenticate(req) {
  const token = req.headers?.authorization;
  return token ? verifyToken(token) : null;
}
