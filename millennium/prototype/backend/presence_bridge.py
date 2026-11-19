#!/usr/bin/env python3
"""Experimental Steam -> Discord RPC bridge for Linux. Python stdlib only."""
import argparse, json, os, socket, struct, subprocess, sys, time, threading, urllib.parse
from pathlib import Path

STEAM_ROOTS = [Path.home()/'.local/share/Steam', Path.home()/'.steam/steam']

def steam_root():
    for p in STEAM_ROOTS:
        if (p/'userdata').exists() or (p/'steamapps').exists():
            return p
    return STEAM_ROOTS[0]


def vdf_pairs(text):
    import re
    tokens = re.findall(r'"((?:\\.|[^"\\])*)"|([{}])|([^\s{}"]+)', text)
    flat=[]
    for q, brace, bare in tokens:
        flat.append(q.replace('\\"','"').replace('\\\\','\\') if q else (brace or bare))
    def parse(i=0):
        out={}
        while i < len(flat):
            t=flat[i]
            if t=='}': return out,i+1
            if t=='{': i+=1; continue
            key=t; i+=1
            if i>=len(flat): break
            if flat[i]=='{': val,i=parse(i+1)
            else: val=flat[i]; i+=1
            out[key]=val
        return out,i
    return parse()[0]


def shortcuts():
    root=steam_root(); result=[]
    userdata=root/'userdata'
    if not userdata.exists(): return result
    for user in userdata.iterdir():
        f=user/'config'/'shortcuts.vdf'
        if not f.exists(): continue
        try:
            parsed=vdf_pairs(f.read_text(errors='replace'))
            data=parsed.get('shortcuts', parsed)
            if isinstance(data,dict):
                for entry in data.values():
                    if not isinstance(entry,dict): continue
                    name=str(entry.get('AppName','')).strip()
                    exe=str(entry.get('Exe','')).strip().strip('"')
                    appid=str(entry.get('appid','')).strip()
                    if name and exe: result.append({'name':name,'exe':exe,'appid':appid})
        except Exception as e: print('VDF read error:',e,file=sys.stderr)
    return result


def proc_rows():
    rows=[]
    proc=Path('/proc')
    for p in proc.iterdir():
        if not p.name.isdigit(): continue
        try:
            cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace').strip()
            exe=os.path.realpath((p/'exe').resolve())
            if cmd: rows.append((int(p.name),cmd,exe))
        except (OSError,PermissionError): pass
    return rows


def match_game(rows, shortcuts_list):
    for item in shortcuts_list:
        exe=item['exe'].lower()
        for pid,cmd,proc_exe in rows:
            if exe and (exe in cmd.lower() or exe in proc_exe.lower()): return item

    for pid,cmd,exe in rows:
        low=(cmd+' '+exe).lower()
        if any(x in low for x in ('steamwebhelper','steam.exe','steamclient','steam')): continue
        if any(x in low for x in ('proton','wine','pressure-vessel')):
            return {'name':Path(cmd.split()[0]).stem or 'Steam game','exe':cmd.split()[0],'appid':''}
    return None


def rpc_socket():
    uid=os.getuid()
    candidates=[]
    for base in (Path('/run/user')/str(uid), Path('/tmp')):
        if base.exists():
            candidates.extend(base.glob('discord-ipc-*'))
    for p in candidates:
        try:
            s=socket.socket(socket.AF_UNIX,s.SOCK_STREAM); s.connect(str(p)); return s
        except OSError: continue
    return None


def send_frame(sock, opcode, payload):
    body=json.dumps(payload,separators=(',',':')).encode()
    sock.sendall(struct.pack('<II',len(body),opcode)+body)

def read_frame(sock):
    header=sock.recv(8)
    if len(header)!=8: return None
    length,op=struct.unpack('<II',header)
    body=b''
    while len(body)<length:
        chunk=sock.recv(length-len(body))
        if not chunk: break
        body+=chunk
    try:return op,json.loads(body.decode())
    except Exception:return op,body

class DiscordRPC:
    def __init__(self, client_id): self.client_id=client_id; self.sock=None
    def connect(self):
        self.sock=rpc_socket()
        if not self.sock:return False
        send_frame(self.sock,0,{'v':1,'client_id':self.client_id})
        read_frame(self.sock)
        return True
    def activity(self, name, image_url=None):
        if not self.sock and not self.connect(): return False
        assets={}
        if image_url: assets['large_image']=image_url; assets['large_text']=name
        send_frame(self.sock,1,{'cmd':'SET_ACTIVITY','args':{'pid':os.getpid(),'activity':{'details':name,'state':'Steam game','assets':assets,'timestamps':{'start':int(time.time())}}},'nonce':str(time.time_ns())})
        try: read_frame(self.sock)
        except OSError: self.sock=None
        return True
    def clear(self):
        if self.sock:
            try: send_frame(self.sock,1,{'cmd':'SET_ACTIVITY','args':{'pid':os.getpid(),'activity':None},'nonce':str(time.time_ns())}); read_frame(self.sock)
            except OSError: pass
            try:self.sock.close()
            except:pass
            self.sock=None


def main():
    ap=argparse.ArgumentParser(description='Experimental Steam non-Steam shortcut Discord RPC bridge')
    ap.add_argument('--client-id',default='')
    ap.add_argument('--poll',type=float,default=3.0)
    ap.add_argument('--dry-run',action='store_true')
    args=ap.parse_args()
    print('Steam Presence Bridge — experimental Linux prototype')
    if not args.client_id and not args.dry_run:
        print('Set --client-id to your Discord application ID to enable RPC.'); sys.exit(2)
    known=shortcuts(); print(f'Loaded {len(known)} Steam shortcuts; watching processes (Ctrl+C to stop).')
    rpc=DiscordRPC(args.client_id) if args.client_id else None
    current=None
    try:
        while True:
            game=match_game(proc_rows(),known)
            key=(game or {}).get('name') if game else None
            if key!=current:
                if current and rpc: rpc.clear()
                current=key
                if game:
                    print('Detected:',game['name'])
                    if args.dry_run: print('[dry-run] would set Discord activity:',game['name'])
                    elif rpc: rpc.activity(game['name'])
                else: print('No game detected')
            time.sleep(max(1.0,args.poll))
    except KeyboardInterrupt:
        if rpc:rpc.clear()
        print('\nStopped.')
if __name__=='__main__': main()
