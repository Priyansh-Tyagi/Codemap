import { authenticate } from "../services/authService";

export function useAuth() {
  return authenticate({ headers: {} });
}
