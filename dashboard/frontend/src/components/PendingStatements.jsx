import React, { useEffect, useState } from "react";
import axios from "axios";


function decodeBlock(encoded) {
  try {
    const bin = atob(encoded);
    return Uint8Array.from(bin, (c) => c.charCodeAt(0));
  } catch {
    const bytes = [];
    for (let i = 0; i < encoded.length; i += 2) {
      bytes.push(parseInt(encoded.slice(i, i + 2), 16));
    }
    return Uint8Array.from(bytes);
  }
}

function StatementBox({ stmt }) {
  const seeds = Array.isArray(stmt.seeds)
    ? stmt.seeds
    : Array.isArray(stmt.mined_blocks)
    ? stmt.mined_blocks
    : [];
  const bets = stmt.bets || {};
  const yesTotal = bets.YES || bets.TRUE || stmt.total_yes || 0;
  const noTotal = bets.NO || stmt.total_no || 0;

  let decodedBlocks = [];
  if (Array.isArray(stmt.microblocks)) {
    decodedBlocks = stmt.microblocks.map((b) => decodeBlock(b));
  } else if (stmt.statement) {
    const size = stmt.microblock_size || 1;
    for (let i = 0; i < stmt.statement.length; i += size) {
      decodedBlocks.push(
        Uint8Array.from(stmt.statement.slice(i, i + size), (c) =>
          c.charCodeAt(0)
        )
      );
    }
  }

  const blockSize = decodedBlocks[0] ? decodedBlocks[0].length : 1;
  let payloadBytes = [];
  decodedBlocks.forEach((b) => {
    payloadBytes = payloadBytes.concat(Array.from(b));
  });
  while (payloadBytes.length && payloadBytes[payloadBytes.length - 1] === 0) {
    payloadBytes.pop();
  }
  const textDecoder = new TextDecoder("utf-8", { fatal: false });
  const fullText = textDecoder.decode(Uint8Array.from(payloadBytes));

  const segments = [];
  for (let i = 0; i < fullText.length; i += blockSize) {
    segments.push(fullText.slice(i, i + blockSize));
  }

  const blockCount = stmt.microblock_count || Math.ceil(fullText.length / blockSize);
  const minedCount = Array.isArray(seeds)
    ? seeds.filter((s) => s && s.seed).length
    : 0;

  const totalBlocks = blockCount;
  const statusBar = [];
  for (let i = 0; i < totalBlocks; i++) {
    const seedObj = seeds.find((s) => s && s.index === i);
    statusBar.push(
      <div key={i} className="flex flex-col items-center mb-1">
        <div className={`block-icon w-4 h-4 ${seedObj ? 'bg-green-500' : 'bg-purple-300'}`}></div>
        <div className="seed-label text-[10px] break-all">
          {seedObj ? `seed: b'${seedObj.seed}'` : 'Pending'}
        </div>
      </div>
    );
  }

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
      <div className="flex">
        <div className="flex-1 overflow-x-auto">
          <div className="flex flex-wrap font-mono text-sm">
            {segments.map((seg, i) => (
              <span
                key={i}
                className="px-1 whitespace-pre"
                style={{
                  backgroundColor: i % 2 === 0 ? "#D0F0FF" : "#FFFFFF",
                  color: "#000000",
                }}
              >
                {seg}
              </span>
            ))}
          </div>
        </div>
        <div className="ml-4 flex flex-col items-center">
          {statusBar}
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
