#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EbroStream Web Server - Gestion des lignes Softcam (CCcam + Oscam)
Fichier indépendant - Uniquement pour les lignes Cccam et Oscam

Utilisation:
    python3 softcam_web.py
    python3 softcam_web.py --port 9090
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import sys
import uuid
from urllib.parse import urlparse

# ==================== CONFIGURATION ====================
DEFAULT_PORT = 8088

# Chemins des fichiers
CCCAM_FILE = "/etc/tuxbox/config/CCcam.cfg"
OSCAM_FILE = "/etc/tuxbox/config/oscam.server"

# Créer les répertoires si nécessaire
try:
    os.makedirs(os.path.dirname(CCCAM_FILE), exist_ok=True)
except:
    pass


class SoftcamHandler(BaseHTTPRequestHandler):
    """Gestionnaire API pour CCcam et Oscam"""

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

        if path == '/api/lines':
            self._get_lines()
        elif path.startswith('/api/lines/'):
            self._get_line_by_id(path.split('/')[-1])
        elif path == '/' or path == '':
            self._serve_web()
        else:
            self._send_json(404, {"error": f"Route non trouvée: {path}"})

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        data = self._parse_body(content_length)

        if self.path == '/api/lines':
            self._add_line(data)
        else:
            self._send_json(404, {"error": "Route non trouvée"})

    def do_PUT(self):
        content_length = int(self.headers.get('Content-Length', 0))
        data = self._parse_body(content_length)

        if self.path.startswith('/api/lines/'):
            self._update_line(self.path.split('/')[-1], data)
        else:
            self._send_json(404, {"error": "Route non trouvée"})

    def do_DELETE(self):
        if self.path.startswith('/api/lines/'):
            self._delete_line(self.path.split('/')[-1])
        else:
            self._send_json(404, {"error": "Route non trouvée"})

    def _parse_body(self, length):
        try:
            data = self.rfile.read(length).decode('utf-8') if length > 0 else '{}'
            return json.loads(data) if data else {}
        except:
            return {}

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
            with open(CCCAM_FILE, 'w') as f:
                f.write("# Generated by EbroStream - Softcam Manager\n\n")
                if cccam:
                    for l in cccam:
                        if l.get('active', True):
                            f.write(f"C: {l['host']} {l['port']} {l['username']} {l['password']}\n")
                        else:
                            f.write(f"# C: {l['host']} {l['port']} {l['username']} {l['password']}\n")
                else:
                    f.write("# No active CCcam lines\n")

            # Sauvegarder oscam.server
            with open(OSCAM_FILE, 'w') as f:
                f.write("# Generated by EbroStream - Softcam Manager\n\n")
                if oscam:
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
                else:
                    f.write("# No active OSCAM readers\n")

            return True
        except Exception as e:
            print(f"Erreur sauvegarde: {e}")
            return False

    # ==================== INTERFACE WEB ====================

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
    <title>Softcam Manager - CCcam & Oscam</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; font-family:system-ui, 'Segoe UI', Roboto, sans-serif; }
        body { background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%); min-height:100vh; padding:20px; }
        .container { max-width:1200px; margin:0 auto; }
        .card { background:rgba(255,255,255,0.08); backdrop-filter:blur(10px); border-radius:24px; border:1px solid rgba(255,255,255,0.12); margin-bottom:24px; }
        .card-header { padding:20px 28px; border-bottom:1px solid rgba(255,255,255,0.1); background:rgba(0,0,0,0.2); }
        .card-header h2 { font-size:1.5rem; font-weight:600; color:#fff; display:flex; align-items:center; gap:10px; }
        .card-body { padding:24px 28px; }
        .stats { display:flex; gap:20px; margin-bottom:30px; flex-wrap:wrap; }
        .stat { background:rgba(255,255,255,0.05); border-radius:20px; padding:15px 30px; text-align:center; flex:1; min-width:150px; }
        .stat-value { font-size:2rem; font-weight:700; color:#60efff; }
        .stat-label { color:#a8b2d1; margin-top:6px; font-size:0.85rem; }
        .tabs { display:flex; gap:10px; margin-bottom:30px; flex-wrap:wrap; }
        .tab { padding:10px 25px; background:rgba(255,255,255,0.05); border-radius:50px; cursor:pointer; font-weight:600; transition:0.2s; }
        .tab.active { background:#3b82f6; box-shadow:0 4px 15px rgba(59,130,246,0.4); }
        .form-panel { display:none; }
        .form-panel.active { display:block; }
        .form-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px,1fr)); gap:20px; margin-bottom:20px; }
        .form-group { margin-bottom:16px; }
        label { display:block; margin-bottom:8px; color:#cbd5e1; font-weight:500; font-size:0.85rem; }
        input { width:100%; padding:12px 16px; background:rgba(0,0,0,0.45); border:1px solid rgba(255,255,255,0.15); border-radius:12px; color:white; font-size:0.95rem; }
        input:focus { outline:none; border-color:#60efff; }
        .checkbox-row { display:flex; align-items:center; gap:12px; margin-top:20px; }
        .checkbox-row input { width:auto; }
        .btn { padding:12px 28px; border:none; border-radius:40px; font-weight:600; font-size:0.9rem; cursor:pointer; transition:0.2s; }
        .btn-warning { background:#f59e0b; color:white; }
        .btn-warning:hover { background:#d97706; transform:scale(1.02); }
        .btn-purple { background:#8b5cf6; color:white; }
        .btn-purple:hover { background:#7c3aed; transform:scale(1.02); }
        .btn-success { background:#10b981; color:white; }
        .btn-success:hover { background:#059669; }
        .btn-danger { background:#ef4444; color:white; }
        .btn-danger:hover { background:#dc2626; }
        .btn-warning-outline { background:rgba(245,158,11,0.2); color:#f59e0b; border:1px solid #f59e0b; }
        .btn-purple-outline { background:rgba(139,92,246,0.2); color:#8b5cf6; border:1px solid #8b5cf6; }
        .btn-sm { padding:6px 14px; font-size:0.75rem; }
        .items-list { display:flex; flex-direction:column; gap:12px; margin-top:20px; }
        .item-card { background:rgba(0,0,0,0.35); border-radius:16px; padding:16px 20px; border-left:4px solid; transition:0.2s; }
        .item-card.cccam { border-left-color:#f59e0b; }
        .item-card.oscam { border-left-color:#8b5cf6; }
        .item-header { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:10px; }
        .item-title { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
        .item-name { font-size:1.1rem; font-weight:600; color:white; }
        .badge { padding:4px 12px; border-radius:20px; font-size:0.7rem; font-weight:600; }
        .badge-active { background:rgba(16,185,129,0.25); color:#34d399; }
        .badge-inactive { background:rgba(156,163,175,0.2); color:#9ca3af; }
        .badge-cccam { background:rgba(245,158,11,0.2); color:#f59e0b; }
        .badge-oscam { background:rgba(139,92,246,0.2); color:#8b5cf6; }
        .item-details { font-size:0.8rem; color:#9ca3af; margin:8px 0; line-height:1.6; }
        .item-actions { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }
        .alert { position:fixed; bottom:20px; right:20px; max-width:380px; background:#1e293b; border-left:4px solid; padding:14px 20px; border-radius:16px; color:white; z-index:1000; opacity:0; transition:0.3s; pointer-events:none; }
        .alert.show { opacity:1; }
        .alert.success { border-left-color:#10b981; }
        .alert.error { border-left-color:#ef4444; }
        .loading { text-align:center; padding:40px; color:#94a3b8; }
        .modal { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.8); align-items:center; justify-content:center; z-index:1001; }
        .modal.open { display:flex; }
        .modal-content { background:#1e1b4b; border-radius:28px; width:90%; max-width:500px; padding:28px; border:1px solid rgba(255,255,255,0.1); }
        .modal-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
        .modal-close { background:none; border:none; color:#cbd5e1; font-size:1.5rem; cursor:pointer; }
        hr { border-color:rgba(255,255,255,0.08); margin:20px 0; }
        @media (max-width:700px){ .form-grid { grid-template-columns:1fr; } }
    </style>
</head>
<body>
<div class="container">
    <div class="card">
        <div class="card-header">
            <h2>🔑 Gestion des lignes Softcam</h2>
        </div>
        <div class="card-body">
            <div class="stats">
                <div class="stat"><div class="stat-value" id="totalLines">0</div><div class="stat-label">Total lignes</div></div>
                <div class="stat"><div class="stat-value" id="activeLines">0</div><div class="stat-label">Lignes actives</div></div>
            </div>

            <div class="tabs">
                <div class="tab active" data-tab="cccam">📡 CCcam (format C:)</div>
                <div class="tab" data-tab="oscam">⚙️ Oscam (format [reader])</div>
            </div>

            <!-- Formulaire CCcam -->
            <div id="formCccam" class="form-panel active">
                <div class="form-grid">
                    <div><label>🌐 Hôte / Serveur</label><input type="text" id="cccamHost" placeholder="ex: server.dyndns.org"></div>
                    <div><label>🔌 Port</label><input type="text" id="cccamPort" placeholder="12000"></div>
                    <div><label>👤 Nom d'utilisateur</label><input type="text" id="cccamUser" placeholder="username"></div>
                    <div><label>🔒 Mot de passe</label><input type="password" id="cccamPass" placeholder="password"></div>
                    <div class="checkbox-row"><input type="checkbox" id="cccamActive" checked> <label>✅ Activer cette ligne</label></div>
                </div>
                <button class="btn btn-warning" onclick="addLine('cccam')">➕ Ajouter ligne CCcam</button>
            </div>

            <!-- Formulaire Oscam -->
            <div id="formOscam" class="form-panel">
                <div class="form-grid">
                    <div><label>🌐 Hôte / Serveur</label><input type="text" id="oscamHost" placeholder="ex: server.dyndns.org"></div>
                    <div><label>🔌 Port</label><input type="text" id="oscamPort" placeholder="12000"></div>
                    <div><label>👤 Nom d'utilisateur</label><input type="text" id="oscamUser" placeholder="username"></div>
                    <div><label>🔒 Mot de passe</label><input type="password" id="oscamPass" placeholder="password"></div>
                    <div class="checkbox-row"><input type="checkbox" id="oscamActive" checked> <label>✅ Activer cette ligne</label></div>
                </div>
                <button class="btn btn-purple" onclick="addLine('oscam')">➕ Ajouter ligne Oscam</button>
            </div>

            <hr>
            <h3 style="margin:20px 0 15px 0; color:#cbd5e1;">📋 Liste des lignes configurées</h3>
            <div id="linesList"><div class="loading">⏳ Chargement des lignes...</div></div>
        </div>
    </div>
</div>

<div id="toast" class="alert"></div>

<!-- Modal Édition -->
<div id="editModal" class="modal">
    <div class="modal-content">
        <div class="modal-header">
            <h3 style="color:white;">✏️ Modifier la ligne</h3>
            <button class="modal-close" onclick="closeModal()">✕</button>
        </div>
        <input type="hidden" id="editId"><input type="hidden" id="editType">
        <div><label>🌐 Hôte</label><input type="text" id="editHost"></div>
        <div style="margin-top:15px;"><label>🔌 Port</label><input type="text" id="editPort"></div>
        <div style="margin-top:15px;"><label>👤 Utilisateur</label><input type="text" id="editUser"></div>
        <div style="margin-top:15px;"><label>🔒 Mot de passe</label><input type="password" id="editPass" placeholder="Laisser vide = inchangé"></div>
        <div class="checkbox-row" style="margin-top:20px;"><input type="checkbox" id="editActive"> <label>✅ Actif</label></div>
        <div style="display:flex; gap:12px; margin-top:28px; justify-content:flex-end;">
            <button class="btn" style="background:#334155;" onclick="closeModal()">Annuler</button>
            <button class="btn btn-purple" onclick="saveEdit()">💾 Enregistrer</button>
        </div>
    </div>
</div>

<script>
    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.onclick = () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const t = tab.dataset.tab;
            document.getElementById('formCccam').classList.toggle('active', t === 'cccam');
            document.getElementById('formOscam').classList.toggle('active', t === 'oscam');
        };
    });

    function showToast(msg, type='success') {
        const t = document.getElementById('toast');
        t.textContent = msg;
        t.className = `alert ${type} show`;
        setTimeout(() => t.classList.remove('show'), 3500);
    }

    function escapeHtml(s) { if(!s) return ''; return s.replace(/[&<>]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[m])); }

    async function loadLines() {
        try {
            const res = await fetch('/api/lines');
            const d = await res.json();
            if(d.success) {
                renderLines(d.lines);
                document.getElementById('totalLines').innerText = d.lines.length;
                document.getElementById('activeLines').innerText = d.lines.filter(l=>l.active).length;
            }
        } catch(e) {
            document.getElementById('linesList').innerHTML = '<div class="loading">❌ Erreur de connexion</div>';
        }
    }

    function renderLines(lines) {
        const container = document.getElementById('linesList');
        if(!lines.length) {
            container.innerHTML = '<div class="loading">📭 Aucune ligne configurée. Ajoutez une ligne ci-dessus.</div>';
            return;
        }
        container.innerHTML = lines.map(l => `
            <div class="item-card ${l.type}">
                <div class="item-header">
                    <div class="item-title">
                        <span class="item-name">${l.type.toUpperCase()} : ${escapeHtml(l.host)}:${escapeHtml(l.port)}</span>
                        <span class="badge ${l.type === 'cccam' ? 'badge-cccam' : 'badge-oscam'}">${l.type.toUpperCase()}</span>
                        <span class="badge ${l.active ? 'badge-active' : 'badge-inactive'}">${l.active ? 'ACTIF' : 'INACTIF'}</span>
                    </div>
                </div>
                <div class="item-details">
                    👤 Utilisateur: ${escapeHtml(l.username)}<br>
                    🔒 Mot de passe: ********
                </div>
                <div class="item-actions">
                    <button class="btn btn-sm ${l.active ? 'btn-warning-outline' : 'btn-success'}" onclick="toggleActive('${l.id}', ${!l.active})">
                        ${l.active ? '⏸️ Désactiver' : '▶️ Activer'}
                    </button>
                    <button class="btn btn-sm btn-purple-outline" onclick="openEditModal('${l.id}')">✏️ Modifier</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteLine('${l.id}', '${escapeHtml(l.host)}:${escapeHtml(l.port)}')">🗑️ Supprimer</button>
                </div>
            </div>
        `).join('');
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
        if(!p.host || !p.port || !p.username || !p.password) {
            showToast('Tous les champs sont obligatoires', 'error');
            return;
        }
        try {
            const res = await fetch('/api/lines', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify(p)
            });
            const d = await res.json();
            if(d.success) {
                showToast(d.message, 'success');
                if(type === 'cccam') {
                    document.getElementById('cccamHost').value = '';
                    document.getElementById('cccamPort').value = '';
                    document.getElementById('cccamUser').value = '';
                    document.getElementById('cccamPass').value = '';
                    document.getElementById('cccamActive').checked = true;
                } else {
                    document.getElementById('oscamHost').value = '';
                    document.getElementById('oscamPort').value = '';
                    document.getElementById('oscamUser').value = '';
                    document.getElementById('oscamPass').value = '';
                    document.getElementById('oscamActive').checked = true;
                }
                loadLines();
            } else {
                showToast(d.errors ? d.errors.join(', ') : 'Erreur', 'error');
            }
        } catch(e) {
            showToast('Erreur réseau', 'error');
        }
    }

    async function toggleActive(id, active) {
        try {
            const res = await fetch(`/api/lines/${id}`, {
                method:'PUT',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({active})
            });
            const d = await res.json();
            if(d.success) {
                showToast(d.message, 'success');
                loadLines();
            } else {
                showToast('Erreur', 'error');
            }
        } catch(e) {
            showToast('Erreur', 'error');
        }
    }

    async function openEditModal(id) {
        try {
            const res = await fetch(`/api/lines/${id}`);
            const d = await res.json();
            if(d.success && d.line) {
                const l = d.line;
                document.getElementById('editId').value = l.id;
                document.getElementById('editType').value = l.type;
                document.getElementById('editHost').value = l.host || '';
                document.getElementById('editPort').value = l.port || '';
                document.getElementById('editUser').value = l.username || '';
                document.getElementById('editPass').value = '';
                document.getElementById('editActive').checked = l.active || false;
                document.getElementById('editModal').classList.add('open');
            }
        } catch(e) {
            showToast('Erreur chargement', 'error');
        }
    }

    async function saveEdit() {
        const id = document.getElementById('editId').value;
        const p = {
            host: document.getElementById('editHost').value.trim(),
            port: document.getElementById('editPort').value.trim(),
            username: document.getElementById('editUser').value.trim(),
            password: document.getElementById('editPass').value.trim(),
            active: document.getElementById('editActive').checked
        };
        if(!p.host || !p.port || !p.username) {
            showToast('Hôte, port et utilisateur requis', 'error');
            return;
        }
        try {
            const res = await fetch(`/api/lines/${id}`, {
                method:'PUT',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify(p)
            });
            const d = await res.json();
            if(d.success) {
                showToast(d.message, 'success');
                closeModal();
                loadLines();
            } else {
                showToast(d.error || 'Erreur', 'error');
            }
        } catch(e) {
            showToast('Erreur', 'error');
        }
    }

    async function deleteLine(id, name) {
        if(!confirm(`Supprimer la ligne "${name}" ?`)) return;
        try {
            const res = await fetch(`/api/lines/${id}`, { method:'DELETE' });
            const d = await res.json();
            if(d.success) {
                showToast(d.message, 'success');
                loadLines();
            } else {
                showToast(d.error, 'error');
            }
        } catch(e) {
            showToast('Erreur', 'error');
        }
    }

    function closeModal() {
        document.getElementById('editModal').classList.remove('open');
    }

    window.onclick = e => {
        if(e.target === document.getElementById('editModal')) closeModal();
    };

    document.addEventListener('DOMContentLoaded', loadLines);
</script>
</body>
</html>'''


# ==================== MAIN ====================
def run_server(port=DEFAULT_PORT):
    try:
        server = HTTPServer(('0.0.0.0', port), SoftcamHandler)
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
║              Softcam Manager v1.0 - CCcam & Oscam            ║
╠══════════════════════════════════════════════════════════════╣
║  🌐 Serveur démarré sur le port {port}                         ║
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
        print("\n\n👋 Arrêt du serveur...")
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
