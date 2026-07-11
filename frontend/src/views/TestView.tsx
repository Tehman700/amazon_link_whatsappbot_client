import { useState } from "react";
import { api } from "../api";
import type { ProcessResponse, User } from "../types";

interface Props {
  users: User[];
}

const SAMPLE_TEXT =
  "Usa review\nStore name: YusersaEssentials\nhttps://www.amazon.com/dp/B0GS64BBG2?th=1";

export default function TestView({ users }: Props) {
  const [sender, setSender] = useState(users[0]?.whatsapp_number ?? "");
  const [text, setText] = useState(SAMPLE_TEXT);
  const [result, setResult] = useState<ProcessResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setError(null);
    setResult(null);
    try {
      setResult(await api.processMessage(sender, text));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <section>
      <div className="card">
        <h2>Test message processing</h2>
        <p className="muted">
          Simulates an incoming WhatsApp message hitting <code>POST /process-message</code>.
        </p>
        <label className="stacked">
          <span>Sender (WhatsApp number)</span>
          <select value={sender} onChange={(e) => setSender(e.target.value)}>
            {users.map((u) => (
              <option key={u.id} value={u.whatsapp_number}>
                {u.name} — {u.whatsapp_number}
              </option>
            ))}
            <option value="+99999999999">Unregistered number (test 404)</option>
          </select>
        </label>
        <label className="stacked">
          <span>Message text / caption</span>
          <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <button className="primary" onClick={run}>Process</button>
      </div>

      {error && <div className="card error-box">Error: {error}</div>}

      {result && (
        <div className="card">
          <h3>Result — {result.links_replaced} link(s) replaced</h3>
          <pre className="result-text">{result.text}</pre>
          {result.replacements.map((r, i) => (
            <div key={i} className="replacement">
              <span className="badge">{r.marketplace_code}</span>
              <div>
                <div className="muted strike">{r.original}</div>
                <div className="ok">{r.rewritten}</div>
              </div>
            </div>
          ))}
          {result.skipped.map((s, i) => (
            <div key={i} className="replacement">
              <span className="badge warn">skipped</span>
              <div>
                <div>{s.url}</div>
                <div className="muted">{s.reason}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
