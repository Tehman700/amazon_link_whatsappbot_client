import { useState } from "react";
import { api } from "../api";
import type { Marketplace, User } from "../types";

interface Props {
  users: User[];
  marketplaces: Marketplace[];
  refresh: () => Promise<void>;
  onError: (message: string) => void;
}

/** Which cell is being edited: a user field or a marketplace tag. */
type Cell = { userId: number; field: "name" | "whatsapp_number" | "email" | `mp-${number}` };

export default function OverviewView({ users, marketplaces, refresh, onError }: Props) {
  const [editing, setEditing] = useState<Cell | null>(null);
  const [draft, setDraft] = useState("");

  const totalTags = users.reduce((n, u) => n + u.tracking_ids.length, 0);

  const startEdit = (cell: Cell, current: string) => {
    setEditing(cell);
    setDraft(current);
  };

  const commit = async () => {
    if (!editing) return;
    const cell = editing;
    setEditing(null);
    const user = users.find((u) => u.id === cell.userId);
    if (!user) return;
    const value = draft.trim();

    try {
      if (cell.field.startsWith("mp-")) {
        const marketplaceId = Number(cell.field.slice(3));
        const existing =
          user.tracking_ids.find((t) => t.marketplace_id === marketplaceId)?.tag ?? "";
        if (value === existing) return;
        if (value) {
          await api.setTrackingIds(user.id, [{ marketplace_id: marketplaceId, tag: value }]);
        } else {
          await api.deleteTrackingId(user.id, marketplaceId);
        }
      } else {
        const field = cell.field as "name" | "whatsapp_number" | "email";
        const current = user[field] ?? "";
        if (value === current) return;
        if (!value && field !== "email") {
          onError(field === "name" ? "Name cannot be empty" : "WhatsApp number cannot be empty");
          return;
        }
        await api.updateUser(user.id, {
          name: user.name,
          whatsapp_number: user.whatsapp_number,
          email: user.email,
          link_preference: user.link_preference ?? "direct",
          store_name: user.store_name ?? "",
          [field]: field === "email" ? value || null : value,
        });
      }
      await refresh();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const cellContent = (cell: Cell, value: string, placeholder = "—") => {
    const active =
      editing !== null && editing.userId === cell.userId && editing.field === cell.field;
    if (active) {
      return (
        <input
          className="cell-input"
          value={draft}
          autoFocus
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            if (e.key === "Escape") setEditing(null);
          }}
        />
      );
    }
    return (
      <button
        type="button"
        className={"cell-btn" + (value ? "" : " empty")}
        title="Click to edit"
        onClick={() => startEdit(cell, value)}
      >
        {value || placeholder}
      </button>
    );
  };

  return (
    <section>
      <div className="stats">
        <div className="stat">
          <span className="stat-number">{users.length}</span>
          <span className="muted">user{users.length === 1 ? "" : "s"}</span>
        </div>
        <div className="stat">
          <span className="stat-number">{totalTags}</span>
          <span className="muted">tracking IDs</span>
        </div>
        <div className="stat">
          <span className="stat-number">{marketplaces.length}</span>
          <span className="muted">marketplaces</span>
        </div>
      </div>

      <div className="card table-scroll">
        <table className="overview-table">
          <thead>
            <tr>
              <th>User</th>
              <th>WhatsApp</th>
              <th>Email</th>
              {marketplaces.map((m) => (
                <th key={m.id} title={m.domain}>
                  {m.code}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const tags = Object.fromEntries(
                user.tracking_ids.map((t) => [t.marketplace_id, t.tag]),
              );
              return (
                <tr key={user.id}>
                  <td>{cellContent({ userId: user.id, field: "name" }, user.name)}</td>
                  <td>
                    {cellContent(
                      { userId: user.id, field: "whatsapp_number" },
                      user.whatsapp_number,
                    )}
                  </td>
                  <td>{cellContent({ userId: user.id, field: "email" }, user.email ?? "")}</td>
                  {marketplaces.map((m) => (
                    <td key={m.id}>
                      {cellContent({ userId: user.id, field: `mp-${m.id}` }, tags[m.id] ?? "")}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
        {users.length === 0 && <p className="muted">No users yet — add one in the Users tab.</p>}
        <p className="muted overview-hint">Click any cell to edit. Enter saves, Esc cancels; clearing a tag removes it.</p>
      </div>
    </section>
  );
}
