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
  const minedMap = new Map();
  if (Array.isArray(stmt.mined_blocks)) {
    stmt.mined_blocks.forEach(({ index, seed }) => {
      minedMap.set(index, seed);
    });
  }
  const bets = stmt.bets || {};
  const yesBets = bets.TRUE || bets.YES || [];
  const noBets = bets.FALSE || bets.NO || [];
  const yesTotal = Array.isArray(yesBets)
    ? yesBets.reduce((sum, b) => sum + Number(b.amount || 0), 0)
    : Number(yesBets || 0);
  const noTotal = Array.isArray(noBets)
    ? noBets.reduce((sum, b) => sum + Number(b.amount || 0), 0)
    : Number(noBets || 0);

  const blockCount = stmt.microblock_count
    ? stmt.microblock_count
    : Math.ceil(text.length / size);
  const segments = [];
  for (let i = 0; i < blockCount; i++) {
    const start = i * size;
    segments.push(text.slice(start, start + size));
  }

  const minedCount = minedMap.size;

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
            const cls = minedMap.has(i) ? `${color} text-black` : "bg-gray-100";
            return (
              <span key={i} className={`${cls} px-1`}>{seg}</span>
            );
          })}
        </div>
        <div className="flex space-x-1 mt-1 text-xs">
          {segments.map((_, i) => {
            const color = COLORS[i % COLORS.length];
            const seed = minedMap.get(i);
            const isMined = seed !== undefined;
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
