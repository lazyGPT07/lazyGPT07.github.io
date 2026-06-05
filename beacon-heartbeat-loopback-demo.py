#!/usr/bin/env python3
"""
Beacon-style heartbeat loopback demo.

Install:
  python -m pip install pynacl

Run:
  python beacon-heartbeat-loopback-demo.py
"""

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field

from nacl.signing import SigningKey, VerifyKey


def canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def agent_id_from_pubkey(pubkey_hex):
    return "bcn_" + hashlib.sha256(bytes.fromhex(pubkey_hex)).hexdigest()[:12]


@dataclass
class ReplayGuard:
    seen_nonces: set[str] = field(default_factory=set)
    max_skew_seconds: int = 30

    def check(self, envelope):
        now = int(time.time())
        if abs(now - int(envelope["ts"])) > self.max_skew_seconds:
            raise ValueError("TIMESTAMP_STALE")
        if envelope["nonce"] in self.seen_nonces:
            raise ValueError("NONCE_REUSED")
        self.seen_nonces.add(envelope["nonce"])


def sign_heartbeat(signing_key, status="healthy"):
    pubkey_hex = signing_key.verify_key.encode().hex()
    payload = {
        "kind": "heartbeat",
        "status": status,
        "agent_id": agent_id_from_pubkey(pubkey_hex),
        "nonce": secrets.token_hex(8),
        "ts": int(time.time()),
        "pubkey": pubkey_hex,
    }
    payload["sig"] = signing_key.sign(canonical_json(payload)).signature.hex()
    return payload


def verify_envelope(envelope, guard):
    sig = bytes.fromhex(envelope["sig"])
    unsigned = dict(envelope)
    unsigned.pop("sig")
    VerifyKey(bytes.fromhex(envelope["pubkey"])).verify(canonical_json(unsigned), sig)
    expected_agent_id = agent_id_from_pubkey(envelope["pubkey"])
    if envelope["agent_id"] != expected_agent_id:
        raise ValueError("AGENT_ID_MISMATCH")
    guard.check(envelope)
    return True


def main():
    signing_key = SigningKey.generate()
    guard = ReplayGuard()

    heartbeat = sign_heartbeat(signing_key)
    print("[BEACON v2]")
    print(json.dumps(heartbeat, indent=2))
    print("[/BEACON]")

    assert verify_envelope(heartbeat, guard)
    print("verified: heartbeat signature, agent id, timestamp, and nonce")

    try:
        verify_envelope(heartbeat, guard)
    except ValueError as exc:
        print(f"replay blocked: {exc}")

    mayday = sign_heartbeat(signing_key, status="shutting_down")
    mayday["kind"] = "mayday"
    mayday["reason"] = "planned host migration"
    unsigned = dict(mayday)
    unsigned.pop("sig")
    mayday["sig"] = signing_key.sign(canonical_json(unsigned)).signature.hex()
    assert verify_envelope(mayday, guard)
    print("verified: mayday envelope from same agent identity")


if __name__ == "__main__":
    main()
