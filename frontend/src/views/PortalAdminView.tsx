import { Fragment, useCallback, useEffect, useState } from "react";
import { portalAdmin } from "../api";
import type {
  EarningsDetailData,
  EarningsEntryOut,
  EarningsOverview,
  EarningsUserRow,
  LoginRow,
  LoginsData,
  PerformanceData,
  PortalAdminAccount,
  PortalAdminData,
  PortalAdminLink,
  ReferralOut,
} from "../types";

type SubTab = "accounts" | "logins" | "linked" | "payouts" | "performance";

// Where users sign in. One portal for everyone, whatever article domain their
// links land on, so this is a constant rather than per-user. Prod builds
// deliberately avoid Vite env vars (a stray Vercel env var once broke prod).
const PORTAL_LOGIN_URL = "https://www.beastaffiliates.com/dashboard";

/** The three lines the admin pastes to a user, exactly as the client asked. */
function loginDetailsText(username: string, pw: string): string {
  return [
    `Dashboard Login: ${PORTAL_LOGIN_URL}`,
    `Username: ${username}`,
    `Password: ${pw}`,
  ].join("\n");
}

export default function PortalAdminView() {
  const [sub, setSub] = useState<SubTab>("accounts");
  const [data, setData] = useState<PortalAdminData | null>(null);
  const [error, setError] = useState("");
  // `kind` only changes the wording: a reset password is temporary and the user
  // is expected to change it, one the admin just chose is not.
  const [tempPw, setTempPw] = useState<
    { username: string; pw: string; kind: "created" | "reset" } | null
  >(null);
  const [copied, setCopied] = useState("");

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
            ["logins", "Logins"],
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
          {tempPw.kind === "reset" ? "Temporary password" : "New account"} for{" "}
          <strong>@{tempPw.username}</strong>: <code>{tempPw.pw}</code> — share
          it with the user; they can change it in their Profile. (Shown once —
          copy it now.)
          <button
            className="cell-btn"
            style={{ marginLeft: 10 }}
            onClick={() => {
              navigator.clipboard.writeText(
                loginDetailsText(tempPw.username, tempPw.pw),
              );
              setCopied("all");
            }}
          >
            {copied === "all" ? "Copied ✓" : "Copy all details"}
          </button>
          <button
            className="cell-btn"
            style={{ marginLeft: 6 }}
            onClick={() => {
              navigator.clipboard.writeText(tempPw.pw);
              setCopied("pw");
            }}
          >
            {copied === "pw" ? "Copied ✓" : "Password only"}
          </button>
        </div>
      )}

      {sub === "accounts" && (
        <AccountsTab
          data={data}
          refresh={load}
          onTempPw={(username, pw, kind) => {
            setTempPw({ username, pw, kind });
            setCopied("");
          }}
          onError={setError}
        />
      )}
      {sub === "logins" && <LoginsTab />}
      {sub === "linked" && <LinkedTab data={data} refresh={load} onError={setError} />}
      {sub === "payouts" && <PayoutsTab accounts={data.accounts} />}
      {sub === "performance" && <PerformanceTab />}
    </section>
  );
}

/* Entry kinds the admin enters as a direct amount, i.e. everything except a
   commission 'earning', which is gross x rate. */
type OtherKind = "bonus" | "adjustment" | "return";

/* ------------------------------------------------------------ logins tab */

/* Every user who HAS a portal account, with the credentials to hand them.
   Only accounts appear here — people who were never given one live in the
   Accounts tab, where they can be created. Passwords are masked until asked
   for, so the whole list is not sitting in the open during a screen share. */
function LoginsTab() {
  const [data, setData] = useState<LoginsData | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [shown, setShown] = useState<Set<number>>(new Set());
  const [copied, setCopied] = useState<number | null>(null);

  useEffect(() => {
    portalAdmin
      .logins()
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  if (error) return <div className="error-box">{error}</div>;
  if (!data) return <p className="muted">Loading logins…</p>;

  const toggle = (id: number) =>
    setShown((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const copyRow = (r: LoginRow) => {
    navigator.clipboard.writeText(loginDetailsText(r.username, r.password));
    setCopied(r.account_id);
    window.setTimeout(() => setCopied(null), 1500);
  };

  const needle = q.trim().toLowerCase();
  const rows = needle
    ? data.accounts.filter(
        (r) =>
          r.username.toLowerCase().includes(needle) ||
          r.name.toLowerCase().includes(needle) ||
          r.whatsapp_number.includes(needle),
      )
    : data.accounts;

  const known = data.accounts.filter((r) => r.password).length;

  return (
    <div className="card" style={{ marginTop: 18 }}>
      <h2>Logins ({data.accounts.length})</h2>
      <p className="muted" style={{ marginTop: -6, marginBottom: 12, fontSize: 13 }}>
        Everyone who has a portal account, and what to send them. Copy gives the
        dashboard link, username and password ready to paste.
      </p>

      {!data.storage_enabled && (
        <div className="notice" style={{ marginBottom: 12 }}>
          Password storage is off (CREDENTIAL_KEY is not set), so passwords
          issued from now on cannot be shown here. Use Reset PW in the Accounts
          tab to issue one you can copy.
        </div>
      )}

      {data.accounts.length > 10 && (
        <input
          style={{ maxWidth: 280, marginBottom: 12 }}
          placeholder="Search name, username or number…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      )}

      {data.accounts.length === 0 ? (
        <p className="muted">
          No portal accounts yet — create one from the Accounts tab.
        </p>
      ) : (
        <div className="table-scroll">
          <table className="logins-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Username</th>
                <th>Password</th>
                <th style={{ width: 150 }}></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.account_id}>
                  <td>
                    {r.name || <span className="muted">—</span>}
                    {r.disabled && (
                      <span className="muted" style={{ fontSize: 12 }}>
                        {" "}
                        (disabled)
                      </span>
                    )}
                    <div className="muted" style={{ fontSize: 12 }}>
                      {r.whatsapp_number}
                    </div>
                  </td>
                  <td>
                    <code className="cred">{r.username}</code>
                  </td>
                  <td>
                    {r.password ? (
                      <code className="cred">
                        {shown.has(r.account_id) ? r.password : "••••••••••"}
                      </code>
                    ) : (
                      <span className="muted" style={{ fontSize: 13 }}>
                        {r.has_stored
                          ? "Stored under a previous key — reset it to issue a new one"
                          : "Changed by user — reset it to issue a new one"}
                      </span>
                    )}
                  </td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {r.password && (
                      <>
                        <button
                          className="cell-btn"
                          onClick={() => toggle(r.account_id)}
                        >
                          {shown.has(r.account_id) ? "Hide" : "Show"}
                        </button>
                        <button
                          className="cell-btn"
                          style={{ marginLeft: 6 }}
                          onClick={() => copyRow(r)}
                        >
                          {copied === r.account_id ? "Copied ✓" : "Copy"}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="muted">
                    No match for “{q}”.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {data.storage_enabled && known < data.accounts.length && (
        <p className="muted" style={{ marginTop: 10, fontSize: 13 }}>
          {data.accounts.length - known} of {data.accounts.length} have set their
          own password since, so it can no longer be shown here — that is
          working as intended, not a fault.
        </p>
      )}
    </div>
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
  onTempPw: (username: string, pw: string, kind: "created" | "reset") => void;
  onError: (m: string) => void;
}) {
  const [detail, setDetail] = useState<PortalAdminAccount | null>(null);
  // Earnings moved here from the removed Earnings tab: global settings (top),
  // a Balance column, and the full per-user management inside the detail view.
  const [earnings, setEarnings] = useState<EarningsOverview | null>(null);
  const [defRate, setDefRate] = useState("");
  const [minPayout, setMinPayout] = useState("");

  const loadEarnings = useCallback(() => {
    portalAdmin
      .earnings()
      .then((d) => {
        setEarnings(d);
        setDefRate(String(d.settings.default_rate));
        setMinPayout(String(d.settings.min_payout));
      })
      .catch((e) => onError((e as Error).message));
  }, [onError]);
  useEffect(loadEarnings, [loadEarnings]);

  const balanceById = new Map((earnings?.users ?? []).map((u) => [u.account_id, u.balance]));

  const saveSettings = async () => {
    try {
      await portalAdmin.earningsSettings({
        default_rate: Number(defRate),
        min_payout: Number(minPayout),
      });
      loadEarnings();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const resetPw = async (a: PortalAdminAccount) => {
    if (!confirm(`Reset the portal password for @${a.username}?`)) return;
    try {
      const res = await portalAdmin.resetPassword(a.id);
      onTempPw(res.username, res.temp_password, "reset");
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

  const editOrders = async (a: PortalAdminAccount) => {
    const raw = prompt(`Number of orders (purchases) for @${a.username}:`, String(a.orders));
    if (raw === null) return;
    const n = Number(raw);
    if (isNaN(n) || n < 0) { onError("Orders must be a number \u2265 0"); return; }
    try {
      await portalAdmin.setOrders(a.id, n);
      refresh();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const editShippedOrders = async (a: PortalAdminAccount) => {
    const raw = prompt(`Number of shipped orders for @${a.username}:`, String(a.shipped_orders));
    if (raw === null) return;
    const n = Number(raw);
    if (isNaN(n) || n < 0) { onError("Shipped orders must be a number \u2265 0"); return; }
    try {
      await portalAdmin.setShippedOrders(a.id, n);
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
    return (
      <AccountDetail
        account={detail}
        accounts={earnings?.users ?? []}
        back={() => { setDetail(null); loadEarnings(); }}
      />
    );
  }

  return (
    <>
      <div className="card">
        <h2>Earnings settings</h2>
        <p className="muted" style={{ marginTop: -6, marginBottom: 10, fontSize: 13 }}>
          Apply to everyone. A user with no custom rate earns at the default.
        </p>
        <div className="form-row">
          <label className="muted" style={{ fontSize: 13 }}>
            Default commission rate (%)
            <input value={defRate} onChange={(e) => setDefRate(e.target.value)}
              style={{ display: "block", marginTop: 4 }} />
          </label>
          <label className="muted" style={{ fontSize: 13 }}>
            Minimum payout (PKR)
            <input value={minPayout} onChange={(e) => setMinPayout(e.target.value)}
              style={{ display: "block", marginTop: 4 }} />
          </label>
          <button className="primary" onClick={saveSettings} style={{ alignSelf: "flex-end" }}>
            Save settings
          </button>
        </div>
      </div>

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
                <th>Orders</th>
                <th>Shipped</th>
                <th>Balance</th>
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
                  <td>
                    <button className="cell-btn" onClick={() => editOrders(a)} title="Set orders">
                      {a.orders} ✎
                    </button>
                  </td>
                  <td>
                    <button className="cell-btn" onClick={() => editShippedOrders(a)} title="Set shipped orders">
                      {a.shipped_orders} ✎
                    </button>
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {balanceById.has(a.id) ? (
                      <strong>{fmtRs(balanceById.get(a.id) as number)}</strong>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
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

      <NotSignedUpCard
        rows={data.not_signed_up}
        refresh={refresh}
        onError={onError}
        onCreated={(username, pw) => onTempPw(username, pw, "created")}
      />
    </>
  );
}

/* Registered bot users that have no portal account yet. Since 2026-08-06 this
   is the ONLY way an account is created — self-signup is closed (the portal
   login asks for a username and password only), so the admin sets both here
   and passes them on out-of-band via "Copy all details". */
function NotSignedUpCard({
  rows,
  refresh,
  onError,
  onCreated,
}: {
  rows: { id: number; name: string; whatsapp_number: string }[];
  refresh: () => void;
  onError: (m: string) => void;
  onCreated: (username: string, pw: string) => void;
}) {
  const [openId, setOpenId] = useState<number | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");

  // Deliberately no suggested username: pre-filling one from the person's name
  // meant the admin had to clear the box before typing, and a half-edited
  // suggestion could be saved by accident.
  const open = (u: { id: number; name: string }) => {
    setOpenId(u.id);
    setUsername("");
    setPassword("");
  };

  const create = async (u: { name: string; whatsapp_number: string }) => {
    setBusy(true);
    try {
      const res = await portalAdmin.createAccount({
        whatsapp_number: u.whatsapp_number,
        username: username.trim(),
        password,
      });
      onCreated(res.username, password);
      setOpenId(null);
      setUsername("");
      setPassword("");
      refresh();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const needle = q.trim().toLowerCase();
  const shown = needle
    ? rows.filter(
        (u) =>
          u.name.toLowerCase().includes(needle) || u.whatsapp_number.includes(needle),
      )
    : rows;

  return (
    <div className="card" style={{ marginTop: 18 }}>
      <h2>Registered bot users without a portal account ({rows.length})</h2>
      <p className="muted" style={{ marginTop: -6, marginBottom: 10, fontSize: 13 }}>
        Create an account on their behalf by setting a username and password —
        tell them separately. They can change the password in their Profile.
      </p>
      {rows.length > 10 && (
        <input
          style={{ maxWidth: 260, marginBottom: 10 }}
          placeholder="Search name or number…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      )}
      {rows.length === 0 ? (
        <p className="muted">Every registered bot user already has a portal account.</p>
      ) : (
        <div className="table-scroll" style={{ maxHeight: 430, overflowY: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Number</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((u) => (
                <Fragment key={u.id}>
                  <tr>
                    <td>{u.name}</td>
                    <td>{u.whatsapp_number}</td>
                    <td className="row-actions">
                      <button
                        className={openId === u.id ? "cell-btn" : "btn-red"}
                        onClick={() => (openId === u.id ? setOpenId(null) : open(u))}
                      >
                        {openId === u.id ? "Cancel" : "Create account"}
                      </button>
                    </td>
                  </tr>
                  {openId === u.id && (
                    <tr>
                      <td colSpan={3} style={{ background: "var(--soft-cloud)" }}>
                        <div
                          style={{
                            display: "flex",
                            gap: 8,
                            flexWrap: "wrap",
                            alignItems: "center",
                          }}
                        >
                          <input
                            style={{ maxWidth: 200 }}
                            placeholder="username"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                          />
                          <input
                            style={{ maxWidth: 200 }}
                            placeholder="password (min 8 chars)"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                          />
                          <button
                            className="btn-red-solid"
                            disabled={busy || username.trim().length < 3 || password.length < 8}
                            onClick={() => create(u)}
                          >
                            {busy ? "Creating…" : "Create"}
                          </button>
                          <span className="muted" style={{ fontSize: 12 }}>
                            Letters, numbers and _ only · password at least 8 characters
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > 0 && shown.length === 0 && (
        <p className="muted">No user matches “{q}”.</p>
      )}
    </div>
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
  accounts,
  back,
}: {
  account: PortalAdminAccount;
  accounts: EarningsUserRow[];
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
  // The API returns links newest-first, so "recent" is simply the head.
  const recent = (links ?? []).slice(0, 10);

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

      <div className="card">
        <h2>Tracking IDs</h2>
        <p className="muted" style={{ marginTop: -6, marginBottom: 10, fontSize: 13 }}>
          The user's affiliate tag per country, synced with the Overview tab —
          edit these in Overview.
        </p>
        {account.tracking_ids.length === 0 ? (
          <p className="muted">No tracking IDs set for this user yet.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Country</th><th>Marketplace</th><th>Tracking ID</th></tr>
              </thead>
              <tbody>
                {account.tracking_ids.map((t) => (
                  <tr key={t.marketplace_code}>
                    <td><span className="badge">{t.marketplace_code}</span></td>
                    <td className="muted">{t.marketplace_name}</td>
                    <td>{t.tag ? <code>{t.tag}</code> : <span className="muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <UserEarnings accountId={account.id} accounts={accounts} />

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
            <h2>Recent links</h2>
            <p className="muted" style={{ marginTop: -6, marginBottom: 10, fontSize: 13 }}>
              The 10 most recent
              {links.length > 10 ? <> of {links.length} total</> : null}.
            </p>
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
                  {recent.map((l) => (
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
  const [money, setMoney] = useState<EarningsOverview["totals"] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    portalAdmin
      .performance(days)
      .then(setData)
      .catch((e) => setError((e as Error).message));
  }, [days]);

  // Loaded once, outside the day filter: money owed is a running total, not
  // something that happened inside a 7-day window.
  useEffect(() => {
    portalAdmin
      .earnings()
      .then((d) => setMoney(d.totals))
      .catch(() => setMoney(null));
  }, []);

  if (error) return <div className="error-box">{error}</div>;

  const moneyCard = money && (
    <div className="card">
      <h2>Money</h2>
      <p className="muted" style={{ marginTop: -6, fontSize: 13 }}>
        Across every user, all time — the date filter below does not apply to
        these.
      </p>
      <div className="stats">
        <div className="stat">
          <div className="stat-number">{fmtRs(money.to_be_paid)}</div>
          To be paid
        </div>
        <div className="stat">
          <div className="stat-number">{fmtRs(money.paid)}</div>
          Paid
        </div>
      </div>
      {money.overdrawn_users > 0 && (
        <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
          {money.overdrawn_users} user
          {money.overdrawn_users === 1 ? " has" : "s have"} been paid more than
          they have earned; they count as zero above rather than reducing the
          total, since one person's overpayment cannot fund another's.
        </p>
      )}
    </div>
  );

  if (!data)
    return (
      <>
        {moneyCard}
        <p className="muted">Loading performance…</p>
      </>
    );

  const users = data.per_user
    .slice()
    .sort((a, b) => b[metric] - a[metric])
    .slice(0, 10);
  const maxVal = Math.max(1, ...users.flatMap((u) => [u.views, u.clicks]));

  return (
    <>
      {moneyCard}
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


/* ----------------------------------------------------------- earnings */

function fmtRs(n: number) {
  return "Rs " + n.toLocaleString();
}

type EntryKind = "earning" | "bonus" | "adjustment" | "return";

type EntryEdit = {
  id: number; kind: EntryKind; label: string;
  gross: string; rate: string; share: string; date: string;
};

/* Share follows gross x rate as the admin types, but stays editable — the
   figure Amazon actually paid sometimes differs from the arithmetic. */
function recalc(e: EntryEdit): EntryEdit {
  const gross = Number(e.gross);
  const rate = Number(e.rate);
  if (isNaN(gross) || isNaN(rate) || e.gross === "" || e.rate === "") return e;
  return { ...e, share: String(Math.round((gross * rate) / 100)) };
}

/* The per-user earnings management, rendered inside the account detail page
   (the standalone Earnings tab was removed). */
function UserEarnings({ accountId, accounts }: { accountId: number; accounts: EarningsUserRow[] }) {
  const [data, setData] = useState<EarningsDetailData | null>(null);
  const [error, setError] = useState("");
  const [gross, setGross] = useState("");
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [otherKind, setOtherKind] = useState<OtherKind>("bonus");
  const [returnCount, setReturnCount] = useState("");
  const [payOrders, setPayOrders] = useState("");
  const [otherAmount, setOtherAmount] = useState("");
  const [otherLabel, setOtherLabel] = useState("");
  const [payAmount, setPayAmount] = useState("");
  const [payNote, setPayNote] = useState("");
  const [refMode, setRefMode] = useState<"user" | "name">("user");
  const [refUserId, setRefUserId] = useState("");
  const [refName, setRefName] = useState("");
  const [refAmount, setRefAmount] = useState("");
  const [refNote, setRefNote] = useState("");
  // Inline edit of an existing referral reward (they change day to day).
  const [edit, setEdit] = useState<{
    id: number; mode: "user" | "name"; userId: string; name: string;
    amount: string; note: string; date: string;
  } | null>(null);
  // Inline edit of an existing earnings entry.
  const [eEdit, setEEdit] = useState<EntryEdit | null>(null);

  const load = useCallback(() => {
    portalAdmin
      .earningsDetail(accountId)
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e) => setError((e as Error).message));
  }, [accountId]);

  useEffect(load, [load]);

  if (error) return <div className="error-box">{error}</div>;
  if (!data) return <p className="muted">Loading…</p>;

  const preview = gross && !isNaN(Number(gross))
    ? Math.round((Number(gross) * data.rate) / 100)
    : null;

  const addEarning = async () => {
    try {
      await portalAdmin.addEntry(accountId, {
        kind: "earning", gross_amount: Number(gross), label, note,
      });
      setGross(""); setLabel(""); setNote("");
      load();
    } catch (e) { setError((e as Error).message); }
  };

  const addOther = async () => {
    try {
      await portalAdmin.addEntry(accountId, {
        kind: otherKind, net_amount: Number(otherAmount), label: otherLabel,
        ...(otherKind === "return"
          ? { orders_count: Number(returnCount) || 0 }
          : {}),
      });
      setOtherAmount(""); setOtherLabel(""); setReturnCount("");
      load();
    } catch (e) { setError((e as Error).message); }
  };

  const addPayout = async () => {
    try {
      await portalAdmin.addPayout(accountId, {
        amount: Number(payAmount),
        orders_paid: Number(payOrders) || 0,
        note: payNote,
      });
      setPayAmount(""); setPayOrders(""); setPayNote("");
      load();
    } catch (e) { setError((e as Error).message); }
  };

  const addReferral = async () => {
    try {
      const body: Record<string, unknown> = { amount: Number(refAmount), note: refNote };
      if (refMode === "user") {
        if (!refUserId) { setError("Pick the referred user"); return; }
        body.referred_account_id = Number(refUserId);
      } else {
        body.referred_name = refName;
      }
      await portalAdmin.addReferral(accountId, body);
      setRefUserId(""); setRefName(""); setRefAmount(""); setRefNote("");
      load();
    } catch (e) { setError((e as Error).message); }
  };

  const startEdit = (r: ReferralOut) => {
    const isUser = r.referred_name.startsWith("@");
    const match = isUser
      ? accounts.find((u) => `@${u.username}` === r.referred_name)
      : undefined;
    setEdit({
      id: r.id,
      mode: isUser ? "user" : "name",
      userId: match ? String(match.account_id) : "",
      name: isUser ? "" : r.referred_name,
      amount: String(r.amount),
      note: r.note,
      date: r.created_at.slice(0, 10),
    });
  };

  const saveReferral = async () => {
    if (!edit) return;
    const amount = Number(edit.amount);
    if (isNaN(amount) || amount <= 0) { setError("Reward must be a positive number"); return; }
    const body: Record<string, unknown> = {
      amount, note: edit.note, created_at: edit.date,
    };
    if (edit.mode === "user") {
      if (!edit.userId) { setError("Pick the referred user"); return; }
      body.referred_account_id = Number(edit.userId);
    } else {
      if (!edit.name.trim()) { setError("Enter the referred person's name"); return; }
      body.referred_name = edit.name.trim();
    }
    try {
      await portalAdmin.updateReferral(accountId, edit.id, body);
      setEdit(null);
      load();
    } catch (e) { setError((e as Error).message); }
  };

  const delReferral = async (id: number) => {
    if (!confirm("Delete this referral reward? Balance recalculates.")) return;
    try { await portalAdmin.deleteReferral(accountId, id); load(); }
    catch (e) { setError((e as Error).message); }
  };

  const startEntryEdit = (e: EarningsEntryOut) => {
    setEEdit({
      id: e.id,
      kind: e.kind as EntryKind,
      label: e.label,
      gross: e.kind === "earning" ? String(e.gross_amount) : "",
      rate: e.kind === "earning" ? String(e.rate_applied) : String(data.rate),
      share: String(e.net_amount),
      date: e.created_at.slice(0, 10),
    });
  };

  const saveEntry = async () => {
    if (!eEdit) return;
    if (!eEdit.label.trim()) { setError("Label is required"); return; }
    const share = Number(eEdit.share);
    if (isNaN(share)) { setError("Share must be a number"); return; }
    const body: Record<string, unknown> = {
      kind: eEdit.kind, label: eEdit.label.trim(),
      net_amount: share, created_at: eEdit.date,
    };
    if (eEdit.kind === "earning") {
      const gross = Number(eEdit.gross);
      const rate = Number(eEdit.rate);
      if (isNaN(gross) || gross <= 0) { setError("Gross must be a positive number"); return; }
      if (isNaN(rate) || rate < 0 || rate > 100) { setError("Rate must be 0–100"); return; }
      body.gross_amount = gross;
      body.rate_applied = rate;
    } else if (share === 0) {
      setError("Amount cannot be zero"); return;
    }
    try {
      await portalAdmin.updateEntry(accountId, eEdit.id, body);
      setEEdit(null);
      load();
    } catch (e) { setError((e as Error).message); }
  };

  const delEntry = async (id: number) => {
    if (!confirm("Delete this entry? Balances recalculate.")) return;
    try { await portalAdmin.deleteEntry(accountId, id); load(); }
    catch (e) { setError((e as Error).message); }
  };

  const delPayout = async (id: number) => {
    if (!confirm("Delete this payout record? Balances recalculate.")) return;
    try { await portalAdmin.deletePayout(accountId, id); load(); }
    catch (e) { setError((e as Error).message); }
  };

  const editRate = async () => {
    const raw = prompt(
      `Commission rate % for @${data.username} (0-100).\nLeave empty to use the default rate.`,
      data.custom_rate === null ? "" : String(data.rate),
    );
    if (raw === null) return;
    try {
      await portalAdmin.setRate(accountId, raw.trim() === "" ? null : Number(raw));
      load();
    } catch (e) { setError((e as Error).message); }
  };

  return (
    <>
      <div className="card">
        <h2>Earnings</h2>
        <p className="muted" style={{ fontSize: 13, marginTop: -4 }}>
          Rate: <strong>{data.rate}%</strong>{" "}
          {data.custom_rate === null ? "(default)" : "(custom)"}{" "}
          <button className="cell-btn" onClick={editRate}>Set rate</button>
          {data.payout_method ? <> · Payout: {data.payout_method}</> : " · No payout details saved"}
        </p>
        <div className="stats">
          <div className="stat"><div className="stat-number">{fmtRs(data.earned)}</div>Earned (share)</div>
          <div className="stat"><div className="stat-number">{fmtRs(data.paid)}</div>Paid out</div>
          <div className="stat"><div className="stat-number">{fmtRs(data.balance)}</div>Pending</div>
        </div>
      </div>

      <div className="card">
        <h2>Add earning</h2>
        <p className="muted" style={{ marginTop: -6, fontSize: 13 }}>
          Enter the GROSS amount (PKR) this user's tracking IDs earned — the
          system applies their {data.rate}% share automatically.
        </p>
        <div className="form-row">
          <input placeholder="Gross amount (PKR)" value={gross} onChange={(e) => setGross(e.target.value)} />
          <input placeholder="Label (e.g. July 2026)" value={label} onChange={(e) => setLabel(e.target.value)} />
          <input placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="primary" onClick={addEarning}>
            Add{preview !== null ? ` → share ${fmtRs(preview)}` : ""}
          </button>
        </div>
      </div>

      <div className="card">
        <h2>Add bonus / adjustment / return</h2>
        <p className="muted" style={{ marginTop: -6, fontSize: 13 }}>
          Direct amounts (no rate applied). A <strong>return</strong> always
          comes off the user's earnings, so the sign does not matter — enter 500
          or -500 for a 500 clawback and you get the same result. Returned units
          show as their own figure and do not reduce Total orders.
        </p>
        <div className="form-row">
          <select
            value={otherKind}
            onChange={(e) => setOtherKind(e.target.value as OtherKind)}
          >
            <option value="bonus">Bonus (e.g. referral)</option>
            <option value="adjustment">Adjustment (+/-)</option>
            <option value="return">Return (always -)</option>
          </select>
          <input placeholder="Amount (PKR)" value={otherAmount} onChange={(e) => setOtherAmount(e.target.value)} />
          {otherKind === "return" && (
            <input
              placeholder="Return orders"
              value={returnCount}
              onChange={(e) => setReturnCount(e.target.value)}
              style={{ maxWidth: 140 }}
            />
          )}
          <input placeholder="Label" value={otherLabel} onChange={(e) => setOtherLabel(e.target.value)} />
          <button className="primary" onClick={addOther}>Add</button>
        </div>
      </div>

      <div className="card">
        <h2>Referral rewards ({data.referrals.length})</h2>
        <p className="muted" style={{ marginTop: -6, fontSize: 13 }}>
          Reward @{data.username} for referring someone. The amount is added to
          their earnings balance.
        </p>
        <div className="form-row">
          <select value={refMode} onChange={(e) => setRefMode(e.target.value as "user" | "name")}>
            <option value="user">Referred a portal user</option>
            <option value="name">Referred (name)</option>
          </select>
          {refMode === "user" ? (
            <select value={refUserId} onChange={(e) => setRefUserId(e.target.value)}>
              <option value="">— pick user —</option>
              {accounts
                .filter((u) => u.account_id !== accountId)
                .map((u) => (
                  <option key={u.account_id} value={u.account_id}>@{u.username}</option>
                ))}
            </select>
          ) : (
            <input placeholder="Referred person's name" value={refName} onChange={(e) => setRefName(e.target.value)} />
          )}
          <input placeholder="Reward (PKR)" value={refAmount} onChange={(e) => setRefAmount(e.target.value)} />
          <input placeholder="Note (optional)" value={refNote} onChange={(e) => setRefNote(e.target.value)} />
          <button className="primary" onClick={addReferral}>Add referral</button>
        </div>
        {data.referrals.length > 0 && (
          <div className="table-scroll" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr><th>Referred</th><th>Reward</th><th>Note</th><th>Date</th><th></th></tr>
              </thead>
              <tbody>
                {data.referrals.map((r) =>
                  edit && edit.id === r.id ? (
                    <tr key={r.id}>
                      <td>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          <select
                            value={edit.mode}
                            onChange={(e) => setEdit({ ...edit, mode: e.target.value as "user" | "name" })}
                          >
                            <option value="user">Portal user</option>
                            <option value="name">Name</option>
                          </select>
                          {edit.mode === "user" ? (
                            <select
                              value={edit.userId}
                              onChange={(e) => setEdit({ ...edit, userId: e.target.value })}
                            >
                              <option value="">— pick user —</option>
                              {accounts
                                .filter((u) => u.account_id !== accountId)
                                .map((u) => (
                                  <option key={u.account_id} value={u.account_id}>@{u.username}</option>
                                ))}
                            </select>
                          ) : (
                            <input
                              style={{ maxWidth: 160 }}
                              value={edit.name}
                              onChange={(e) => setEdit({ ...edit, name: e.target.value })}
                            />
                          )}
                        </div>
                      </td>
                      <td>
                        <input
                          style={{ maxWidth: 110 }}
                          value={edit.amount}
                          onChange={(e) => setEdit({ ...edit, amount: e.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          style={{ maxWidth: 160 }}
                          value={edit.note}
                          onChange={(e) => setEdit({ ...edit, note: e.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          type="date"
                          style={{ maxWidth: 150 }}
                          value={edit.date}
                          onChange={(e) => setEdit({ ...edit, date: e.target.value })}
                        />
                      </td>
                      <td className="row-actions">
                        <button className="primary" onClick={saveReferral}>Save</button>
                        <button className="cell-btn" onClick={() => setEdit(null)}>Cancel</button>
                      </td>
                    </tr>
                  ) : (
                    <tr key={r.id}>
                      <td>{r.referred_name}</td>
                      <td><strong>{fmtRs(r.amount)}</strong></td>
                      <td className="muted">{r.note || "—"}</td>
                      <td className="muted" style={{ whiteSpace: "nowrap" }}>{new Date(r.created_at).toLocaleDateString()}</td>
                      <td className="row-actions">
                        <button className="cell-btn" onClick={() => startEdit(r)}>Edit</button>
                        <button className="danger" onClick={() => delReferral(r.id)}>Delete</button>
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Record payout</h2>
        <p className="muted" style={{ marginTop: -6, fontSize: 13 }}>
          Both figures come off what the user sees: the amount off their current
          earnings, the orders off their Total and Shipped orders.{" "}
          <strong>{data.current_orders}</strong> order
          {data.current_orders === 1 ? "" : "s"} outstanding
          {data.orders_entered !== data.current_orders && (
            <> of {data.orders_entered} entered</>
          )}
          . Nothing is overwritten — delete a payout and it all comes back.
        </p>
        <div className="form-row">
          <input placeholder="Amount (PKR)" value={payAmount} onChange={(e) => setPayAmount(e.target.value)} />
          <input
            placeholder="Orders paid"
            value={payOrders}
            onChange={(e) => setPayOrders(e.target.value)}
            style={{ maxWidth: 140 }}
          />
          <input placeholder="Note (optional)" value={payNote} onChange={(e) => setPayNote(e.target.value)} />
          <button className="primary" onClick={addPayout}>Record payout</button>
        </div>
        {data.payout_method && (
          <p className="muted" style={{ fontSize: 12 }}>Will be recorded against: {data.payout_method}</p>
        )}
      </div>

      <div className="card">
        <h2>Entries ({data.entries.length})</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Kind</th><th>Label</th><th>Gross</th><th>Rate</th><th>Share</th><th>Date</th><th></th>
              </tr>
            </thead>
            <tbody>
              {data.entries.map((e) =>
                eEdit && eEdit.id === e.id ? (
                  <tr key={e.id}>
                    <td>
                      <select
                        value={eEdit.kind}
                        onChange={(ev) => setEEdit({ ...eEdit, kind: ev.target.value as EntryKind })}
                      >
                        <option value="earning">earning</option>
                        <option value="bonus">bonus</option>
                        <option value="adjustment">adjustment</option>
                        <option value="return">return</option>
                      </select>
                    </td>
                    <td>
                      <input
                        style={{ maxWidth: 150 }}
                        value={eEdit.label}
                        onChange={(ev) => setEEdit({ ...eEdit, label: ev.target.value })}
                      />
                    </td>
                    <td>
                      {eEdit.kind === "earning" ? (
                        <input
                          style={{ maxWidth: 110 }}
                          value={eEdit.gross}
                          onChange={(ev) => setEEdit(recalc({ ...eEdit, gross: ev.target.value }))}
                        />
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      {eEdit.kind === "earning" ? (
                        <input
                          style={{ maxWidth: 70 }}
                          value={eEdit.rate}
                          onChange={(ev) => setEEdit(recalc({ ...eEdit, rate: ev.target.value }))}
                        />
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      <input
                        style={{ maxWidth: 110 }}
                        value={eEdit.share}
                        onChange={(ev) => setEEdit({ ...eEdit, share: ev.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        type="date"
                        style={{ maxWidth: 150 }}
                        value={eEdit.date}
                        onChange={(ev) => setEEdit({ ...eEdit, date: ev.target.value })}
                      />
                    </td>
                    <td className="row-actions">
                      <button className="btn-red-solid" onClick={saveEntry}>Save</button>
                      <button className="cell-btn" onClick={() => setEEdit(null)}>Cancel</button>
                    </td>
                  </tr>
                ) : (
                  <tr key={e.id}>
                    <td><span className={`badge ${e.kind === "earning" ? "" : "warn"}`}>{e.kind}</span></td>
                    <td>{e.label}{e.note ? <span className="muted"> — {e.note}</span> : null}</td>
                    <td>{e.kind === "earning" ? fmtRs(e.gross_amount) : "—"}</td>
                    <td>{e.kind === "earning" ? `${e.rate_applied}%` : "—"}</td>
                    <td><strong>{fmtRs(e.net_amount)}</strong></td>
                    <td className="muted" style={{ whiteSpace: "nowrap" }}>{new Date(e.created_at).toLocaleDateString()}</td>
                    <td className="row-actions">
                      <button className="cell-btn" onClick={() => startEntryEdit(e)}>Edit</button>
                      <button className="danger" onClick={() => delEntry(e.id)}>Delete</button>
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
        {data.entries.length === 0 && <p className="muted">No entries yet.</p>}
      </div>

      <div className="card">
        <h2>Payouts ({data.payouts.length})</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Amount</th><th>Orders</th><th>Method</th><th>Note</th><th>Date</th><th></th></tr>
            </thead>
            <tbody>
              {data.payouts.map((pRow) => (
                <tr key={pRow.id}>
                  <td><strong>{fmtRs(pRow.amount)}</strong></td>
                  <td>{pRow.orders_paid || <span className="muted">—</span>}</td>
                  <td className="muted">{pRow.method || "—"}</td>
                  <td className="muted">{pRow.note || "—"}</td>
                  <td className="muted" style={{ whiteSpace: "nowrap" }}>{new Date(pRow.paid_at).toLocaleDateString()}</td>
                  <td><button className="danger" onClick={() => delPayout(pRow.id)}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.payouts.length === 0 && <p className="muted">No payouts recorded yet.</p>}
      </div>
    </>
  );
}
