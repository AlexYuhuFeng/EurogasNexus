import { useAppController } from "@/app/hooks/useAppController";
import { AppShell } from "@/app/shell/AppShell";
import "./styles/app.css";

export default function App() {
  const controller = useAppController();
  return <AppShell controller={controller} />;
}

