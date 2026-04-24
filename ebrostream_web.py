#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EbroStream Web Server - Version Autonome
Fichier indépendant - À copier et exécuter n'importe où

Utilisation:
    python3 ebrostream_web.py
    python3 ebrostream_web.py --port 9090
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import sys
import uuid
import re
from urllib.parse import urlparse

# ==================== CONFIGURATION ====================
DEFAULT_PORT = 8088

# Chemins des fichiers (indépendants)
CONFIG_DIR = "/etc/enigma2/EbroStream"
CCCAM_FILE = "/etc/tuxbox/config/CCcam.cfg"
OSCAM_FILE = "/etc/tuxbox/config/oscam.server"
SERVERS_FILE = os.path.join(CONFIG_DIR, "servers.json")

# Créer les répertoires si nécessaire (avec gestion d'erreur)
try:
    os.makedirs(CONFIG_DIR, exist_ok=True)
except:
    pass
try:
    os.makedirs(os.path.dirname(CCCAM_FILE), exist_ok=True)
except:
    pass


class EbroStreamHandler(BaseHTTPRequestHandler):
    """Gestionnaire API complet"""

    def _send_json(self, code, data):
        response = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(response)

    def _send_html(self, content):
        encoded = content.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/servers':
            self._get_servers()
        elif path == '/api/lines':
            self._get_lines()
        elif path.startswith('/api/servers/'):
            self._get_server_by_id(path.split('/')[-1])
        elif path.startswith('/api/lines/'):
            self._get_line_by_id(path.split('/')[-1])
        elif path == '/' or path == '':
            self._serve_web()
        else:
            self._send_json(404, {"error": f"Route non trouvée: {path}"})

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        data = self._parse_body(content_length)

        if self.path == '/api/servers':
            self._add_server(data)
        elif self.path == '/api/lines':
            self._add_line(data)
        else:
            self._send_json(404, {"error": "Route non trouvée"})

    def do_PUT(self):
        content_length = int(self.headers.get('Content-Length', 0))
        data = self._parse_body(content_length)

        if self.path.startswith('/api/servers/'):
            self._update_server(self.path.split('/')[-1], data)
        elif self.path.startswith('/api/lines/'):
            self._update_line(self.path.split('/')[-1], data)
        else:
            self._send_json(404, {"error": "Route non trouvée"})

    def do_DELETE(self):
        if self.path.startswith('/api/servers/'):
            self._delete_server(self.path.split('/')[-1])
        elif self.path.startswith('/api/lines/'):
            self._delete_line(self.path.split('/')[-1])
        else:
            self._send_json(404, {"error": "Route non trouvée"})

    def _parse_body(self, length):
        try:
            data = self.rfile.read(length).decode('utf-8') if length > 0 else '{}'
            return json.loads(data) if data else {}
        except:
            return {}

    # ==================== SERVEURS ====================

    def _get_servers(self):
        try:
            servers = self._load_servers()
            for s in servers:
                if 'password' in s:
                    s['password'] = '********'
            self._send_json(200, {"success": True, "servers": servers, "total": len(servers)})
        except Exception as e:
            self._send_json(500, {"success": False, "error": str(e)})

    def _get_server_by_id(self, sid):
        servers = self._load_servers()
        server = next((s for s in servers if s.get('id') == sid), None)
        if server:
            self._send_json(200, {"success": True, "server": server})
        else:
            self._send_json(404, {"success": False, "error": "Serveur non trouvé"})

    def _add_server(self, data):
        errors = []
        stype = data.get('type', 'stalker')
        name = data.get('name', '').strip()
        host = data.get('host', '').strip()

        if not name:
            errors.append("Nom requis")
        if not host:
            errors.append("URL requise")

        if stype == 'stalker':
            mac = data.get('mac', '').strip()
            if not mac:
                errors.append("MAC requise")
        else:
            if not data.get('username', '').strip():
                errors.append("Username requis")
            if not data.get('password', '').strip():
                errors.append("Password requis")

        if errors:
            self._send_json(400, {"success": False, "errors": errors})
            return

        server = {
            "id": str(uuid.uuid4())[:8],
            "type": stype,
            "name": name,
            "host": host.rstrip('/'),
            "active": data.get('active', False)
        }

        if stype == 'stalker':
            server["mac"] = self._format_mac(data.get('mac', ''))
        else:
            server["username"] = data.get('username', '').strip()
            server["password"] = data.get('password', '').strip()

        if server['active']:
            self._deactivate_all_servers()

        servers = self._load_servers()
        servers.append(server)

        if self._save_servers(servers):
            resp = server.copy()
            if 'password' in resp:
                resp['password'] = '********'
            self._send_json(201, {"success": True, "message": f"Serveur '{name}' ajouté", "server": resp})
        else:
            self._send_json(500, {"success": False, "error": "Erreur sauvegarde"})

    def _update_server(self, sid, data):
        servers = self._load_servers()
        idx = next((i for i, s in enumerate(servers) if s.get('id') == sid), None)
        if idx is None:
            self._send_json(404, {"success": False, "error": "Serveur non trouvé"})
            return

        server = servers[idx]
        old_active = server.get('active', False)

        if 'name' in data and data['name']:
            server['name'] = data['name'].strip()
        if 'host' in data and data['host']:
            server['host'] = data['host'].strip().rstrip('/')
        if 'active' in data:
            server['active'] = data['active']

        if server['type'] == 'stalker' and 'mac' in data and data['mac']:
            server['mac'] = self._format_mac(data['mac'])
        elif server['type'] != 'stalker':
            if 'username' in data and data['username']:
                server['username'] = data['username'].strip()
            if 'password' in data and data['password'] and data['password'] != '********':
                server['password'] = data['password'].strip()

        if server.get('active', False) and not old_active:
            for i, s in enumerate(servers):
                if i != idx:
                    s['active'] = False

        if self._save_servers(servers):
            resp = server.copy()
            if 'password' in resp:
                resp['password'] = '********'
            self._send_json(200, {"success": True, "message": "Serveur mis à jour", "server": resp})
        else:
            self._send_json(500, {"success": False, "error": "Erreur sauvegarde"})

    def _delete_server(self, sid):
        servers = self._load_servers()
        to_delete = next((s for s in servers if s.get('id') == sid), None)
        if not to_delete:
            self._send_json(404, {"success": False, "error": "Serveur non trouvé"})
            return

        new_servers = [s for s in servers if s.get('id') != sid]
        if self._save_servers(new_servers):
            self._send_json(200, {"success": True, "message": f"Serveur '{to_delete.get('name')}' supprimé"})
        else:
            self._send_json(500, {"success": False, "error": "Erreur suppression"})

    def _load_servers(self):
        if not os.path.exists(SERVERS_FILE):
            self._save_servers([])
            return []
        try:
            with open(SERVERS_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'servers' in data:
                    return data['servers']
                elif isinstance(data, list):
                    return data
                return []
        except:
            return []

    def _save_servers(self, servers):
        try:
            with open(SERVERS_FILE, 'w') as f:
                json.dump({"version": "2.0", "servers": servers, "total": len(servers)}, f, indent=2)
            return True
        except:
            return False

    def _deactivate_all_servers(self):
        servers = self._load_servers()
        for s in servers:
            s['active'] = False
        self._save_servers(servers)

    def _format_mac(self, mac):
        if not mac:
            return "00:00:00:00:00:00"
        mac = ''.join(c for c in mac.strip().upper() if c.isalnum())
        mac = (mac + '0' * 12)[:12]
        return ':'.join(mac[i:i+2] for i in range(0, 12, 2))

    # ==================== LIGNES ====================

    def _get_lines(self):
        try:
            lines = self._load_lines()
            for l in lines:
                if 'password' in l:
                    l['password'] = '********'
            self._send_json(200, {"success": True, "lines": lines, "total": len(lines)})
        except Exception as e:
            self._send_json(500, {"success": False, "error": str(e)})

    def _get_line_by_id(self, lid):
        lines = self._load_lines()
        line = next((l for l in lines if l.get('id') == lid), None)
        if line:
            self._send_json(200, {"success": True, "line": line})
        else:
            self._send_json(404, {"success": False, "error": "Ligne non trouvée"})

    def _add_line(self, data):
        errors = []
        ltype = data.get('type', 'cccam')
        host = data.get('host', '').strip()
        port = data.get('port', '').strip()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not host:
            errors.append("Hôte requis")
        if not port:
            errors.append("Port requis")
        if not username:
            errors.append("Username requis")
        if not password:
            errors.append("Password requis")

        if errors:
            self._send_json(400, {"success": False, "errors": errors})
            return

        line = {
            "id": str(uuid.uuid4())[:8],
            "type": ltype,
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "active": data.get('active', True)
        }

        lines = self._load_lines()
        lines.append(line)

        if self._save_lines(lines):
            self._send_json(201, {"success": True, "message": f"Ligne {host}:{port} ajoutée", "line": line})
        else:
            self._send_json(500, {"success": False, "error": "Erreur sauvegarde"})

    def _update_line(self, lid, data):
        lines = self._load_lines()
        idx = next((i for i, l in enumerate(lines) if l.get('id') == lid), None)
        if idx is None:
            self._send_json(404, {"success": False, "error": "Ligne non trouvée"})
            return

        line = lines[idx]
        if 'host' in data and data['host']:
            line['host'] = data['host'].strip()
        if 'port' in data and data['port']:
            line['port'] = data['port'].strip()
        if 'username' in data and data['username']:
            line['username'] = data['username'].strip()
        if 'password' in data and data['password'] and data['password'] != '********':
            line['password'] = data['password'].strip()
        if 'active' in data:
            line['active'] = data['active']

        if self._save_lines(lines):
            resp = line.copy()
            if 'password' in resp:
                resp['password'] = '********'
            self._send_json(200, {"success": True, "message": "Ligne mise à jour", "line": resp})
        else:
            self._send_json(500, {"success": False, "error": "Erreur sauvegarde"})

    def _delete_line(self, lid):
        lines = self._load_lines()
        to_delete = next((l for l in lines if l.get('id') == lid), None)
        if not to_delete:
            self._send_json(404, {"success": False, "error": "Ligne non trouvée"})
            return

        new_lines = [l for l in lines if l.get('id') != lid]
        if self._save_lines(new_lines):
            self._send_json(200, {"success": True, "message": f"Ligne {to_delete.get('host')}:{to_delete.get('port')} supprimée"})
        else:
            self._send_json(500, {"success": False, "error": "Erreur suppression"})

    def _load_lines(self):
        lines = []

        # Lire CCcam.cfg
        if os.path.exists(CCCAM_FILE):
            try:
                with open(CCCAM_FILE, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('C:'):
                            parts = line.split()
                            if len(parts) >= 5:
                                lines.append({
                                    "id": str(uuid.uuid4())[:8],
                                    "type": "cccam",
                                    "host": parts[1],
                                    "port": parts[2],
                                    "username": parts[3],
                                    "password": parts[4],
                                    "active": not line.startswith('#'),
                                    "raw": line
                                })
            except:
                pass

        # Lire oscam.server
        if os.path.exists(OSCAM_FILE):
            try:
                current = {}
                in_reader = False
                with open(OSCAM_FILE, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('[reader]'):
                            if in_reader and current.get('device') and current.get('account'):
                                device = current['device'].replace(' ', '').split(',')
                                if len(device) >= 2:
                                    lines.append({
                                        "id": str(uuid.uuid4())[:8],
                                        "type": "oscam",
                                        "host": device[0],
                                        "port": device[1],
                                        "username": current.get('account', ''),
                                        "password": current.get('password', ''),
                                        "active": current.get('enable') != '0'
                                    })
                            current = {}
                            in_reader = True
                        elif in_reader and '=' in line:
                            k, v = line.split('=', 1)
                            current[k.strip()] = v.strip()
                # Dernier reader
                if in_reader and current.get('device') and current.get('account'):
                    device = current['device'].replace(' ', '').split(',')
                    if len(device) >= 2:
                        lines.append({
                            "id": str(uuid.uuid4())[:8],
                            "type": "oscam",
                            "host": device[0],
                            "port": device[1],
                            "username": current.get('account', ''),
                            "password": current.get('password', ''),
                            "active": current.get('enable') != '0'
                        })
            except:
                pass

        return lines

    def _save_lines(self, lines):
        try:
            cccam = [l for l in lines if l.get('type') == 'cccam']
            oscam = [l for l in lines if l.get('type') == 'oscam']

            # Sauvegarder CCcam.cfg
            if cccam:
                with open(CCCAM_FILE, 'w') as f:
                    f.write("# Generated by EbroStream\n\n")
                    for l in cccam:
                        if l.get('active', True):
                            f.write(f"C: {l['host']} {l['port']} {l['username']} {l['password']}\n")
                        else:
                            f.write(f"# C: {l['host']} {l['port']} {l['username']} {l['password']}\n")

            # Sauvegarder oscam.server
            if oscam:
                with open(OSCAM_FILE, 'w') as f:
                    f.write("# Generated by EbroStream\n\n")
                    for i, l in enumerate(oscam):
                        if l.get('active', True):
                            f.write(f"[reader]\n")
                            f.write(f"label = ebrostream_{i+1}\n")
                            f.write(f"enable = 1\n")
                            f.write(f"protocol = cccam\n")
                            f.write(f"device = {l['host']},{l['port']}\n")
                            f.write(f"account = {l['username']}\n")
                            f.write(f"password = {l['password']}\n")
                            f.write(f"cccversion = 2.0.11\n")
                            f.write(f"cccmaxhops = 3\n")
                            f.write(f"group = 1\n")
                            f.write(f"inactivitytimeout = 1\n")
                            f.write(f"reconnecttimeout = 30\n")
                            f.write(f"keepalive = 1\n\n")
                        else:
                            f.write(f"# [reader] - disabled\n")
                            f.write(f"# label = ebrostream_{i+1}\n")
                            f.write(f"# enable = 0\n")
                            f.write(f"# device = {l['host']},{l['port']}\n\n")

            return True
        except:
            return False

    # ==================== INTERFACE ====================

    def _serve_web(self):
        self._send_html(HTML_TEMPLATE)

    def log_message(self, fmt, *args):
        pass


# ==================== HTML TEMPLATE ====================
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EbroStream - Gestion IPTV + Softcam</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; font-family:system-ui, 'Segoe UI', Roboto, sans-serif; }
        body { background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%); min-height:100vh; padding:20px; }
        .container { max-width:1400px; margin:0 auto; }
        .tabs-main { display:flex; gap:12px; margin-bottom:28px; flex-wrap:wrap; }
        .tab-main { padding:12px 28px; background:rgba(255,255,255,0.08); border-radius:50px; cursor:pointer; font-weight:600; backdrop-filter:blur(10px); }
        .tab-main.active { background:#3b82f6; box-shadow:0 4px 15px rgba(59,130,246,0.4); }
        .panel { display:none; }
        .panel.active { display:block; }
        .card { background:rgba(255,255,255,0.08); backdrop-filter:blur(10px); border-radius:24px; border:1px solid rgba(255,255,255,0.12); margin-bottom:24px; }
        .card-header { padding:18px 24px; border-bottom:1px solid rgba(255,255,255,0.1); background:rgba(0,0,0,0.2); }
        .card-header h2 { font-size:1.3rem; font-weight:600; color:#fff; }
        .card-body { padding:20px 24px; }
        .stats { display:flex; gap:16px; margin-bottom:24px; flex-wrap:wrap; }
        .stat { background:rgba(255,255,255,0.05); border-radius:16px; padding:12px 24px; text-align:center; flex:1; min-width:120px; }
        .stat-value { font-size:1.8rem; font-weight:700; color:#60efff; }
        .stat-label { color:#a8b2d1; font-size:0.8rem; margin-top:4px; }
        .form-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px,1fr)); gap:20px; }
        .form-group { margin-bottom:16px; }
        label { display:block; margin-bottom:6px; color:#cbd5e1; font-size:0.85rem; font-weight:500; }
        input { width:100%; padding:10px 14px; background:rgba(0,0,0,0.45); border:1px solid rgba(255,255,255,0.15); border-radius:12px; color:white; font-size:0.9rem; }
        input:focus { outline:none; border-color:#60efff; }
        .checkbox-row { display:flex; align-items:center; gap:10px; margin-top:16px; }
        .checkbox-row input { width:auto; margin:0; }
        .btn { padding:10px 24px; border:none; border-radius:40px; font-weight:600; font-size:0.85rem; cursor:pointer; transition:0.2s; }
        .btn-primary { background:#3b82f6; color:white; }
        .btn-primary:hover { background:#2563eb; }
        .btn-success { background:#10b981; color:white; }
        .btn-success:hover { background:#059669; }
        .btn-warning { background:#f59e0b; color:white; }
        .btn-warning:hover { background:#d97706; }
        .btn-danger { background:#ef4444; color:white; }
        .btn-danger:hover { background:#dc2626; }
        .btn-purple { background:#8b5cf6; color:white; }
        .btn-purple:hover { background:#7c3aed; }
        .btn-sm { padding:5px 12px; font-size:0.75rem; }
        .items-list { display:flex; flex-direction:column; gap:12px; }
        .item-card { background:rgba(0,0,0,0.35); border-radius:16px; padding:14px 18px; border-left:4px solid; }
        .item-card.stalker { border-left-color:#3b82f6; }
        .item-card.xtream { border-left-color:#10b981; }
        .item-card.cccam { border-left-color:#f59e0b; }
        .item-card.oscam { border-left-color:#8b5cf6; }
        .item-header { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:8px; }
        .item-title { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
        .item-name { font-size:1rem; font-weight:600; color:white; }
        .badge { padding:3px 10px; border-radius:20px; font-size:0.65rem; font-weight:600; }
        .badge-active { background:rgba(16,185,129,0.25); color:#34d399; }
        .badge-inactive { background:rgba(156,163,175,0.2); color:#9ca3af; }
        .item-details { font-size:0.75rem; color:#9ca3af; margin:8px 0; line-height:1.5; }
        .item-actions { display:flex; gap:8px; margin-top:10px; flex-wrap:wrap; }
        .alert { position:fixed; bottom:20px; right:20px; max-width:380px; background:#1e293b; border-left:4px solid; padding:12px 18px; border-radius:14px; color:white; z-index:1000; opacity:0; transition:0.3s; pointer-events:none; font-size:0.85rem; }
        .alert.show { opacity:1; }
        .alert.success { border-left-color:#10b981; }
        .alert.error { border-left-color:#ef4444; }
        .loading { text-align:center; padding:30px; color:#94a3b8; }
        .modal { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.7); align-items:center; justify-content:center; z-index:1001; }
        .modal.open { display:flex; }
        .modal-content { background:#1e1b4b; border-radius:24px; width:90%; max-width:480px; padding:24px; border:1px solid rgba(255,255,255,0.1); }
        .modal-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
        .modal-close { background:none; border:none; color:#cbd5e1; font-size:1.3rem; cursor:pointer; }
        hr { border-color:rgba(255,255,255,0.08); margin:16px 0; }
        .tab-sub { padding:8px 20px; background:rgba(255,255,255,0.05); border-radius:30px; cursor:pointer; display:inline-block; }
        .tab-sub.active { background:#3b82f6; }
        .form-panel-sub { display:none; }
        .form-panel-sub.active { display:block; }
        @media (max-width:700px){ .form-grid { grid-template-columns:1fr; } }
    </style>
</head>
<body>
<div class="container">
    <div class="tabs-main">
        <div class="tab-main active" data-panel="servers">📡 Serveurs IPTV</div>
        <div class="tab-main" data-panel="lines">🔑 Lignes Softcam</div>
    </div>

    <!-- Panel Serveurs -->
    <div id="panelServers" class="panel active">
        <div class="card">
            <div class="card-header"><h2>📺 Gestion des serveurs IPTV</h2></div>
            <div class="card-body">
                <div class="stats">
                    <div class="stat"><div class="stat-value" id="totalServers">0</div><div class="stat-label">Serveurs</div></div>
                    <div class="stat"><div class="stat-value" id="activeServers">0</div><div class="stat-label">Actifs</div></div>
                </div>
                <div style="display:flex; gap:8px; margin-bottom:20px;">
                    <div class="tab-sub active" data-sub="stalker" style="cursor:pointer;">📡 Stalker</div>
                    <div class="tab-sub" data-sub="xtream" style="cursor:pointer;">⚡ Xtream</div>
                </div>
                <div id="formStalker" class="form-panel-sub active">
                    <div class="form-grid">
                        <div><label>📛 Nom</label><input type="text" id="stalkerName" placeholder="Mon serveur"></div>
                        <div><label>🌐 URL</label><input type="text" id="stalkerHost" placeholder="http://ip:port/c/"></div>
                        <div><label>🔑 MAC</label><input type="text" id="stalkerMac" placeholder="00:1A:79:00:00:00"></div>
                        <div class="checkbox-row"><input type="checkbox" id="stalkerActive"> <label>✅ Actif</label></div>
                    </div>
                    <button class="btn btn-primary" onclick="addServer('stalker')">➕ Ajouter serveur Stalker</button>
                </div>
                <div id="formXtream" class="form-panel-sub">
                    <div class="form-grid">
                        <div><label>📛 Nom</label><input type="text" id="xtreamName" placeholder="Serveur Xtream"></div>
                        <div><label>🌐 URL</label><input type="text" id="xtreamHost" placeholder="http://ip:port"></div>
                        <div><label>👤 Username</label><input type="text" id="xtreamUser" placeholder="username"></div>
                        <div><label>🔒 Password</label><input type="password" id="xtreamPass" placeholder="password"></div>
                        <div class="checkbox-row"><input type="checkbox" id="xtreamActive"> <label>✅ Actif</label></div>
                    </div>
                    <button class="btn btn-success" onclick="addServer('xtream')">⚡ Ajouter serveur Xtream</button>
                </div>
                <hr>
                <h3 style="margin:16px 0; color:#cbd5e1;">📋 Liste des serveurs</h3>
                <div id="serversList"><div class="loading">⏳ Chargement...</div></div>
            </div>
        </div>
    </div>

    <!-- Panel Lignes -->
    <div id="panelLines" class="panel">
        <div class="card">
            <div class="card-header"><h2>🔑 Gestion des lignes Softcam</h2></div>
            <div class="card-body">
                <div class="stats">
                    <div class="stat"><div class="stat-value" id="totalLines">0</div><div class="stat-label">Lignes</div></div>
                </div>
                <div style="display:flex; gap:8px; margin-bottom:20px;">
                    <div class="tab-sub active" data-line="cccam" style="cursor:pointer;">📡 CCcam (C:)</div>
                    <div class="tab-sub" data-line="oscam" style="cursor:pointer;">⚙️ Oscam</div>
                </div>
                <div id="formCccam" class="form-panel-sub active">
                    <div class="form-grid">
                        <div><label>🌐 Hôte</label><input type="text" id="cccamHost" placeholder="server.dyndns.org"></div>
                        <div><label>🔌 Port</label><input type="text" id="cccamPort" placeholder="12000"></div>
                        <div><label>👤 Utilisateur</label><input type="text" id="cccamUser" placeholder="username"></div>
                        <div><label>🔒 Mot de passe</label><input type="password" id="cccamPass" placeholder="password"></div>
                        <div class="checkbox-row"><input type="checkbox" id="cccamActive" checked> <label>✅ Activer</label></div>
                    </div>
                    <button class="btn btn-warning" onclick="addLine('cccam')">➕ Ajouter ligne CCcam</button>
                </div>
                <div id="formOscam" class="form-panel-sub">
                    <div class="form-grid">
                        <div><label>🌐 Hôte</label><input type="text" id="oscamHost" placeholder="server.dyndns.org"></div>
                        <div><label>🔌 Port</label><input type="text" id="oscamPort" placeholder="12000"></div>
                        <div><label>👤 Utilisateur</label><input type="text" id="oscamUser" placeholder="username"></div>
                        <div><label>🔒 Mot de passe</label><input type="password" id="oscamPass" placeholder="password"></div>
                        <div class="checkbox-row"><input type="checkbox" id="oscamActive" checked> <label>✅ Activer</label></div>
                    </div>
                    <button class="btn btn-purple" onclick="addLine('oscam')">➕ Ajouter ligne Oscam</button>
                </div>
                <hr>
                <h3 style="margin:16px 0; color:#cbd5e1;">📋 Liste des lignes</h3>
                <div id="linesList"><div class="loading">⏳ Chargement...</div></div>
            </div>
        </div>
    </div>
</div>

<div id="toast" class="alert"></div>

<!-- Modal Édition Ligne -->
<div id="editLineModal" class="modal">
    <div class="modal-content">
        <div class="modal-header"><h3 style="color:white;">✏️ Modifier la ligne</h3><button class="modal-close" onclick="closeLineModal()">✕</button></div>
        <input type="hidden" id="editLineId"><input type="hidden" id="editLineType">
        <div><label>🌐 Hôte</label><input type="text" id="editLineHost"></div>
        <div style="margin-top:12px;"><label>🔌 Port</label><input type="text" id="editLinePort"></div>
        <div style="margin-top:12px;"><label>👤 Utilisateur</label><input type="text" id="editLineUser"></div>
        <div style="margin-top:12px;"><label>🔒 Mot de passe</label><input type="password" id="editLinePass" placeholder="Laisser vide = inchangé"></div>
        <div class="checkbox-row"><input type="checkbox" id="editLineActive"> <label>✅ Actif</label></div>
        <div style="display:flex; gap:12px; margin-top:24px; justify-content:flex-end;">
            <button class="btn" style="background:#334155;" onclick="closeLineModal()">Annuler</button>
            <button class="btn btn-purple" onclick="saveLineEdit()">💾 Enregistrer</button>
        </div>
    </div>
</div>

<script>
    // Tabs principaux
    document.querySelectorAll('.tab-main').forEach(t => {
        t.onclick = () => {
            document.querySelectorAll('.tab-main').forEach(x => x.classList.remove('active'));
            t.classList.add('active');
            const p = t.dataset.panel;
            document.getElementById('panelServers').classList.toggle('active', p === 'servers');
            document.getElementById('panelLines').classList.toggle('active', p === 'lines');
            if(p === 'servers') loadServers();
            else loadLines();
        };
    });
    // Sous-tabs serveurs
    document.querySelectorAll('[data-sub="stalker"],[data-sub="xtream"]').forEach(t => {
        t.onclick = () => {
            document.querySelectorAll('[data-sub]').forEach(x => x.classList.remove('active'));
            t.classList.add('active');
            document.getElementById('formStalker').classList.toggle('active', t.dataset.sub === 'stalker');
            document.getElementById('formXtream').classList.toggle('active', t.dataset.sub === 'xtream');
        };
    });
    // Tabs lignes
    document.querySelectorAll('[data-line]').forEach(t => {
        t.onclick = () => {
            document.querySelectorAll('[data-line]').forEach(x => x.classList.remove('active'));
            t.classList.add('active');
            document.getElementById('formCccam').classList.toggle('active', t.dataset.line === 'cccam');
            document.getElementById('formOscam').classList.toggle('active', t.dataset.line === 'oscam');
        };
    });

    function showToast(msg, type='success') {
        const t = document.getElementById('toast');
        t.textContent = msg;
        t.className = `alert ${type} show`;
        setTimeout(() => t.classList.remove('show'), 3500);
    }
    function escapeHtml(s) { if(!s) return ''; return s.replace(/[&<>]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[m])); }

    async function loadServers() {
        try {
            const res = await fetch('/api/servers');
            const d = await res.json();
            if(d.success) {
                renderServers(d.servers);
                document.getElementById('totalServers').innerText = d.servers.length;
                document.getElementById('activeServers').innerText = d.servers.filter(s=>s.active).length;
            }
        } catch(e) { document.getElementById('serversList').innerHTML = '<div class="loading">❌ Erreur</div>'; }
    }
    function renderServers(servers) {
        const c = document.getElementById('serversList');
        if(!servers.length) { c.innerHTML = '<div class="loading">📭 Aucun serveur</div>'; return; }
        c.innerHTML = servers.map(s => `
            <div class="item-card ${s.type === 'stalker' ? 'stalker' : 'xtream'}">
                <div class="item-header"><div class="item-title"><span class="item-name">${escapeHtml(s.name)}</span><span class="badge ${s.active ? 'badge-active' : 'badge-inactive'}">${s.active ? 'ACTIF' : 'INACTIF'}</span></div></div>
                <div class="item-details">${s.type === 'stalker' ? `🌐 ${escapeHtml(s.host)}<br>🔑 MAC: ${escapeHtml(s.mac)}` : `🌐 ${escapeHtml(s.host)}<br>👤 User: ${escapeHtml(s.username)}`}</div>
                <div class="item-actions"><button class="btn btn-sm ${s.active ? 'btn-warning' : 'btn-success'}" onclick="toggleActive('${s.id}', ${!s.active})">${s.active ? '⏸️ Désactiver' : '▶️ Activer'}</button><button class="btn btn-sm btn-danger" onclick="deleteServer('${s.id}', '${escapeHtml(s.name)}')">🗑️ Supprimer</button></div>
            </div>`).join('');
    }
    async function addServer(type) {
        let p = { type };
        if(type === 'stalker') {
            p.name = document.getElementById('stalkerName').value.trim();
            p.host = document.getElementById('stalkerHost').value.trim();
            p.mac = document.getElementById('stalkerMac').value.trim();
            p.active = document.getElementById('stalkerActive').checked;
            if(!p.name || !p.host || !p.mac) { showToast('Tous les champs requis', 'error'); return; }
        } else {
            p.name = document.getElementById('xtreamName').value.trim();
            p.host = document.getElementById('xtreamHost').value.trim();
            p.username = document.getElementById('xtreamUser').value.trim();
            p.password = document.getElementById('xtreamPass').value.trim();
            p.active = document.getElementById('xtreamActive').checked;
            if(!p.name || !p.host || !p.username || !p.password) { showToast('Tous les champs requis', 'error'); return; }
        }
        try {
            const res = await fetch('/api/servers', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p) });
            const d = await res.json();
            if(d.success) {
                showToast(d.message, 'success');
                if(type==='stalker') { document.getElementById('stalkerName').value=''; document.getElementById('stalkerHost').value=''; document.getElementById('stalkerMac').value=''; document.getElementById('stalkerActive').checked=false; }
                else { document.getElementById('xtreamName').value=''; document.getElementById('xtreamHost').value=''; document.getElementById('xtreamUser').value=''; document.getElementById('xtreamPass').value=''; document.getElementById('xtreamActive').checked=false; }
                loadServers();
            } else showToast(d.errors ? d.errors.join(', ') : 'Erreur', 'error');
        } catch(e) { showToast('Erreur', 'error'); }
    }
    async function toggleActive(id, active) {
        try {
            const res = await fetch(`/api/servers/${id}`, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({active}) });
            const d = await res.json();
            if(d.success) { showToast(d.message, 'success'); loadServers(); }
            else showToast('Erreur', 'error');
        } catch(e) { showToast('Erreur', 'error'); }
    }
    async function deleteServer(id, name) {
        if(!confirm(`Supprimer "${name}" ?`)) return;
        try {
            const res = await fetch(`/api/servers/${id}`, { method:'DELETE' });
            const d = await res.json();
            if(d.success) { showToast(d.message, 'success'); loadServers(); }
            else showToast(d.error, 'error');
        } catch(e) { showToast('Erreur', 'error'); }
    }

    async function loadLines() {
        try {
            const res = await fetch('/api/lines');
            const d = await res.json();
            if(d.success) {
                renderLines(d.lines);
                document.getElementById('totalLines').innerText = d.lines.length;
            }
        } catch(e) { document.getElementById('linesList').innerHTML = '<div class="loading">❌ Erreur</div>'; }
    }
    function renderLines(lines) {
        const c = document.getElementById('linesList');
        if(!lines.length) { c.innerHTML = '<div class="loading">📭 Aucune ligne</div>'; return; }
        c.innerHTML = lines.map(l => `
            <div class="item-card ${l.type === 'cccam' ? 'cccam' : 'oscam'}">
                <div class="item-header"><div class="item-title"><span class="item-name">${l.type.toUpperCase()} : ${escapeHtml(l.host)}:${escapeHtml(l.port)}</span><span class="badge ${l.active ? 'badge-active' : 'badge-inactive'}">${l.active ? 'ACTIF' : 'INACTIF'}</span></div></div>
                <div class="item-details">👤 User: ${escapeHtml(l.username)}<br>🔒 Pass: ********</div>
                <div class="item-actions"><button class="btn btn-sm ${l.active ? 'btn-warning' : 'btn-success'}" onclick="toggleLineActive('${l.id}', ${!l.active})">${l.active ? '⏸️ Désactiver' : '▶️ Activer'}</button><button class="btn btn-sm btn-purple" onclick="openLineEditModal('${l.id}')">✏️ Modifier</button><button class="btn btn-sm btn-danger" onclick="deleteLine('${l.id}', '${escapeHtml(l.host)}:${escapeHtml(l.port)}')">🗑️ Supprimer</button></div>
            </div>`).join('');
    }
    async function addLine(type) {
        let p = { type };
        if(type === 'cccam') {
            p.host = document.getElementById('cccamHost').value.trim();
            p.port = document.getElementById('cccamPort').value.trim();
            p.username = document.getElementById('cccamUser').value.trim();
            p.password = document.getElementById('cccamPass').value.trim();
            p.active = document.getElementById('cccamActive').checked;
        } else {
            p.host = document.getElementById('oscamHost').value.trim();
            p.port = document.getElementById('oscamPort').value.trim();
            p.username = document.getElementById('oscamUser').value.trim();
            p.password = document.getElementById('oscamPass').value.trim();
            p.active = document.getElementById('oscamActive').checked;
        }
        if(!p.host || !p.port || !p.username || !p.password) { showToast('Tous les champs requis', 'error'); return; }
        try {
            const res = await fetch('/api/lines', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p) });
            const d = await res.json();
            if(d.success) {
                showToast(d.message, 'success');
                if(type==='cccam') { document.getElementById('cccamHost').value=''; document.getElementById('cccamPort').value=''; document.getElementById('cccamUser').value=''; document.getElementById('cccamPass').value=''; document.getElementById('cccamActive').checked=true; }
                else { document.getElementById('oscamHost').value=''; document.getElementById('oscamPort').value=''; document.getElementById('oscamUser').value=''; document.getElementById('oscamPass').value=''; document.getElementById('oscamActive').checked=true; }
                loadLines();
            } else showToast(d.errors ? d.errors.join(', ') : 'Erreur', 'error');
        } catch(e) { showToast('Erreur', 'error'); }
    }
    async function toggleLineActive(id, active) {
        try {
            const res = await fetch(`/api/lines/${id}`, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({active}) });
            const d = await res.json();
            if(d.success) { showToast(d.message, 'success'); loadLines(); }
            else showToast('Erreur', 'error');
        } catch(e) { showToast('Erreur', 'error'); }
    }
    async function openLineEditModal(id) {
        try {
            const res = await fetch(`/api/lines/${id}`);
            const d = await res.json();
            if(d.success && d.line) {
                const l = d.line;
                document.getElementById('editLineId').value = l.id;
                document.getElementById('editLineType').value = l.type;
                document.getElementById('editLineHost').value = l.host || '';
                document.getElementById('editLinePort').value = l.port || '';
                document.getElementById('editLineUser').value = l.username || '';
                document.getElementById('editLinePass').value = '';
                document.getElementById('editLineActive').checked = l.active || false;
                document.getElementById('editLineModal').classList.add('open');
            }
        } catch(e) { showToast('Erreur', 'error'); }
    }
    async function saveLineEdit() {
        const id = document.getElementById('editLineId').value;
        const p = {
            host: document.getElementById('editLineHost').value.trim(),
            port: document.getElementById('editLinePort').value.trim(),
            username: document.getElementById('editLineUser').value.trim(),
            password: document.getElementById('editLinePass').value.trim(),
            active: document.getElementById('editLineActive').checked
        };
        if(!p.host || !p.port || !p.username) { showToast('Hôte, port et utilisateur requis', 'error'); return; }
        try {
            const res = await fetch(`/api/lines/${id}`, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p) });
            const d = await res.json();
            if(d.success) { showToast(d.message, 'success'); closeLineModal(); loadLines(); }
            else showToast(d.error || 'Erreur', 'error');
        } catch(e) { showToast('Erreur', 'error'); }
    }
    async function deleteLine(id, name) {
        if(!confirm(`Supprimer "${name}" ?`)) return;
        try {
            const res = await fetch(`/api/lines/${id}`, { method:'DELETE' });
            const d = await res.json();
            if(d.success) { showToast(d.message, 'success'); loadLines(); }
            else showToast(d.error, 'error');
        } catch(e) { showToast('Erreur', 'error'); }
    }
    function closeLineModal() { document.getElementById('editLineModal').classList.remove('open'); }
    window.onclick = e => { if(e.target === document.getElementById('editLineModal')) closeLineModal(); };
    document.addEventListener('DOMContentLoaded', () => loadServers());
</script>
</body>
</html>'''


# ==================== MAIN ====================
def run_server(port=DEFAULT_PORT):
    try:
        server = HTTPServer(('0.0.0.0', port), EbroStreamHandler)
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
        except:
            ip = socket.gethostbyname(socket.gethostname()) if hasattr(socket, 'gethostbyname') else "127.0.0.1"

        print(f"""
╔══════════════════════════════════════════════════════════════╗
║              EbroStream Web Server v5.0 - Autonome           ║
╠══════════════════════════════════════════════════════════════╣
║  🌐 Serveur démarré sur le port {port}                         ║
║  📁 Serveurs IPTV: {SERVERS_FILE}                           ║
║  📁 CCcam: {CCCAM_FILE}                                     ║
║  📁 Oscam: {OSCAM_FILE}                                     ║
║                                                              ║
║  📱 Accédez à l'interface via:                              ║
║     http://{ip}:{port}                                       ║
║                                                              ║
║  🛑 Ctrl+C pour arrêter                                      ║
╚══════════════════════════════════════════════════════════════╝
        """)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Arrêt du serveur web...")
    except Exception as e:
        print(f"❌ Erreur: {e}")


if __name__ == '__main__':
    port = DEFAULT_PORT
    if len(sys.argv) > 2 and sys.argv[1] == '--port':
        try:
            port = int(sys.argv[2])
        except ValueError:
            pass
    run_server(port)
