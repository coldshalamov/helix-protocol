import React, { useState } from "react";
import axios from "axios";

export default function SubmitStatement() {
  const [statement, setStatement] = useState("");
  const [microblockSize, setMicroblockSize] = useState(8);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const onSubmit = async (e) => {
    e.preventDefault();
    setResult(null);
    setError("");
    try {
      const res = await axios.post("/api/submit", {
        statement,
        wallet_id: "1",
        microblock_size: microblockSize,
      });
      setResult(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    }
  };

  return (
    <div className="p-4">
      <form onSubmit={onSubmit} className="space-y-4 border p-4 shadow">
        <div>
          <label className="block mb-1 font-semibold">Statement</label>
          <textarea
            className="w-full border p-2"
            rows="4"
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="block mb-1 font-semibold">Microblock Size (bytes)</label>
          <input
            type="number"
            className="border p-2 w-24"
            value={microblockSize}
            onChange={(e) => setMicroblockSize(Number(e.target.value))}
          />
        </div>
        <button
          type="submit"
          className="bg-blue-500 text-white px-4 py-2"
        >
          Submit
        </button>
      </form>
      {result && (
        <div className="mt-4 border p-4 shadow bg-green-50">
          Event ID: {result.event_id}
        </div>
      )}
      {error && (
        <div className="mt-4 border p-4 shadow bg-red-50 text-red-600">
          {error}
        </div>
      )}
    </div>
  );
}
