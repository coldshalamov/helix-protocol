import React, { useState, useRef, useEffect } from "react";
import axios from "axios";

export default function DiceRoller() {
  const [seed, setSeed] = useState("");
  const [size, setSize] = useState(0); // purely visual
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const inputRef = useRef(null);

  const roll = () => {
    setLoading(true);
    setError("");
    setOutput("");
    axios
      .post("/api/generate", { seed, size: 16 }) // always return 16 chars
      .then((res) => {
        if (res.data?.output) {
          setOutput(res.data.output);
        } else {
          setError("Invalid response");
        }
      })
      .catch(() => setError("Failed to generate"))
      .finally(() => setLoading(false));
  };

  // ⌨️ Handle Enter in seed field
  useEffect(() => {
    const handler = (e) => {
      if (document.activeElement === inputRef.current && e.key === "Enter") {
        roll();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [seed]);

  return (
    <div className="fixed right-0 top-0 w-64 h-full bg-white shadow-lg p-4 rounded-l-lg flex flex-col items-center justify-start">
      <h2 className="text-lg font-semibold mb-2">🎲 Dice Roller</h2>
      <label className="text-sm font-medium">Seed</label>
      <input
        ref={inputRef}
        className="border p-1 mb-2 w-full"
        value={seed}
        onChange={(e) => setSeed(e.target.value)}
        placeholder="base64 or string"
      />
      <label className="text-sm font-medium">Highlight First N Chars</label>
      <input
        type="number"
        min="0"
        max="16"
        className="border p-1 mb-2 w-full"
        value={size}
        onChange={(e) => setSize(Number(e.target.value))}
      />
      <button onClick={roll} className="mb-4">
        <img src="/helix_icon.ico" alt="roll" className="w-4 h-4 mx-auto" />
      </button>
      {loading && <div className="text-sm">Loading...</div>}
      {error && <div className="text-sm text-red-600">{error}</div>}
      {output && (
        <pre className="mt-2 bg-gray-100 p-2 overflow-auto font-mono break-all w-full text-sm">
          <span style={{ color: "#0070B8" }}>{output.slice(0, size)}</span>
          <span>{output.slice(size)}</span>
        </pre>
      )}
    </div>
  );
}
