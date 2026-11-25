import { useEffect, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { useApp } from "./context/AppContext";
import { rpc } from "./lib/api";
import NavRail from "./components/NavRail";
import StatusBar from "./components/StatusBar";
import ToastContainer from "./components/ToastContainer";
import ModelDownloadScreen from "./components/ModelDownloadScreen";
import GalleryView from "./views/GalleryView";
import PeopleView from "./views/PeopleView";
import DuplicatesView from "./views/DuplicatesView";
import BurstsView from "./views/BurstsView";
import TimelineView from "./views/TimelineView";
import SettingsView from "./views/SettingsView";
import LightboxModal from "./modals/LightboxModal";

function WorkspaceShell() {
  const { activeView, connected, backendError, initBackend, lightboxPhoto, setLightboxPhoto } =
    useApp();

  const renderView = () => {
    switch (activeView) {
      case "people":
        return <PeopleView />;
      case "duplicates":
        return <DuplicatesView />;
      case "bursts":
        return <BurstsView />;
      case "timeline":
        return <TimelineView />;
      case "settings":
        return <SettingsView />;
      case "photos":
      default:
        return <GalleryView />;
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-app text-primary">
      <NavRail />

      <div className="flex-1 min-w-0 flex flex-col h-screen overflow-hidden">
        {!connected && backendError && (
          <div className="px-4 py-2 bg-danger-bg border-b border-danger/50 text-xs text-primary flex items-center justify-between gap-3 shrink-0">
            <span className="inline-flex items-center gap-2 min-w-0">
              <AlertTriangle className="w-3.5 h-3.5 text-danger shrink-0" strokeWidth={1.7} />
              <span className="truncate">{backendError}</span>
            </span>
            <button
              type="button"
              onClick={initBackend}
              className="btn-danger h-6 px-2 text-xs shrink-0"
            >
              <RefreshCw className="w-3 h-3" strokeWidth={1.6} />
              <span>Retry</span>
            </button>
          </div>
        )}

        <main className="flex-1 min-h-0 flex flex-col overflow-hidden">{renderView()}</main>

        <StatusBar />
      </div>

      {lightboxPhoto && (
        <LightboxModal
          key={lightboxPhoto.id}
          photo={lightboxPhoto}
          onClose={() => setLightboxPhoto(null)}
        />
      )}

      <ToastContainer />
    </div>
  );
}

export default function App() {
  const { connected } = useApp();
  const [checkingModels, setCheckingModels] = useState(true);
  const [modelsReady, setModelsReady] = useState(false);

  useEffect(() => {
    if (!connected) return;

    let mounted = true;
    rpc<{ ready: boolean }>("models.status")
      .then(res => {
        if (!mounted) return;
        if (res && res.ready) {
          setModelsReady(true);
        } else {
          setModelsReady(false);
        }
      })
      .catch(() => {
        if (!mounted) return;
        // If models.status fails or is not supported, fall back to letting the app load
        setModelsReady(true);
      })
      .finally(() => {
        if (mounted) setCheckingModels(false);
      });

    return () => {
      mounted = false;
    };
  }, [connected]);

  // If connected and models are not ready, show model download screen with real-time progress
  if (connected && !checkingModels && !modelsReady) {
    return <ModelDownloadScreen onComplete={() => setModelsReady(true)} />;
  }

  return <WorkspaceShell />;
}
