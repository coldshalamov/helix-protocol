import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useParams } from 'react-router-dom';
import axios from 'axios';
import './index.css';

const Navbar = () => (
  <nav className="bg-gray-800 p-4 text-white flex space-x-4">
    <Link to="/" className="hover:underline">Home</Link>
    <Link to="/wallet/1" className="hover:underline">Wallet</Link>
  </nav>
);

const Home = () => {
  const [statements, setStatements] = useState([]);

  useEffect(() => {
    axios.get('http://localhost:8000/api/statements?limit=10')
      .then(res => setStatements(res.data))
      .catch(err => console.error(err));
  }, []);

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Latest Statements</h1>
      <table className="min-w-full divide-y divide-gray-200">
        <thead>
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ID</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Compression %</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Delta Seconds</th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Timestamp</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {statements.map(st => (
            <tr key={st.statement_id} className="hover:bg-gray-100">
              <td className="px-6 py-4 whitespace-nowrap">
                <Link to={`/statement/${st.statement_id}`} className="text-indigo-600 hover:underline">
                  {st.statement_id}
                </Link>
              </td>
              <td className="px-6 py-4 whitespace-nowrap">{st.compression_percent}</td>
              <td className="px-6 py-4 whitespace-nowrap">{st.delta_seconds}</td>
              <td className="px-6 py-4 whitespace-nowrap">{st.timestamp}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
      <div>
        <h2 className="text-xl font-semibold mt-4">Microblocks</h2>
        <table className="min-w-full divide-y divide-gray-200 mt-2">
          <thead>
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Index</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Original Bytes</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Mined Seed</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Seed Length</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Miner Wallet</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {data.microblocks && data.microblocks.map((block, idx) => {
              const seeds = data.seeds || [];
              const miners = data.miners || [];
              const seed = seeds[idx];
              const seedHex = Array.isArray(seed)
                ? seed.map((b) => b.toString(16).padStart(2, "0")).join("")
                : seed || "";
              const seedLength = seed
                ? Array.isArray(seed)
                  ? seed.length
                  : Math.floor(seed.length / 2)
                : 0;
              return (
                <tr key={idx} className="hover:bg-gray-50">
                  <td className="px-4 py-2 whitespace-nowrap">{idx}</td>
                  <td className="px-4 py-2 whitespace-nowrap font-mono">{block}</td>
                  <td className="px-4 py-2 whitespace-nowrap font-mono">{seedHex}</td>
                  <td className="px-4 py-2 whitespace-nowrap">{seedLength}</td>
                  <td className="px-4 py-2 whitespace-nowrap">{miners[idx] || ''}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div>
        <h2 className="text-xl font-semibold">Miners</h2>
        <ul className="list-disc pl-5">
          {data.miners && data.miners.map((miner, idx) => (
            <li key={idx}>{miner} - Seed Length: {data.seed_lengths[idx]}</li>
          ))}
        </ul>
      </div>
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

const App = () => (
  <Router>
    <Navbar />
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/statement/:id" element={<Statement />} />
      <Route path="/wallet/:walletId" element={<Wallet />} />
    </Routes>
  </Router>
);

export default App;
