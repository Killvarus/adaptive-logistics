import { Database, Route, LayoutDashboard } from "lucide-react";
import { useApp } from "./state/AppProvider";
import { DataPage } from "./features/DataPage";
import { Overview } from "./features/Overview";
import { PlanPage } from "./features/PlanPage";
import { ScenarioPanel } from "./features/ScenarioPanel";
import { downloadJson } from "./shared/format";

const NAV = [
  { id: "overview" as const, label: "Обзор", icon: LayoutDashboard },
  { id: "plan" as const, label: "План перевозок", icon: Route },
  { id: "data" as const, label: "Данные и модель", icon: Database },
];

export function App() {
  const { state, setView, reset } = useApp();
  const dataset = state.dataset?.dataset;
  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <Logo />
          <div>
            <h1>Адаптивная логистика</h1>
            <p>Сценарии затрат и планы перевозок</p>
          </div>
        </div>
        <div className="header-meta">
          <span>{dataset?.metadata.dataset_id ?? "…"}</span>
          <span className="badge demo">Синтетический demo</span>
        </div>
        <nav className="top-nav" aria-label="Разделы">
          {NAV.map((item) => (
            <button key={item.id} className={state.view === item.id ? "active" : ""} onClick={() => setView(item.id)}>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="header-actions">
          <button className="btn" onClick={() => state.draft && downloadJson("scenario.json", state.draft)} disabled={!state.draft}>
            Сохранить сценарий
          </button>
          <button className="btn-ghost" onClick={reset}>Сбросить</button>
        </div>
      </header>
      <nav className="nav" aria-label="Разделы">
        {NAV.map((item) => {
          const Icon = item.icon;
          return (
            <button key={item.id} className={state.view === item.id ? "active" : ""} onClick={() => setView(item.id)}>
              <Icon size={16} style={{ verticalAlign: "text-bottom", marginRight: 8 }} />
              {item.label}
            </button>
          );
        })}
      </nav>
      <main className="main">
        {state.datasetStatus === "loading" && <p>Загружаем демонстрационный набор.</p>}
        {state.datasetStatus === "error" && (
          <div className="banner error">
            <span>{state.error ?? "Не удалось связаться с расчётным сервисом."}</span>
            <button className="btn" onClick={() => window.location.reload()}>Повторить</button>
          </div>
        )}
        {state.view === "overview" && <Overview />}
        {state.view === "plan" && <PlanPage />}
        {state.view === "data" && <DataPage />}
        <p className="footer-note">Результаты — расчёт модели на выбранных данных. Не подтверждённый эффект для реальной компании.</p>
      </main>
      <ScenarioPanel />
    </div>
  );
}

function Logo() {
  return (
    <svg width="36" height="36" viewBox="0 0 36 36" aria-hidden="true">
      <rect width="36" height="36" rx="8" fill="#e6f2ef" />
      <circle cx="8" cy="18" r="3" fill="#176b62" />
      <circle cx="18" cy="10" r="3" fill="#176b62" />
      <circle cx="28" cy="22" r="3" fill="#176b62" />
      <path d="M8 18 L18 10 L28 22" fill="none" stroke="#176b62" strokeWidth="1.6" />
    </svg>
  );
}
