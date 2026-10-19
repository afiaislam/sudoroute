#!/usr/bin/env python3
"""Verify a SudoRoute payment certificate offline (standard library only).

    python scripts/verify_certificate.py "SR1.<claims>.<signature>" <public-key-hex>

The public key is shown on the /verify page and at /api/public/issuer.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sudoroute.security import certificates  # noqa: E402

if len(sys.argv) != 3:
    sys.exit(__doc__)
pub = bytes.fromhex(sys.argv[2])
code = sys.argv[1]
claims = json.loads(certificates.unb64u(code.split(".")[1])) if code.count(".") == 2 else {}
res = certificates.verify(code, {claims.get("kid", ""): pub})
print("VALID" if res["valid"] else f"NOT VALID: {res['reason']}")
if res.get("claims"):
    print(json.dumps(res["claims"], indent=2, ensure_ascii=False))
sys.exit(0 if res["valid"] else 1)
