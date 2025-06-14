#!/usr/bin/env python3
"""Command-line interface for Helix wallets."""

import argparse
import json

from helix.wallet import create_wallet, load_wallet, send_hlx, sign_with_wallet


def main() -> None:
    parser = argparse.ArgumentParser(description="Helix Wallet CLI")
    sub = parser.add_subparsers(dest="cmd")

    c = sub.add_parser("create-wallet", help="Create a new wallet")
    c.add_argument("wallet_file", help="Path to wallet JSON")
    c.add_argument("--balance", type=int, default=1000, help="Initial HLX balance")

    s = sub.add_parser("show-wallet", help="Display wallet contents")
    s.add_argument("wallet_file")

    t = sub.add_parser("send-hlx", help="Send HLX from one wallet to another")
    t.add_argument("from_wallet")
    t.add_argument("to_wallet")
    t.add_argument("amount", type=int)

    sg = sub.add_parser("sign-data", help="Sign a message with a wallet")
    sg.add_argument("wallet_file")
    sg.add_argument("message")

    args = parser.parse_args()
    if args.cmd == "create-wallet":
        wallet = create_wallet(args.wallet_file, balance=args.balance)
        print(json.dumps(wallet.to_dict(), indent=2))
    elif args.cmd == "show-wallet":
        wallet = load_wallet(args.wallet_file)
        print(json.dumps(wallet.to_dict(), indent=2))
    elif args.cmd == "send-hlx":
        send_hlx(args.from_wallet, args.to_wallet, args.amount)
        print("Transfer complete")
    elif args.cmd == "sign-data":
        signature = sign_with_wallet(args.wallet_file, args.message)
        print(signature)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

