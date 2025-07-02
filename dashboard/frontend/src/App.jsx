import React, { useEffect, useState } from "react";
import { BrowserRouter as Router, Routes, Route, Link, useParams } from "react-router-dom";
import axios from "axios";
import EventList from "./components/EventList";
import SubmitStatement from "./SubmitStatement";

const Navbar = ({ totalSupply }) => (
  <nav className="bg-gray-800 p-4 text-white flex justify-between items-center">
    <div className="space-x-4">
      <Link to="/" className="hover:underline">Home</Link>
      <Link to="/events" className="hover:underline">Events</Link>
      <Link to="/submit" className="hover:underline">Submit</Link>
      <Link to="/wallet/1" className="hover:underline">Wallet</Link>
    </div>
    <div>Total HLX: {totalSupply ?? '123.45'}</div>
  </nav>
);

const Home = () => {
  const [statements, setStatements] = useState([]);

  useEffect(() => {
    axios.get("/api/statements?limit=10")
      .then(res => setStatements(res.data))
      .catch(err => console.error(err));
  }, []);

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Latest Statements</h1>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left font-semibold whitespace-nowrap">ID</th>
              <th className="px-4 py-2 text-left font-semibold whitespace-nowrap">Compression %</th>
              <th className="px-4 py-2 text-left font-semibold whitespace-nowrap">Delta Seconds</th>
              <th className="px-4 py-2 text-left font-semibold whitespace-nowrap">Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {statements.map(st => (
              <tr key={st.statement_id}>
                <td className="px-4 py-2 break-all">
                  <Link to={`/statement/${st.statement_id}`} className="text-indigo-600 hover:underline">
                    {st.statement_id}
                  </Link>
                </td>
                <td className="px-4 py-2 whitespace-nowrap">{st.compression_percent}</td>
                <td className="px-4 py-2 whitespace-nowrap">{st.delta_seconds}</td>
                <td className="px-4 py-2 whitespace-nowrap">{st.timestamp}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const Statement = () => {
  const { id } = useParams();
  const [data, setData] = useState(null);

  useEffect(() => {
    axios.get(`/api/statement/${id}`)
      .then(res => setData(res.data))
      .catch(err => console.error(err));
  }, [id]);

  if (!data) return <div className="p-4">Loading...</div>;

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold">Statement {id}</h1>
      <div>Original Size: {data.original_size}</div>
      <div>Compressed Size: {data.compressed_size}</div>
      <pre className="bg-gray-100 p-2 whitespace-pre-wrap">{data.reconstructed}</pre>
      <h2 className="text-xl font-semibold mt-4">Microblocks</h2>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 mt-2">
          <thead className="bg-gray-50">
            <tr>
              <th className="w-16 px-4 py-2 text-left font-semibold whitespace-nowrap">Index</th>
              <th className="px-4 py-2 text-left font-semibold whitespace-nowrap">Original Bytes</th>
              <th className="px-4 py-2 text-left font-semibold whitespace-nowrap">Mined Seed</th>
              <th className="w-28 px-4 py-2 text-left font-semibold whitespace-nowrap">Seed Length</th>
              <th className="px-4 py-2 text-left font-semibold whitespace-nowrap">Miner Wallet</th>
            </tr>
          </thead>
          <tbody>
            {data.microblocks?.map((block, idx) => {
              const seed = data.seeds?.[idx];
              const miner = data.miners?.[idx];
              const seedHex = Array.isArray(seed) ? seed.map(b => b.toString(16).padStart(2, "0")).join("") : seed || "";
              const seedLength = seed ? (Array.isArray(seed) ? seed.length : Math.floor(seed.length / 2)) : 0;
              return (
                <tr key={idx}>
                  <td className="px-4 py-2 whitespace-nowrap">{idx}</td>
                  <td className="px-4 py-2 font-mono break-all">{block}</td>
                  <td className="px-4 py-2 font-mono break-all">{seedHex}</td>
                  <td className="px-4 py-2 whitespace-nowrap">{seedLength}</td>
                  <td className="px-4 py-2 break-all">{miner || ''}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <h2 className="text-xl font-semibold">Miners</h2>
      <ul className="list-disc pl-5">
        {data.miners?.map((miner, idx) => (
          <li key={idx}>{miner} - Seed Length: {data.seed_lengths[idx]}</li>
        ))}
      </ul>
    </div>
  );
};

const Wallet = () => {
  const { walletId } = useParams();
  const [balance, setBalance] = useState(null);

  useEffect(() => {
    axios.get(`/api/balance/${walletId}`)
      .then(res => setBalance(res.data.balance))
      .catch(err => console.error(err));
  }, [walletId]);

  if (balance === null) return <div className="p-4">Loading...</div>;

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold">Wallet {walletId}</h1>
      <div className="mt-2">HLX Balance: {balance}</div>
    </div>
  );
};

export default function App() {
  const [supply, setSupply] = useState(null);

  useEffect(() => {
    axios.get("/api/supply")
      .then(res => setSupply(res.data.total_supply))
      .catch(err => console.error(err));
  }, []);

  return (
    <Router>
      <Navbar totalSupply={supply} />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/events" element={<EventList />} />
        <Route path="/submit" element={<SubmitStatement />} />
        <Route path="/statement/:id" element={<Statement />} />
        <Route path="/wallet/:walletId" element={<Wallet />} />
      </Routes>
    </Router>
  );
}
