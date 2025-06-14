import json
import threading
from typing import Optional

from .betting_interface import submit_bet, record_bet
from .helix_node import HelixNode, GossipMessageType


def run_cli(node: HelixNode, *, keyfile: Optional[str] = None) -> None:
    """Simple interactive CLI for a :class:`HelixNode`."""

    threading.Thread(target=node._message_loop, daemon=True).start()
    while True:
        print("\nHelix CLI")
        print("1. Submit statement")
        print("2. Submit bet")
        print("3. Show balances")
        print("4. Quit")
        choice = input("Select: ").strip()
        if choice == "1":
            statement = input("Statement: ")
            event = node.create_event(statement)
            evt_id = event["header"]["statement_id"]
            node.events[evt_id] = event
            node.save_state()
            node.send_message({"type": GossipMessageType.NEW_STATEMENT, "event": event})
            threading.Thread(target=node.mine_event, args=(event,)).start()
        elif choice == "2":
            evt_id = input("Event ID: ")
            bet_choice = input("Bet YES/NO: ").strip().upper()
            amount = int(input("Amount: "))
            if keyfile is None:
                keyfile = input("Keyfile path: ")
            bet = submit_bet(evt_id, bet_choice, amount, keyfile)
            if evt_id in node.events:
                record_bet(node.events[evt_id], bet)
            else:
                print("Unknown event")
        elif choice == "3":
            print(json.dumps(node.balances, indent=2))
        elif choice == "4":
            break
        else:
            print("Invalid choice")

__all__ = ["run_cli"]
