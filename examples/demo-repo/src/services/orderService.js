import Order from "../models/Order";
import { findUser } from "./userService";
import { isNonEmptyString } from "../utils/validators";

export function findOrder(id) {
  return new Order(id, null);
}

export function placeOrder(data) {
  if (!isNonEmptyString(data.item)) return null;
  const user = findUser(data.userId);
  return new Order(null, user, data.item);
}
