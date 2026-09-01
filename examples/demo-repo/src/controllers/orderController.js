import { findOrder, placeOrder } from "../services/orderService";
import { isNonEmptyString } from "../utils/validators";
import { formatDate } from "../utils/formatDate";

export function getOrder(req) {
  const order = findOrder(req.params.id);
  return { ...order, placedOn: formatDate(Date.now()) };
}

export function createOrder(req) {
  if (!isNonEmptyString(req.body.item)) return null;
  return placeOrder(req.body);
}
