import React, { useState } from "react";
import axios from "axios";

export default function DiceRoller() {
  const [seed, setSeed] = useState("");
  const [size, setSize] = useState(0);
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const roll = () => {
    setLoading(true);
    setError("");
    setOutput("");
    axios
      .post("/api/generate", { seed })
      .then((res) => {
        if (res.data && res.data.output) {
          setOutput(res.data.output);
        } else {
          setError("Invalid response");
        }
      })
      .catch(() => {
        setError("Failed to generate");
      })
      .finally(() => setLoading(false));
  };

  return (
    <div className="fixed right-0 top-0 w-64 h-full bg-white shadow-lg p-4 rounded-l-lg flex flex-col">
      <h2 className="text-lg font-semibold mb-2">🎲 Dice Roller</h2>
      <label className="text-sm font-medium">Seed</label>
      <input
        className="border p-1 mb-2 w-full"
        value={seed}
        onChange={(e) => setSeed(e.target.value)}
        placeholder="base64 or hex"
      />
      <label className="text-sm font-medium">Size</label>
      <input
        type="number"
        min="0"
        className="border p-1 mb-2 w-full"
        value={size}
        onChange={(e) => setSize(e.target.value)}
      />
      <button onClick={roll} className="mx-auto mb-2">
        <img src="/helix_icon.ico" alt="roll" className="w-6 h-6" />
      </button>
      {loading && <div className="text-sm">Loading...</div>}
      {error && <div className="text-sm text-red-600">{error}</div>}
      {output && (
        <pre className="mt-2 font-mono flex">
          <span style={{ color: "#00AEEF" }}>{output.slice(0, Number(size))}</span>
          <span>{output.slice(Number(size))}</span>
        </pre>
      )}
    </div>
  );
}
