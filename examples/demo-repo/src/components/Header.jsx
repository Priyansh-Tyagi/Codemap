import { useAuth } from "../hooks/useAuth";

export default function Header() {
  const user = useAuth();
  return { type: "header", user };
}
