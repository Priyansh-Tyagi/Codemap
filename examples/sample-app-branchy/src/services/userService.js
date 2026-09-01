import User from "../models/User";
import { formatName } from "../utils/format";
export function fetchUser() { return formatName(new User()); }
