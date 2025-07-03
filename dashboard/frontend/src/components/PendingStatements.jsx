import React, { useEffect, useState } from "react";
import axios from "axios";
import ReactModal from "react-modal";

ReactModal.setAppElement("#root");

const quotes = [
  "The unexamined bet is not worth placing.",
  "Reality is that which, when you stop believing in it, does not go away.",
  "The difference between intelligent and unintelligent people is intelligent people can handle subtlety.",
  "A lie gets halfway around the world before the truth has a chance to get its trousers on.",
  "The simple step of a courageous individual is not to take part in the lie. One word of truth outweighs the world.",
  "In a world of secrets, the only certainty is doubt.",
  "The truth is rarely pure and never simple.",
  "Truth is an expensive commodity. That's why the market is full of counterfeits.",
  "We know the truth not only by reason, but by the heart.",
  "In a time of universal deceit, telling the truth is a revolutionary action.",
  "The easiest person to fool is yourself.",
  "Seeking what is true is not seeking what is desirable.",
  "Prefer questions that can't be answered to answers that can't be questioned.",
  "Once a file gets on a computer, it's hard to kill.",
  "Live not by lies.",
  "Let the lie come into the world, let it even triumph. But not through me.",
  "The truth is not learned in safety.",
  "The truth is the most painful thing to tell.",
  "What is real? What is illusion? Sometimes, we cannot tell the difference.",
];


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
  const [voteAmount, setVoteAmount] = useState("");
  const [voteChoice, setVoteChoice] = useState(null);
  const [voteResult, setVoteResult] = useState(null);
  const [voteError, setVoteError] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [pendingVote, setPendingVote] = useState(null); // { choice, amount }
  const [quote, setQuote] = useState("");

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

  const submitVote = async (choice, eventId) => {
    setVoteResult(null);
    setVoteError(null);
    setVoteChoice(choice);
    try {
      const res = await axios.post("/api/vote", {
        wallet_id: "1",
        event_id: eventId,
        amount: parseFloat(voteAmount),
        choice: choice,
      });
      setVoteResult(res.data);
    } catch (err) {
      setVoteError(err.response?.data?.detail || "Vote failed.");
    }
  };

  const handleVoteClick = (choice) => {
    if (!voteAmount || isNaN(parseFloat(voteAmount))) {
      setVoteError("Please enter a valid HLX amount.");
      return;
    }
    const q = quotes[Math.floor(Math.random() * quotes.length)];
    setQuote(q);
    setPendingVote({ choice, amount: parseFloat(voteAmount) });
    setConfirming(true);
  };

  const confirmVote = () => {
    if (pendingVote) {
      submitVote(pendingVote.choice, stmt.statement_id);
    }
    setConfirming(false);
    setPendingVote(null);
  };

  const microblocks = Array.from({ length: totalBlocks }).map((_, i) => ({
    mined: !!seeds.find((s) => s && s.index === i),
  }));
  const eventId = stmt.statement_id;

  return (
    <div className="border shadow p-4 my-4 space-y-2 bg-white rounded">
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

      <div className="flex flex-wrap gap-1">
        {microblocks.map((block, i) => (
          <div
            key={i}
            className={`px-2 py-1 rounded text-sm ${block.mined ? "bg-green-200" : "bg-yellow-200"}`}
          >
            {block.mined ? `✔ Block ${i}` : `⏳ Block ${i}`}
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <label className="font-semibold">Vote:</label>
        <input
          type="number"
          value={voteAmount}
          onChange={(e) => setVoteAmount(e.target.value)}
          className="border px-2 py-1 w-24"
        />
        <button
          className="bg-green-600 text-white px-3 py-1 rounded"
          onClick={() => handleVoteClick("YES")}
        >
          ✅ TRUE
        </button>
        <div className="text-sm">{yesTotal} HLX</div>
        <button
          className="bg-red-600 text-white px-3 py-1 rounded"
          onClick={() => handleVoteClick("NO")}
        >
          ❌ FALSE
        </button>
        <div className="text-sm">{noTotal} HLX</div>
      </div>

      <div className="text-gray-600 text-sm">
        {minedCount} / {blockCount} blocks mined
      </div>

      {voteResult && (
        <div className="text-green-700 text-sm">✅ Vote submitted.</div>
      )}
      {voteError && (
        <div className="text-red-600 text-sm">❌ {voteError}</div>
      )}
      <ReactModal
        isOpen={confirming}
        onRequestClose={() => setConfirming(false)}
        className="bg-white rounded shadow p-6 w-96 mx-auto mt-20"
        overlayClassName="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-start z-50"
      >
        <h2 className="text-xl font-semibold mb-2">Confirm Your Bet</h2>
        <div className="mb-2">
          <div className="text-sm font-medium text-gray-700">Statement:</div>
          <div className="text-sm text-gray-900 whitespace-pre-wrap">{fullText}</div>
        </div>
        <div className="text-sm text-gray-800 my-2">
          You are betting <strong>{pendingVote?.amount} HLX</strong> on{" "}
          <strong>{pendingVote?.choice === "YES" ? "✅ TRUE" : "❌ FALSE"}</strong>.
        </div>
        <blockquote className="italic text-gray-600 border-l-4 pl-2 border-blue-400 mb-4">
          {quote}
        </blockquote>
        <div className="flex justify-end gap-4">
          <button
            className="px-4 py-2 bg-gray-300 text-gray-700 rounded"
            onClick={() => setConfirming(false)}
          >
            Forget it
          </button>
          <button
            className="px-4 py-2 bg-blue-600 text-white rounded"
            onClick={confirmVote}
          >
            I'm certain
          </button>
        </div>
      </ReactModal>
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
