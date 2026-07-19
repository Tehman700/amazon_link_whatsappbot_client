import { useCallback, useEffect, useState } from "react";
import { api, hasToken, setToken } from "./api";
import type { Marketplace, User } from "./types";
import OverviewView from "./views/OverviewView";
import UsersView from "./views/UsersView";
import MarketplacesView from "./views/MarketplacesView";
import TestView from "./views/TestView";
import LoginView from "./views/LoginView";
import PortalAdminView from "./views/PortalAdminView";
import "./App.css";

type Tab = "overview" | "users" | "marketplaces" | "test";

export default function App() {
  const [authed, setAuthed] = useState(hasToken());
  const [tab, setTab] = useState<Tab>("overview");
  // Real URL route: "/portal-admin" hosts the portal administration page.
  const [route, setRoute] = useState(window.location.pathname);

  useEffect(() => {
    const onPop = () => setRoute(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const go = (path: string) => {
    window.history.pushState({}, "", path);
    setRoute(path);
  };
  const onPortalAdmin = route === "/portal-admin";
  const [users, setUsers] = useState<User[]>([]);
  const [marketplaces, setMarketplaces] = useState<Marketplace[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [u, m] = await Promise.all([api.listUsers(), api.listMarketplaces()]);
      setUsers(u);
      setMarketplaces(m);
      setError(null);
    } catch (e) {
      setError(`Cannot reach the API: ${(e as Error).message}`);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    const onExpired = () => setAuthed(false);
    window.addEventListener("auth-expired", onExpired);
    return () => window.removeEventListener("auth-expired", onExpired);
  }, []);

  useEffect(() => {
    if (authed) refresh();
  }, [authed, refresh]);

  if (!authed) {
    return <LoginView onLogin={() => setAuthed(true)} />;
  }

  const logout = () => {
    setToken(null);
    setAuthed(false);
    setLoaded(false);
  };

  return (
    <div className="layout">
      <header>
        <h1>Amazon Affiliate Bot — Admin</h1>
        <nav>
          <button
            className={!onPortalAdmin && tab === "overview" ? "active" : ""}
            onClick={() => { go("/"); setTab("overview"); }}
          >
            Overview
          </button>
          <button
            className={!onPortalAdmin && tab === "users" ? "active" : ""}
            onClick={() => { go("/"); setTab("users"); }}
          >
            Users
          </button>
          <button
            className={!onPortalAdmin && tab === "marketplaces" ? "active" : ""}
            onClick={() => { go("/"); setTab("marketplaces"); }}
          >
            Marketplaces
          </button>
          <button
            className={!onPortalAdmin && tab === "test" ? "active" : ""}
            onClick={() => { go("/"); setTab("test"); }}
          >
            Test message
          </button>
          <button
            className={`danger-tab ${onPortalAdmin ? "active" : ""}`}
            onClick={() => go("/portal-admin")}
          >
            Portal administration
          </button>
          <button onClick={logout}>Log out</button>
        </nav>
      </header>

      {error && (
        <div className="card error-box">
          {error} <button onClick={refresh}>Retry</button>
        </div>
      )}

      {onPortalAdmin && <PortalAdminView />}

      {!onPortalAdmin && loaded && !error && (
        <>
          {tab === "overview" && (
            <OverviewView
              users={users}
              marketplaces={marketplaces}
              refresh={refresh}
              onError={setError}
            />
          )}
          {tab === "users" && (
            <UsersView users={users} marketplaces={marketplaces} refresh={refresh} onError={setError} />
          )}
          {tab === "marketplaces" && (
            <MarketplacesView marketplaces={marketplaces} refresh={refresh} onError={setError} />
          )}
          {tab === "test" && <TestView users={users} />}
        </>
      )}
    </div>
  );
}
