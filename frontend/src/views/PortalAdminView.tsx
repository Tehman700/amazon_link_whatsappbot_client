import { useCallback, useEffect, useState } from "react";
import { portalAdmin } from "../api";
import type {
  PerformanceData,
  PortalAdminAccount,
  PortalAdminData,
  PortalAdminLink,
} from "../types";

type SubTab = "accounts" | "linked" | "payouts" | "performance";

export default function PortalAdminView() {
  const [sub, setSub] = useState<SubTab>("accounts");
  const [data, setData] = useState<PortalAdminData | null>(null);
  const [error, setError] = useState("");
  const [tempPw, setTempPw] = useState<{ username: string; pw: string } | null>(null);

  const load = useCallback(() => {
    portalAdmin
      .data()
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  useEffect(load, [load]);

  if (error) return <div className="error-box">{error}</div>;
  if (!data) return <p className="muted">Loading portal data…</p>;

  return (
    <section>
      <div className="subtabs">
        {(
          [
            ["accounts", `Accounts (${data.accounts.length})`],
            ["linked", "Linked numbers"],
            ["payouts", "Payout details"],
            ["performance", "Overall performance"],
          ] as [SubTab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            className={sub === key ? "active" : ""}
            onClick={() => setSub(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {tempPw && (
        <div className="temp-pw">
          Temporary password for <strong>@{tempPw.username}</strong>:{" "}
          <code>{tempPw.pw}</code> — share it with the user; they can change it
          in their Profile. (Shown once — copy it now.)
          <button
            className="cell-btn"
            style={{ marginLeft: 10 }}
            onClick={() => navigator.clipboard.writeText(tempPw.pw)}
          >
            Copy
          </button>
        </div>
      )}

      {sub === "accounts" && (
        <AccountsTab
          data={data}
          refresh={load}
          onTempPw={(username, pw) => setTempPw({ username, pw })}
          onError={setError}
        />
      )}
      {sub === "linked" && <LinkedTab data={data} refresh={load} onError={setError} />}
      {sub === "payouts" && <PayoutsTab accounts={data.accounts} />}
      {sub === "performance" && <PerformanceTab />}
    </section>
  );
}

/* ---------------------------------------------------------- accounts tab */

function AccountsTab({
  data,
  refresh,
  onTempPw,
  onError,
}: {
  data: PortalAdminData;
  refresh: () => void;
  onTempPw: (username: string, pw: string) => void;
  onError: (m: string) => void;
}) {
  const [detail, setDetail] = useState<PortalAdminAccount | null>(null);

  const resetPw = async (a: PortalAdminAccount) => {
    if (!confirm(`Reset the portal password for @${a.username}?`)) return;
    try {
      const res = await portalAdmin.resetPassword(a.id);
      onTempPw(res.username, res.temp_password);
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const toggleDisabled = async (a: PortalAdminAccount) => {
    const verb = a.disabled ? "enable" : "disable";
    if (!confirm(`Really ${verb} @${a.username}? ${a.disabled ? "" : "They will not be able to log in until re-enabled."}`)) return;
    try {
      await portalAdmin.setDisabled(a.id, !a.disabled);
      refresh();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const del = async (a: PortalAdminAccount) => {
    if (
      !confirm(
        `Delete portal account @${a.username}? Their number becomes claimable again. Links/articles are kept.`,
      )
    )
      return;
    try {
      await portalAdmin.deleteAccount(a.id);
      refresh();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  if (detail) {
    return <AccountDetail account={detail} back={() => setDetail(null)} />;
  }

  return (
    <>
      <div className="card">
        <h2>Portal accounts</h2>
        <p className="muted" style={{ marginTop: -6, marginBottom: 10, fontSize: 13 }}>
          Click a user to see all their links and best performers.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th></th>
                <th>User</th>
                <th>Number</th>
                <th>Reply</th>
                <th>Store page</th>
                <th>Links</th>
                <th>Views</th>
                <th>Clicks</th>
                <th>Signed up</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.accounts.map((a) => (
                <tr key={a.id} style={a.disabled ? { opacity: 0.55 } : undefined}>
                  <td>
                    {a.avatar ? (
                      <img className="avatar-sm" src={a.avatar} alt="" />
                    ) : (
                      <span className="avatar-sm">{a.username[0]?.toUpperCase()}</span>
                    )}
                  </td>
                  <td
                    style={{ cursor: "pointer" }}
                    onClick={() => setDetail(a)}
                    title="View user details"
                  >
                    <strong style={{ textDecoration: "underline" }}>@{a.username}</strong>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {a.name}
                      {a.disabled ? " · DISABLED" : ""}
                    </div>
                  </td>
                  <td>{a.whatsapp_number}</td>
                  <td>
                    <span className={`badge ${a.link_preference === "hub" ? "" : "warn"}`}>
                      {a.link_preference}
                    </span>
                  </td>
                  <td>
                    {a.store_slug ? (
                      <a
                        href={`https://www.beastaffiliates.com/u/${a.store_slug}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        /u/{a.store_slug}
                      </a>
                    ) : (
                      <span className="muted">—</span>
                    )}
                    {a.store_slug && !a.store_enabled && (
                      <span className="muted" style={{ fontSize: 11 }}> (off)</span>
                    )}
                  </td>
                  <td>{a.links}</td>
                  <td>{a.views}</td>
                  <td>{a.clicks}</td>
                  <td className="muted" style={{ whiteSpace: "nowrap" }}>
                    {new Date(a.created_at).toLocaleDateString()}
                  </td>
                  <td className="row-actions">
                    <button className="cell-btn" onClick={() => resetPw(a)}>
                      Reset PW
                    </button>
                    <button className="cell-btn" onClick={() => toggleDisabled(a)}>
                      {a.disabled ? "Enable" : "Disable"}
                    </button>
                    <button className="danger" onClick={() => del(a)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.accounts.length === 0 && (
          <p className="muted">No portal accounts yet.</p>
        )}
      </div>

    </>
  );
}

/* ----------------------------------------------------- linked numbers tab */

function LinkedTab({
  data,
  refresh,
  onError,
}: {
  data: PortalAdminData;
  refresh: () => void;
  onError: (m: string) => void;
}) {
  const withLinked = data.accounts.filter((a) => a.linked_numbers.length > 0);

  const unlink = async (number: string, username: string) => {
    if (!confirm(`Unlink ${number} from @${username}? The bot will stop replying to it.`)) return;
    try {
      await portalAdmin.unlinkNumber(number);
      refresh();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  return (
    <div className="card">
      <h2>Linked WhatsApp numbers</h2>
      {withLinked.length === 0 ? (
        <p className="muted">No user has linked extra numbers yet.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Primary number</th>
                <th>Linked number</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {withLinked.flatMap((a) =>
                a.linked_numbers.map((n) => (
                  <tr key={n}>
                    <td>
                      <strong>@{a.username}</strong>{" "}
                      <span className="muted">({a.name})</span>
                    </td>
                    <td>{a.whatsapp_number}</td>
                    <td>{n}</td>
                    <td className="row-actions">
                      <button className="danger" onClick={() => unlink(n, a.username)}>
                        Unlink
                      </button>
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ----------------------------------------------------------- payouts tab */

function PayoutsTab({ accounts }: { accounts: PortalAdminAccount[] }) {
  const withPayout = accounts.filter((a) => a.bank || a.account_number);
  const missing = accounts.filter((a) => !a.bank && !a.account_number);

  return (
    <>
      <div className="card">
        <h2>Payout details ({withPayout.length})</h2>
        {withPayout.length === 0 ? (
          <p className="muted">No user has saved payout details yet.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Bank</th>
                  <th>Account title</th>
                  <th>Account number</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {withPayout.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <strong>@{a.username}</strong>{" "}
                      <span className="muted">({a.name})</span>
                    </td>
                    <td>{a.bank || <span className="muted">—</span>}</td>
                    <td>{a.account_title || <span className="muted">—</span>}</td>
                    <td>{a.account_number || <span className="muted">—</span>}</td>
                    <td className="row-actions">
                      <button
                        className="cell-btn"
                        onClick={() =>
                          navigator.clipboard.writeText(
                            `${a.bank} | ${a.account_title} | ${a.account_number}`,
                          )
                        }
                      >
                        Copy
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {missing.length > 0 && (
        <div className="card">
          <h2>Missing payout details ({missing.length})</h2>
          <p className="muted">
            {missing.map((a) => `@${a.username}`).join(", ")}
          </p>
        </div>
      )}
    </>
  );
}


/* ------------------------------------------------------ account detail */

function AccountDetail({
  account,
  back,
}: {
  account: PortalAdminAccount;
  back: () => void;
}) {
  const [links, setLinks] = useState<PortalAdminLink[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    portalAdmin
      .accountLinks(account.id)
      .then((d) => setLinks(d.links))
      .catch((e) => setError((e as Error).message));
  }, [account.id]);

  const best = (links ?? []).slice().sort((a, b) => b.clicks - a.clicks).slice(0, 5);

  return (
    <>
      <div className="card">
        <button className="cell-btn" onClick={back}>← Back to accounts</button>
        <div style={{ display: "flex", gap: 16, alignItems: "center", marginTop: 14 }}>
          {account.avatar ? (
            <img className="avatar-sm" style={{ width: 52, height: 52 }} src={account.avatar} alt="" />
          ) : (
            <span className="avatar-sm" style={{ width: 52, height: 52, fontSize: 20 }}>
              {account.username[0]?.toUpperCase()}
            </span>
          )}
          <div>
            <h2 style={{ margin: 0 }}>@{account.username}</h2>
            <p className="muted" style={{ margin: 0 }}>
              {account.name} · {account.whatsapp_number}
              {account.disabled ? " · DISABLED" : ""}
            </p>
          </div>
        </div>
        <div className="stats" style={{ marginTop: 16 }}>
          <div className="stat"><div className="stat-number">{account.links}</div>Links</div>
          <div className="stat"><div className="stat-number">{account.views}</div>Views</div>
          <div className="stat"><div className="stat-number">{account.clicks}</div>Clicks</div>
          <div className="stat">
            <div className="stat-number">
              {account.views ? Math.round((100 * account.clicks) / account.views) : 0}%
            </div>
            Conversion
          </div>
        </div>
        <p className="muted" style={{ fontSize: 13, marginTop: 12 }}>
          Reply: <strong>{account.link_preference}</strong>
          {account.store_name ? <> · Store name: <strong>{account.store_name}</strong></> : null}
          {account.store_slug ? (
            <>
              {" · Store page: "}
              <a href={`https://www.beastaffiliates.com/u/${account.store_slug}`} target="_blank" rel="noreferrer">
                /u/{account.store_slug}
              </a>
              {account.store_enabled ? "" : " (off)"}
            </>
          ) : null}
          {account.linked_numbers.length > 0 ? (
            <> · Linked numbers: {account.linked_numbers.join(", ")}</>
          ) : null}
        </p>
      </div>

      {error && <div className="error-box">{error}</div>}
      {!links && !error && <p className="muted">Loading links…</p>}

      {links && (
        <>
          <div className="card">
            <h2>Best performing links</h2>
            {best.filter((l) => l.clicks > 0).length === 0 ? (
              <p className="muted">No clicks recorded yet.</p>
            ) : (
              <ol style={{ marginLeft: 20 }}>
                {best.map((l) => (
                  <li key={l.id} style={{ margin: "6px 0" }}>
                    <a href={l.article_url} target="_blank" rel="noreferrer">
                      {l.title.slice(0, 70)}
                    </a>{" "}
                    <span className="muted">
                      — {l.clicks} clicks · {l.views} views · {l.marketplace}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </div>

          <div className="card">
            <h2>All links ({links.length})</h2>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Market</th>
                    <th>Views</th>
                    <th>Clicks</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {links.map((l) => (
                    <tr key={l.id}>
                      <td style={{ maxWidth: 380 }}>
                        <a href={l.article_url} target="_blank" rel="noreferrer">
                          {l.title.slice(0, 80)}
                        </a>
                      </td>
                      <td><span className="badge">{l.marketplace}</span></td>
                      <td>{l.views}</td>
                      <td>{l.clicks}</td>
                      <td className="muted" style={{ whiteSpace: "nowrap" }}>
                        {new Date(l.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {links.length === 0 && <p className="muted">No links yet.</p>}
          </div>
        </>
      )}
    </>
  );
}

/* -------------------------------------------------- overall performance */

const RANGES: [string, number][] = [
  ["Last 7 days", 7],
  ["Last 30 days", 30],
  ["Last 90 days", 90],
  ["All time", 0],
];
type Metric = "clicks" | "views" | "links";

function PerformanceTab() {
  const [days, setDays] = useState(30);
  const [metric, setMetric] = useState<Metric>("clicks");
  const [data, setData] = useState<PerformanceData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    portalAdmin
      .performance(days)
      .then(setData)
      .catch((e) => setError((e as Error).message));
  }, [days]);

  if (error) return <div className="error-box">{error}</div>;
  if (!data) return <p className="muted">Loading performance…</p>;

  const users = data.per_user
    .slice()
    .sort((a, b) => b[metric] - a[metric])
    .slice(0, 10);
  const maxVal = Math.max(1, ...users.flatMap((u) => [u.views, u.clicks]));

  return (
    <>
      <div className="card">
        <div className="form-row" style={{ marginBottom: 6 }}>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {RANGES.map(([label, v]) => (
              <option key={v} value={v}>{label}</option>
            ))}
          </select>
          <select value={metric} onChange={(e) => setMetric(e.target.value as Metric)}>
            <option value="clicks">Sort by clicks</option>
            <option value="views">Sort by views</option>
            <option value="links">Sort by links created</option>
          </select>
          <span className="muted" style={{ fontSize: 13 }}>
            <span style={{ color: "#c0392b" }}>■</span> Clicks&nbsp;&nbsp;
            <span style={{ color: "#b5b8bd" }}>■</span> Views
          </span>
        </div>
      </div>

      <div className="card">
        <h2>Top users</h2>
        {users.length === 0 ? (
          <p className="muted">No portal users yet.</p>
        ) : (
          <svg
            viewBox={`0 0 640 ${users.length * 52 + 10}`}
            style={{ width: "100%", height: "auto" }}
          >
            {users.map((u, i) => {
              const y = i * 52;
              const wViews = (u.views / maxVal) * 420;
              const wClicks = (u.clicks / maxVal) * 420;
              return (
                <g key={u.username} transform={`translate(0,${y})`}>
                  <text x="0" y="20" fontSize="13" fontWeight="600" fill="#111">
                    @{u.username.slice(0, 16)}
                  </text>
                  <text x="0" y="36" fontSize="10" fill="#8a8a8f">
                    {u.links} link{u.links === 1 ? "" : "s"}
                  </text>
                  <rect x="150" y="8" width={Math.max(2, wClicks)} height="14" rx="4" fill="#c0392b" />
                  <text x={155 + Math.max(2, wClicks)} y="19" fontSize="11" fill="#c0392b">
                    {u.clicks}
                  </text>
                  <rect x="150" y="26" width={Math.max(2, wViews)} height="14" rx="4" fill="#b5b8bd" />
                  <text x={155 + Math.max(2, wViews)} y="37" fontSize="11" fill="#8a8a8f">
                    {u.views}
                  </text>
                </g>
              );
            })}
          </svg>
        )}
      </div>

      <div className="card">
        <h2>Daily activity (all users)</h2>
        <TrendChart series={data.series} />
      </div>

      <div className="card">
        <h2>Leaderboard</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>User</th>
                <th>Links</th>
                <th>Views</th>
                <th>Clicks</th>
                <th>Conversion</th>
              </tr>
            </thead>
            <tbody>
              {data.per_user
                .slice()
                .sort((a, b) => b[metric] - a[metric])
                .map((u, i) => (
                  <tr key={u.username}>
                    <td>{i + 1}</td>
                    <td>
                      <strong>@{u.username}</strong>{" "}
                      <span className="muted">({u.name})</span>
                    </td>
                    <td>{u.links}</td>
                    <td>{u.views}</td>
                    <td>{u.clicks}</td>
                    <td>{u.views ? Math.round((100 * u.clicks) / u.views) : 0}%</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function TrendChart({ series }: { series: { date: string; views: number; clicks: number }[] }) {
  const width = 640;
  const height = 180;
  const pad = 28;
  const max = Math.max(1, ...series.flatMap((d) => [d.views, d.clicks]));
  const x = (i: number) => pad + (i * (width - 2 * pad)) / Math.max(1, series.length - 1);
  const y = (v: number) => height - pad - (v / max) * (height - 2 * pad);
  const path = (key: "views" | "clicks") =>
    series.map((d, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(d[key])}`).join(" ");
  const labelEvery = Math.max(1, Math.floor(series.length / 8));

  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto" }}>
      {[0.5, 1].map((f) => (
        <line key={f} x1={pad} x2={width - pad} y1={y(max * f)} y2={y(max * f)} stroke="#eee" />
      ))}
      <path d={path("views")} fill="none" stroke="#b5b8bd" strokeWidth="2" />
      <path d={path("clicks")} fill="none" stroke="#c0392b" strokeWidth="2" />
      {series.map((d, i) =>
        i % labelEvery === 0 ? (
          <text key={d.date} x={x(i)} y={height - 8} textAnchor="middle" fontSize="9" fill="#8a8a8f">
            {d.date.slice(5)}
          </text>
        ) : null,
      )}
    </svg>
  );
}
