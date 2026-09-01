import Header from "./components/Header";
import Footer from "./components/Footer";
import userRoutes from "./routes/userRoutes";
import orderRoutes from "./routes/orderRoutes";

export function startApp() {
  return { Header, Footer, userRoutes, orderRoutes };
}
