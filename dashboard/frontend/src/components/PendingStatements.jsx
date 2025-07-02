import React, { useEffect, useState } from "react";
import axios from "axios";

const COLORS = [
  "bg-red-200",
  "bg-green-200",
  "bg-blue-200",
  "bg-yellow-200",
  "bg-purple-200",
  "bg-pink-200",
  "bg-indigo-200",
  "bg-teal-200",
  "bg-orange-200",
  "bg-emerald-200",
];

function StatementBox({ stmt }) {
  const text = stmt.statement || "";
  const size = stmt.microblock_size || 1;
  const mined = Array.isArray(stmt.mined_status) ? stmt.mined_status : [];
  const seeds = Array.isArray(stmt.seeds) ? stmt.seeds : [];
  const bets = stmt.bets || {};
  const yesTotal = bets.YES || bets.TRUE || stmt.total_yes || 0;
  const noTotal = bets.NO || stmt.total_no || 0;

  const segments = [];
  for (let i = 0; i < text.length; i += size) {
    segments.push(text.slice(i, i + size));
  }

  const minedCount = mined.filter(Boolean).length;
  const blockCount = segments.length;

  return (
    <div className="border shadow p-4 mb-4">
      <div className="flex justify-between mb-2">
        <div className="flex flex-col items-center">
          <button className="bg-green-500 text-white px-2 py-1 rounded">TRUE</button>
          <span className="text-sm mt-1">{yesTotal} HLX</span>
        </div>
        <div className="flex flex-col items-center">
          <button className="bg-red-500 text-white px-2 py-1 rounded">FALSE</button>
          <span className="text-sm mt-1">{noTotal} HLX</span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <div className="flex space-x-1 font-mono text-sm">
          {segments.map((seg, i) => {
            const color = COLORS[i % COLORS.length];
            const cls = mined[i] ? `${color} text-black` : "bg-gray-100";
            return (
              <span key={i} className={`${cls} px-1`}>{seg}</span>
            );
          })}
        </div>
        <div className="flex space-x-1 mt-1 text-xs">
          {segments.map((_, i) => {
            const color = COLORS[i % COLORS.length];
            const isMined = mined[i];
            const seed = seeds[i];
            const cls = isMined ? color : "bg-gray-100";
            return (
              <span key={i} className={`${cls} px-1 flex flex-col items-center`}>
                {isMined ? "Mined" : "Pending"}
                {isMined && (
                  <span className="text-[10px] break-all">{seed}</span>
                )}
              </span>
            );
          })}
        </div>
      </div>
      <div className="mt-2">
        <label className="mr-2">Vote</label>
        <input type="number" className="border p-1 w-24" />
      </div>
      <div className="mt-1 text-sm text-gray-600">
        {minedCount} / {blockCount} blocks mined
      </div>
    </div>
  );
}

export default function PendingStatements() {
  const [statements, setStatements] = useState([]);

  useEffect(() => {
    const fetchData = () => {
      axios
        .get("/api/statements/active_status")
        .then((res) => {
          const data = Array.isArray(res.data) ? res.data : [];
          setStatements(data.filter((s) => !s.finalized));
        })
        .catch((err) => console.error(err));
    };

    fetchData();
    const id = setInterval(fetchData, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="p-4 overflow-y-auto" style={{ maxHeight: "80vh" }}>
      <h1 className="text-2xl font-bold mb-4">Pending Statements</h1>
      {statements.map((st) => (
        <StatementBox key={st.statement_id} stmt={st} />
      ))}
    </div>
  );
}
