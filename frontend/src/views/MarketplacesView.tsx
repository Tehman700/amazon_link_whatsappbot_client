import { useState } from "react";
import { api } from "../api";
import type { Marketplace } from "../types";

interface Props {
  marketplaces: Marketplace[];
  refresh: () => Promise<void>;
  onError: (message: string) => void;
}

const emptyForm = { code: "", name: "", domain: "" };

export default function MarketplacesView({ marketplaces, refresh, onError }: Props) {
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState(emptyForm);

  const add = async () => {
    if (!form.code.trim() || !form.name.trim() || !form.domain.trim()) {
      onError("Code, name and domain are all required");
      return;
    }
    try {
      await api.createMarketplace(form);
      setForm(emptyForm);
      await refresh();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const save = async (id: number) => {
    try {
      await api.updateMarketplace(id, editForm);
      setEditingId(null);
      await refresh();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const remove = async (m: Marketplace) => {
    if (!confirm(`Delete marketplace ${m.code} (${m.domain})? All tracking IDs for it will be removed.`)) return;
    try {
      await api.deleteMarketplace(m.id);
      await refresh();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  return (
    <section>
      <div className="card">
        <h2>Add marketplace</h2>
        <div className="form-row">
          <input
            placeholder="Code (e.g. MX)"
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
          />
          <input
            placeholder="Name (e.g. Mexico)"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            placeholder="Domain (e.g. amazon.com.mx)"
            value={form.domain}
            onChange={(e) => setForm({ ...form, domain: e.target.value })}
          />
          <button className="primary" onClick={add}>Add</button>
        </div>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
              <th>Domain</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {marketplaces.map((m) =>
              editingId === m.id ? (
                <tr key={m.id}>
                  <td><input value={editForm.code} onChange={(e) => setEditForm({ ...editForm, code: e.target.value })} /></td>
                  <td><input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} /></td>
                  <td><input value={editForm.domain} onChange={(e) => setEditForm({ ...editForm, domain: e.target.value })} /></td>
                  <td className="row-actions">
                    <button className="primary" onClick={() => save(m.id)}>Save</button>
                    <button onClick={() => setEditingId(null)}>Cancel</button>
                  </td>
                </tr>
              ) : (
                <tr key={m.id}>
                  <td>{m.code}</td>
                  <td>{m.name}</td>
                  <td>{m.domain}</td>
                  <td className="row-actions">
                    <button
                      onClick={() => {
                        setEditingId(m.id);
                        setEditForm({ code: m.code, name: m.name, domain: m.domain });
                      }}
                    >
                      Edit
                    </button>
                    <button className="danger" onClick={() => remove(m)}>Delete</button>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
