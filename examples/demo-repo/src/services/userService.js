import User from "../models/User";
import { issueToken } from "./authService";
import { isValidEmail } from "../utils/validators";

export function findUser(id) {
  return new User(id, "placeholder@example.com");
}

export function registerUser(data) {
  if (!isValidEmail(data.email)) return null;
  const user = new User(null, data.email);
  const token = issueToken(user);
  return { user, token };
}
