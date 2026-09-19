import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

const ChatPage = lazy(() =>
  import("../pages/ChatPage").then((module) => ({ default: module.ChatPage })),
);
const HomePage = lazy(() =>
  import("../pages/HomePage").then((module) => ({ default: module.HomePage })),
);
const LibraryPage = lazy(() =>
  import("../pages/LibraryPage").then((module) => ({
    default: module.LibraryPage,
  })),
);
const SearchPage = lazy(() =>
  import("../pages/SearchPage").then((module) => ({ default: module.SearchPage })),
);

export function App() {
  return (
    <Suspense
      fallback={<div className="route-loading">Loading workspace...</div>}
    >
      <Routes>
        <Route path="/home" element={<HomePage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/:roomId" element={<ChatPage />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Routes>
    </Suspense>
  );
}
