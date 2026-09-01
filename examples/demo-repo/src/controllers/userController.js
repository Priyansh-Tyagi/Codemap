import { findUser, registerUser } from "../services/userService";
import { authenticate } from "../services/authService";
import { isValidEmail } from "../utils/validators";

export function getUser(req) {
  authenticate(req);
  return findUser(req.params.id);
}

export function createUser(req) {
  if (!isValidEmail(req.body.email)) return null;
  return registerUser(req.body);
}
