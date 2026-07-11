import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { Marketplace, User } from "./types";
import UsersView from "./views/UsersView";
import MarketplacesView from "./views/MarketplacesView";
import TestView from "./views/TestView";
import "./App.css";

type Tab = "users" | "marketplaces" | "test";

export default function App() {
  const [tab, setTab] = useState<Tab>("users");
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
    refresh();
  }, [refresh]);

  return (
    <div className="layout">
      <header>
        <h1>Amazon Affiliate Bot — Admin</h1>
        <nav>
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
        </nav>
      </header>

      {error && (
        <div className="card error-box">
          {error} <button onClick={refresh}>Retry</button>
        </div>
      )}

      {loaded && !error && (
        <>
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
