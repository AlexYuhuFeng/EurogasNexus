import { useAppController } from "@/app/hooks/useAppController";
import { useUnsavedChangesGuard } from "@/app/hooks/useUnsavedChangesGuard";
import { AppShell } from "@/app/shell/AppShell";
import "./styles/app.css";

export default function App() {
  const controller = useAppController();
  // A contract draft lives in the controller across pages; only an unload can lose it.
  useUnsavedChangesGuard(controller.contractEditor.draftDirty);
  return <AppShell controller={controller} />;
}

