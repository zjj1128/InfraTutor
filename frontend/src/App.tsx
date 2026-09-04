import { AlertTriangle, LoaderCircle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  abandonTutorSession,
  fetchRoadmap,
  resetLearner,
  startTutorSession,
} from "./api/client";
import { RoadmapDashboard } from "./components/RoadmapDashboard";
import { TutorSessionPage } from "./components/TutorSessionPage";
import type { RoadmapData, SeedName } from "./types/roadmap";
import type { EntryMode } from "./types/session";

function currentPath() {
  return window.location.pathname;
}

export default function App() {
  const [roadmap, setRoadmap] = useState<RoadmapData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);
  const [isResetting, setIsResetting] = useState(false);
  const [requestVersion, setRequestVersion] = useState(0);
  const [path, setPath] = useState(currentPath);

  const navigate = useCallback((nextPath: string) => {
    window.history.pushState({}, "", nextPath);
    setPath(nextPath);
  }, []);

  useEffect(() => {
    const handlePopState = () => setPath(currentPath());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const retry = useCallback(() => {
    setRoadmap(null);
    setError(null);
    setRequestVersion((value) => value + 1);
  }, []);

  useEffect(() => {
    if (path.startsWith("/learn/")) return;
    const controller = new AbortController();

    fetchRoadmap(controller.signal)
      .then(setRoadmap)
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "路线加载失败");
      });

    return () => controller.abort();
  }, [path, requestVersion]);

  const handleReset = useCallback(async (seed: SeedName) => {
    setIsResetting(true);
    setResetError(null);
    try {
      await resetLearner(seed);
      setRoadmap(await fetchRoadmap());
    } catch (reason: unknown) {
      setResetError(reason instanceof Error ? reason.message : "学习状态重置失败");
    } finally {
      setIsResetting(false);
    }
  }, []);

  const handleStartSession = useCallback(
    async (nodeId: string, entryMode: EntryMode) => {
      const session = await startTutorSession(nodeId, entryMode);
      navigate(`/learn/${session.session_id}`);
    },
    [navigate],
  );

  const handleAbandonSession = useCallback(async (sessionId: string, version: number) => {
    await abandonTutorSession(sessionId, version);
  }, []);

  const sessionMatch = path.match(/^\/learn\/([^/]+)$/);
  if (sessionMatch) {
    return <TutorSessionPage sessionId={decodeURIComponent(sessionMatch[1])} onNavigate={navigate} />;
  }

  if (error) {
    return (
      <main className="centered-state" role="alert">
        <AlertTriangle size={28} aria-hidden="true" />
        <h1>课程路线暂时无法加载</h1>
        <p>{error}</p>
        <button type="button" onClick={retry}>
          <RefreshCw size={17} aria-hidden="true" />
          重新加载
        </button>
      </main>
    );
  }

  if (!roadmap) {
    return (
      <main className="centered-state loading-state" aria-live="polite">
        <LoaderCircle className="spinner" size={28} aria-hidden="true" />
        <span>正在加载课程图谱</span>
      </main>
    );
  }

  return (
    <RoadmapDashboard
      roadmap={roadmap}
      onReset={handleReset}
      isResetting={isResetting}
      resetError={resetError}
      onNavigate={navigate}
      onStartSession={handleStartSession}
      onAbandonSession={handleAbandonSession}
    />
  );
}
