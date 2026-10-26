import { Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import ProjectPage from "./pages/ProjectPage";
import ServerBanner from "./components/ServerBanner";
import { useServerStatus } from "./hooks/useServerStatus";
import { ServerStatusContext } from "./hooks/serverStatusContext";

export default function App() {
  // One status check for the whole app: it wakes a sleeping host the moment any
  // page opens (including a shared /p/:id link), explains the wait, and tells
  // pages whether saved projects will survive a restart.
  const status = useServerStatus();
  return (
    <ServerStatusContext.Provider value={status}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/p/:projectId" element={<ProjectPage />} />
        <Route path="*" element={<HomePage />} />
      </Routes>
      <ServerBanner
        phase={status.phase}
        elapsedSeconds={status.elapsedSeconds}
        storage={status.storage}
        onRetry={status.retry}
      />
    </ServerStatusContext.Provider>
  );
}
