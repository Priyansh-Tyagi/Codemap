import { getOrder, createOrder } from "../controllers/orderController";
import { isNonEmptyString } from "../utils/validators";

export function registerOrderRoutes(router) {
  router.get("/orders/:id", getOrder);
  router.post("/orders", (req) => (isNonEmptyString(req.body.item) ? createOrder(req) : null));
}
