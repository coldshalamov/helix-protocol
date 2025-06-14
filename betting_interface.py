diff --git a//dev/null b/helix/betting_interface.py
index 0000000000000000000000000000000000000000..451ca100f2b8c1416fd589c893d04267a143c7e3 100644
--- a//dev/null
+++ b/helix/betting_interface.py
@@ -0,0 +1,82 @@
+"""Bet submission and verification utilities for Helix."""
+
+from __future__ import annotations
+
+import json
+from typing import Any, Dict
+
+from .signature_utils import load_keys, sign_data, verify_signature
+
+
+def submit_bet(event_id: str, choice: str, amount: int, keyfile: str) -> Dict[str, Any]:
+    """Return a signed bet for ``event_id`` using keys from ``keyfile``."""
+    if choice not in ("YES", "NO"):
+        raise ValueError("choice must be 'YES' or 'NO'")
+    pub, priv = load_keys(keyfile)
+    payload = {
+        "event_id": event_id,
+        "choice": choice,
+        "amount": amount,
+        "pubkey": pub,
+    }
+    signature = sign_data(repr(payload).encode("utf-8"), priv)
+    bet = payload.copy()
+    bet["signature"] = signature
+    return bet
+
+
+def verify_bet(bet: Dict[str, Any]) -> bool:
+    """Return ``True`` if ``bet`` has a valid structure and signature."""
+    required_fields = {"event_id", "choice", "amount", "pubkey", "signature"}
+    if not required_fields.issubset(bet):
+        return False
+    if bet["choice"] not in ("YES", "NO"):
+        return False
+    payload = {
+        "event_id": bet["event_id"],
+        "choice": bet["choice"],
+        "amount": bet["amount"],
+        "pubkey": bet["pubkey"],
+    }
+    return verify_signature(repr(payload).encode("utf-8"), bet["signature"], bet["pubkey"])
+
+
+def record_bet(event: Dict[str, Any], bet: Dict[str, Any]) -> None:
+    """Append ``bet`` to ``event`` if valid."""
+    if not verify_bet(bet):
+        raise ValueError("Invalid bet or signature")
+    choice = bet["choice"]
+    if "bets" not in event or choice not in event["bets"]:
+        raise ValueError("Event missing bets structure")
+    event["bets"][choice].append(bet)
+
+
+def main() -> None:
+    from .event_manager import create_event
+    from .signature_utils import generate_keypair, save_keys
+
+    # Generate keys for demo and persist to a temporary file
+    pub, priv = generate_keypair()
+    keyfile = "demo_keys.txt"
+    save_keys(keyfile, pub, priv)
+
+    # Create a simple event
+    event = create_event("Demo event for betting")
+    event_id = event["header"]["statement_id"]
+
+    # Submit and record a YES bet
+    bet = submit_bet(event_id, "YES", 100, keyfile)
+    record_bet(event, bet)
+
+    print(json.dumps(event["bets"], indent=2))
+
+
+__all__ = [
+    "submit_bet",
+    "verify_bet",
+    "record_bet",
+]
+
+
+if __name__ == "__main__":
+    main()
