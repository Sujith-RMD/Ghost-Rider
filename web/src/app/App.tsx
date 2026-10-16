import { lazy, Suspense, useEffect } from "react";
import { NavLink, Route, Routes, useLocation, Link, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Route as RouteIcon,
  Activity,
  Image,
  MapPin,
  FileText,
  Radio,
  Upload,
  ArrowUpRight,
} from "lucide-react";
import { dataSource, PreviewBanner } from "virtual:roadsight-data";
import {
  Card,
  EmptyState,
  ErrorPanel,
  SampleCard,
} from "../components/primitives";
const RoutePage = lazy(() => import("../features/route-map/RoutePage"));
const SamplePage = lazy(() => import("../features/sample/SamplePage"));
const ActualSamplePage = lazy(() => import("../features/sample/ActualSamplePage"));
const RecentSamplesPage = lazy(() => import("../features/sample/RecentSamplesPage"));
const AssessPage = lazy(() => import("../features/assess/AssessPage"));
const LivePage = lazy(() => import("../features/live/LivePage"));
const SessionPage = lazy(() => import("../features/session/SessionPage"));
const ReportPage = lazy(() => import("../features/report/ReportPage"));
const SystemPage = lazy(() => import("../features/system/SystemPage"));
const ActualSystemPage = lazy(() => import("../features/system/ActualSystemPage"));
const navigation = [
  { to: "/", label: "Route map", Icon: MapPin },
  { to: "/assess", label: "Assess", Icon: Upload },
  { to: "/live", label: "Live", Icon: Radio },
  { to: "/samples", label: "Samples", Icon: Image },
  { to: "/reports", label: "Reports", Icon: FileText },
  { to: "/system", label: "System", Icon: Activity },
];
export default function App() {
  const location = useLocation();
  const query = useQuery({
    queryKey: ["workspace", dataSource.mock],
    queryFn: dataSource.load,
    retry: false,
    refetchInterval: dataSource.mock ? false : 30000,
    refetchIntervalInBackground: false,
  });
  useEffect(() => {
    const title =
      navigation.find((n) =>
        n.to === "/"
          ? location.pathname === "/"
          : location.pathname.startsWith(n.to),
      )?.label ?? "Session";
    document.title = `RoadSight | ${title}`;
    window.scrollTo(0, 0);
  }, [location.pathname]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        const close = document.querySelector<HTMLButtonElement>(
          ".selected-bin .close-button",
        );
        close?.click();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  return (
    <div className={`app-shell ${dataSource.mock ? "is-preview" : ""} ${location.pathname === "/" ? "route-view" : "content-view"}`}>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <PreviewBanner />
      <header className="app-header">
        <Link to="/" className="wordmark" aria-label="RoadSight home">
          <RouteIcon size={26} strokeWidth={1.5} />
          <span>
            RoadSight<span className="wordmark-ai"> AI</span>
          </span>
        </Link>
        <nav aria-label="Main navigation">
          {navigation.filter(({ to }) => dataSource.mock || to !== "/").map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              aria-label={label}
              end={to === "/"}
              className={({ isActive }) =>
                `nav-pill ${isActive ? "active" : ""}`
              }
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <Link to="/system" className="api-status">
          <span className="status-ring" />
          {dataSource.mock ? "Preview mode" : "Assessment service"}
        </Link>
      </header>
      <main id="main" tabIndex={-1}>
        {!dataSource.mock && location.pathname === "/" ? (
          <Navigate to="/assess" replace />
        ) : query.isPending ? (
          <div
            className="loading-layout"
            aria-label="Loading assessment workspace"
          >
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        ) : query.isError && !dataSource.mock && (location.pathname === "/assess" || location.pathname === "/samples" || location.pathname.startsWith("/samples/") || location.pathname === "/system") ? (
          <Suspense fallback={<div className="loading-layout"><div className="skeleton" /></div>}>
            {location.pathname === "/assess" ? <AssessPage mock={false} /> : location.pathname === "/samples" ? <RecentSamplesPage /> : location.pathname === "/system" ? <ActualSystemPage /> : <ActualSamplePage id={location.pathname.slice("/samples/".length)} />}
          </Suspense>
        ) : query.isError ? (
          <div className="content-page">
            <h1>This screen is not connected yet</h1>
            <ErrorPanel
              family="integration"
              title="Production data unavailable"
            >
              <p>Route, live and report data are still being connected.</p>
            </ErrorPanel>
            <p>
              Image assessment is available now. Other screens will appear when their real data is ready.
            </p>
            <Link className="button primary" to="/assess">Open assessment</Link>
            <Link className="button secondary" to="/system">
              System readiness
            </Link>
            {location.pathname === "/system" && (
              <SystemPage health={[]} contractVersion={null} />
            )}
          </div>
        ) : (
          <Suspense
            fallback={
              <div className="loading-layout">
                <div className="skeleton" />
                <div className="skeleton" />
              </div>
            }
          >
            <Routes>
              <Route
                path="/"
                element={<RoutePage session={query.data.session} />}
              />
              <Route
                path="/assess"
                element={
                  <AssessPage
                    session={query.data.session}
                    mock={dataSource.mock}
                  />
                }
              />
              <Route
                path="/live"
                element={
                  <LivePage
                    session={query.data.session}
                    monitor={query.data.monitor}
                  />
                }
              />
              <Route
                path="/samples"
                element={
                  <div className="content-page">
                    <div className="page-heading">
                      <div>
                        <h1>Sample evidence</h1>
                        <p>
                          Original imagery, measurement support and review
                          state.
                        </p>
                      </div>
                    </div>
                    <div className="sample-list-grid">
                      {query.data.session.samples.map((s) => (
                        <SampleCard key={s.id} sample={s} />
                      ))}
                    </div>
                  </div>
                }
              />
              <Route
                path="/samples/:id"
                element={<SamplePage session={query.data.session} />}
              />
              <Route
                path="/sessions/:id"
                element={<SessionPage session={query.data.session} />}
              />
              <Route
                path="/reports"
                element={
                  <div className="content-page">
                    <div className="page-heading">
                      <div>
                        <h1>Inspection reports</h1>
                        <p>
                          Structured facts first. Supporting explanation second.
                        </p>
                      </div>
                    </div>
                    <Card
                      title="Session inspection report"
                      href={`/reports/${query.data.report.id}`}
                    >
                      <p>{query.data.session.name}</p>
                      <p className="muted">
                        Template fixture / limitations included
                      </p>
                      <Link
                        className="button secondary"
                        to={`/reports/${query.data.report.id}`}
                      >
                        Open report
                        <ArrowUpRight size={16} />
                      </Link>
                    </Card>
                  </div>
                }
              />
              <Route
                path="/reports/:id"
                element={<ReportPage report={query.data.report} />}
              />
              <Route
                path="/system"
                element={
                  <SystemPage
                    health={query.data.health}
                    contractVersion={dataSource.contractVersion}
                  />
                }
              />
              <Route
                path="*"
                element={
                  <EmptyState title="Page not found">
                    Return to <Link to="/">Route map</Link>.
                  </EmptyState>
                }
              />
            </Routes>
          </Suspense>
        )}
      </main>
    </div>
  );
}
