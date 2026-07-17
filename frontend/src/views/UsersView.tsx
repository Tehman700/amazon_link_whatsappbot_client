import { useState } from "react";
import { api } from "../api";
import type { Marketplace, User } from "../types";

interface Props {
  users: User[];
  marketplaces: Marketplace[];
  refresh: () => Promise<void>;
  onError: (message: string) => void;
}

const emptyForm = { name: "", whatsapp_number: "", email: "" };

export default function UsersView({ users, marketplaces, refresh, onError }: Props) {
  const [form, setForm] = useState(emptyForm);
  const [expanded, setExpanded] = useState<number | null>(null);

  const addUser = async () => {
    if (!form.name.trim() || !form.whatsapp_number.trim()) {
      onError("Name and WhatsApp number are required");
      return;
    }
    try {
      await api.createUser({
        name: form.name.trim(),
        whatsapp_number: form.whatsapp_number.trim(),
        email: form.email.trim() || null,
      });
      setForm(emptyForm);
      await refresh();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  return (
    <section>
      <div className="card">
        <h2>Add user</h2>
        <div className="form-row">
          <input
            placeholder="Name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            placeholder="WhatsApp number (e.g. +923001234567)"
            value={form.whatsapp_number}
            onChange={(e) => setForm({ ...form, whatsapp_number: e.target.value })}
          />
          <input
            placeholder="Email (optional)"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <button className="primary" onClick={addUser}>Add</button>
        </div>
      </div>

      {users.map((user) => (
        <UserCard
          key={user.id}
          user={user}
          marketplaces={marketplaces}
          expanded={expanded === user.id}
          toggle={() => setExpanded(expanded === user.id ? null : user.id)}
          refresh={refresh}
          onError={onError}
        />
      ))}
      {users.length === 0 && <p className="muted">No users yet.</p>}
    </section>
  );
}

function UserCard({
  user,
  marketplaces,
  expanded,
  toggle,
  refresh,
  onError,
}: {
  user: User;
  marketplaces: Marketplace[];
  expanded: boolean;
  toggle: () => void;
  refresh: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [edit, setEdit] = useState({
    name: user.name,
    whatsapp_number: user.whatsapp_number,
    email: user.email ?? "",
    link_preference: user.link_preference ?? "direct",
    store_name: user.store_name ?? "",
  });
  const [tags, setTags] = useState<Record<number, string>>(() =>
    Object.fromEntries(user.tracking_ids.map((t) => [t.marketplace_id, t.tag])),
  );

  const saveUser = async () => {
    try {
      await api.updateUser(user.id, {
        name: edit.name.trim(),
        whatsapp_number: edit.whatsapp_number.trim(),
        email: edit.email.trim() || null,
        link_preference: edit.link_preference,
        store_name: edit.store_name.trim(),
      });
      await refresh();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const removeUser = async () => {
    if (!confirm(`Delete user "${user.name}" and all their tracking IDs?`)) return;
    try {
      await api.deleteUser(user.id);
      await refresh();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const saveTags = async () => {
    const existing = Object.fromEntries(
      user.tracking_ids.map((t) => [t.marketplace_id, t.tag]),
    );
    const upserts = marketplaces
      .filter((m) => (tags[m.id] ?? "").trim() && tags[m.id]?.trim() !== existing[m.id])
      .map((m) => ({ marketplace_id: m.id, tag: tags[m.id].trim() }));
    const deletions = marketplaces.filter(
      (m) => existing[m.id] && !(tags[m.id] ?? "").trim(),
    );
    try {
      if (upserts.length) await api.setTrackingIds(user.id, upserts);
      for (const m of deletions) await api.deleteTrackingId(user.id, m.id);
      await refresh();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  return (
    <div className="card">
      <div className="user-header" onClick={toggle}>
        <div>
          <strong>{user.name}</strong>
          <span className="muted"> · {user.whatsapp_number}</span>
          {user.email && <span className="muted"> · {user.email}</span>}
          {user.link_preference === "hub" && (
            <span className="muted"> · hub{user.store_name ? ` (${user.store_name})` : ""}</span>
          )}
        </div>
        <span className="muted">
          {user.tracking_ids.length} tag{user.tracking_ids.length === 1 ? "" : "s"}{" "}
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {expanded && (
        <div className="user-body">
          <h3>Details</h3>
          <div className="form-row">
            <input
              value={edit.name}
              onChange={(e) => setEdit({ ...edit, name: e.target.value })}
            />
            <input
              value={edit.whatsapp_number}
              onChange={(e) => setEdit({ ...edit, whatsapp_number: e.target.value })}
            />
            <input
              placeholder="Email (optional)"
              value={edit.email}
              onChange={(e) => setEdit({ ...edit, email: e.target.value })}
            />
            <button className="primary" onClick={saveUser}>Save</button>
            <button className="danger" onClick={removeUser}>Delete user</button>
          </div>

          <h3>Reply format</h3>
          <div className="form-row">
            <select
              value={edit.link_preference}
              onChange={(e) =>
                setEdit({ ...edit, link_preference: e.target.value as "direct" | "hub" })
              }
            >
              <option value="direct">Direct Amazon link (default)</option>
              <option value="hub">Hub article page</option>
            </select>
            <input
              placeholder="Store name shown on articles (optional)"
              value={edit.store_name}
              onChange={(e) => setEdit({ ...edit, store_name: e.target.value })}
            />
            <button className="primary" onClick={saveUser}>Save</button>
          </div>

          <h3>Tracking IDs</h3>
          <div className="tags-grid">
            {marketplaces.map((m) => (
              <label key={m.id}>
                <span>
                  {m.code} <span className="muted">({m.domain})</span>
                </span>
                <input
                  placeholder="no tag — leave empty to unset"
                  value={tags[m.id] ?? ""}
                  onChange={(e) => setTags({ ...tags, [m.id]: e.target.value })}
                />
              </label>
            ))}
          </div>
          <button className="primary" onClick={saveTags}>Save tracking IDs</button>
        </div>
      )}
    </div>
  );
}
