"""Generate a PseudoGram webhook signature for local testing."""
import argparse, hashlib, hmac
p=argparse.ArgumentParser(); p.add_argument('--secret',required=True); p.add_argument('--body',required=True); a=p.parse_args()
print('sha256='+hmac.new(a.secret.encode(),a.body.encode(),hashlib.sha256).hexdigest())
