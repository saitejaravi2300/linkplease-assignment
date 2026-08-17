"""Apply for the assignment API key.

Usage:
  python scripts/apply_and_key.py --name "Your Name" --email you@example.com --phone +91... --linkedin https://linkedin.com/in/you
"""
import argparse, json, urllib.request

BASE="https://pseudogram-api.onrender.com"

def post(path,payload):
    req=urllib.request.Request(BASE+path,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req) as r:
        return json.load(r)

ap=argparse.ArgumentParser()
ap.add_argument('--name',required=True); ap.add_argument('--email',required=True); ap.add_argument('--phone',required=True); ap.add_argument('--linkedin',required=True); ap.add_argument('--whatsapp')
a=ap.parse_args()
print(post('/v1/apply',{'name':a.name,'email':a.email,'phone':a.phone,'whatsapp':a.whatsapp or a.phone,'linkedin_url':a.linkedin}))
print(post('/v1/keygen',{'email':a.email}))
