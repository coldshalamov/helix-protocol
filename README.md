# helix-protocol
A decentralized on‑chain oracle protocol for truth verification on Ethereum.
Helix is a fully on-chain oracle system that replaces centralized APIs and unverifiable data feeds with a permissionless staking protocol for resolving truth claims.

Mission: To create a transparent, decentralized, and economically sound oracle layer that secures smart contracts, restores trust in shared facts, and unlocks new forms of public infrastructure in Web3.

⸻

🚨 The Oracle Problem Today

Smart contracts depend on off-chain data to trigger on-chain events. But the current oracle landscape is dominated by:
	•	❌ Centralized APIs and closed data sources
	•	❌ Single points of failure (downtime, DDoS, rugpulls)
	•	❌ Mutable endpoints backing immutable contracts

Helix offers a resilient alternative—a system that verifies real-world claims through game-theoretic staking, not corporate trust.

⸻

🔐 Key Features
	•	🧾 Binary Truth Contracts
Every claim (e.g., “Did ETH close above $2,000 on May 1?”) is deployed as a smart contract with a staking window.
	•	🪙 Staking-Based Consensus
Users stake HELIX tokens on “true” or “false.” The winning side receives rewards; the losing side forfeits their stake.
	•	🕶 Dark Period to Prevent Sniping
In the final 10% of the contract window, the vote tally is hidden to prevent last-minute manipulation.
	•	🧠 Economic Epistemology
Truth becomes a public good—verified not by emotion or authority, but by financial consensus.
	•	💻 Fully On-Chain & Immutable
Once resolved, any dApp can trustlessly query TruthClaim(outcome) with no external dependencies.

⸻

🧱 Protocol Architecture

At its core, Helix uses a binary staking system:
	•	Anyone can post a claim by deploying a TruthClaim.sol contract.
	•	Two visible staking pools (true/false) build over time.
	•	During the final phase, the protocol enters a dark period where stakes are hidden.
	•	After expiry, the majority pool wins and the result is published immutably on-chain.

This allows dApps to securely reference off-chain events with no reliance on oracles, APIs, or trusted third parties.

⸻

🌍 Why It Matters

As misinformation, AI-generated content, and disinformation campaigns rise, Helix offers a scalable model for trust in a decentralized world.

It’s not just a data layer for Ethereum — it’s a proof-of-truth infrastructure for an information-saturated age.

⸻

👷 How to Get Involved

We’re looking for collaborators across disciplines:
	•	Solidity Devs: Build TruthClaim.sol and staking logic
	•	Frontend Engineers: Create UI for submitting, staking, and verifying claims
	•	Protocol Architects: Help refine dark period logic, tokenomics, and L2 design
	•	Researchers: Analyze security and game theory of staked consensus

📄 White Paper: [Add Google Docs or GitHub link here]
📫 Contact: DM Robin Gattis or submit a PR to this repo.

⸻

👤 Project Credits

Lead Author & Concept: Robin Gattis
Inspired by: Varlam Shalamov, Kim Stanley Robinson, Satoshi Nakamoto