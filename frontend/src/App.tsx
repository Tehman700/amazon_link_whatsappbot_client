import { useCallback, useEffect, useState } from "react";
import { api, hasToken, setToken } from "./api";
import type { Marketplace, User } from "./types";
import OverviewView from "./views/OverviewView";
import UsersView from "./views/UsersView";
import MarketplacesView from "./views/MarketplacesView";
import TestView from "./views/TestView";
import LoginView from "./views/LoginView";
import "./App.css";

type Tab = "overview" | "users" | "marketplaces" | "test";

export default function App() {
  const [authed, setAuthed] = useState(hasToken());
  const [tab, setTab] = useState<Tab>("overview");
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
            className={tab === "overview" ? "active" : ""}
            onClick={() => setTab("overview")}
          >
            Overview
          </button>
          <button className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>
            Users
          </button>
          <button
            className={tab === "marketplaces" ? "active" : ""}
            onClick={() => setTab("marketplaces")}
          >
            Marketplaces
          </button>
          <button className={tab === "test" ? "active" : ""} onClick={() => setTab("test")}>
            Test message
          </button>
          <button onClick={logout}>Log out</button>
        </nav>
      </header>

      {error && (
        <div className="card error-box">
          {error} <button onClick={refresh}>Retry</button>
        </div>
      )}

      {loaded && !error && (
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
