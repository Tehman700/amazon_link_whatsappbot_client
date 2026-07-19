import { useCallback, useEffect, useState } from "react";
import { portalAdmin } from "../api";
import type { PortalAdminAccount, PortalAdminData } from "../types";

type SubTab = "accounts" | "linked" | "payouts";

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

  return (
    <>
      <div className="card">
        <h2>Portal accounts</h2>
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
                  <td>
                    <strong>@{a.username}</strong>
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

      <div className="card">
        <h2>Registered bot users without a portal account ({data.not_signed_up.length})</h2>
        {data.not_signed_up.length === 0 ? (
          <p className="muted">Everyone has signed up. 🎉</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>WhatsApp number</th>
                </tr>
              </thead>
              <tbody>
                {data.not_signed_up.map((u) => (
                  <tr key={u.whatsapp_number}>
                    <td>{u.name}</td>
                    <td>{u.whatsapp_number}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
