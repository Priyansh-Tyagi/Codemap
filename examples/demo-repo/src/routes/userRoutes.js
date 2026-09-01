import { getUser, createUser } from "../controllers/userController";
import { isValidEmail } from "../utils/validators";

export function registerUserRoutes(router) {
  router.get("/users/:id", getUser);
  router.post("/users", (req) => (isValidEmail(req.body.email) ? createUser(req) : null));
}
