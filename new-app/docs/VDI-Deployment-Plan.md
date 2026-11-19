# MOA Valuation — VDI Deployment Plan

## Short answer: domain vs localhost

**Use localhost.** Do **not** put this app on a public or corporate domain for normal VDI use.

| Question | Answer |
|----------|--------|
| Does the EXE need a domain name? | **No** |
| What URL does the browser open? | `http://127.0.0.1:8002` (localhost) |
| Who can reach it? | Only that user’s VDI session (same Windows desktop) |
| Is a shared web server needed? | **No** — each user starts their own copy of the EXE |

The EXE starts a local server bound to `127.0.0.1:8002`. The browser inside that VDI talks only to the machine/session where the EXE is running. Other users on other VDI sessions cannot open your localhost, and you do not need DNS, IIS, or a company domain for this.

---

## Target model (recommended)

Assumptions:

- Users connect from their own PCs into a **VDI**.
- Each user has **their own Windows login / session**.
- The EXE may live in a **common folder** (shared install path), but each click starts **that user’s own process**.

```text
User PC ──RDP/VDI──► User's Windows session
                         │
                         ├─ double-click MOA_Valuation.exe
                         ├─ server on 127.0.0.1:8002  (local only)
                         └─ browser opens UI in same session
```

This matches Case A from operations guidance: many users can run at once because each session has its own localhost and its own port namespace.

---

## What to deploy

| Artifact | Purpose |
|----------|---------|
| `MOA_Valuation_Setup.msi` | Preferred — installs under Program Files, Start Menu + Desktop shortcuts |
| `MOA_Valuation_portable.zip` | Alternative — unzip to a common folder; shortcut to `MOA_Valuation.exe` |

Build on a Windows machine (or GitHub Actions), then hand IT the MSI or zip. End users do **not** need Python.

How to build: see [`packaging/README.md`](../packaging/README.md) (`packaging\RUN_BUILD.cmd` on Windows).

---

## Recommended install layout

### Option 1 — MSI on golden image / common Program Files (preferred)

1. Install `MOA_Valuation_Setup.msi` once on the VDI golden image (or via software deployment).
2. Default location: `C:\Program Files\MOA Valuation\MOA_Valuation.exe`
3. Each user gets Start Menu / Desktop **MOA Valuation** shortcut.
4. Users double-click the shortcut in **their** session.

### Option 2 — Common shared folder

1. Unzip portable build to e.g. `\\fileserver\Apps\MOA_Valuation\` or `C:\Apps\MOA_Valuation\`.
2. Publish a shortcut for all users to `MOA_Valuation.exe` in that folder.
3. Keep the folder **read-only for users** if possible (program files only).
4. Do **not** store output PDFs in that common folder.

Writable data stays per user (see below).

---

## Per-user data (important)

When frozen, the app writes to:

| Data | Default location |
|------|------------------|
| Output PDFs | `%LOCALAPPDATA%\MOA Valuation\output\` |
| Logs | `%LOCALAPPDATA%\MOA Valuation\logs\` |

That is **per Windows user**, so User A and User B do not overwrite each other even if they share the same EXE path.

### Optional: network output drive

If packages must land on a shared drive (e.g. `K:\Mutual of America`):

1. Set user or machine env var, e.g.  
   `MOA_OUTPUT_DIR=K:\Mutual of America\ValuationPackages\%USERNAME%`  
   (include `%USERNAME%` or another per-user folder so files do not collide.)
2. Or set `MOA_DATA_DIR` for both output + logs under a per-user path.

Do **not** point every user at the exact same output folder without a username subfolder.

---

## Day-to-day user flow

1. User logs into VDI.
2. Clicks **MOA Valuation** (shortcut or EXE).
3. Black console window opens — **leave it open**.
4. Browser opens to `http://127.0.0.1:8002`.
5. User uploads / processes packages as today.
6. User closes the console window to stop the app.

No CMD typing. No domain URL. No separate “server” machine for this model.

---

## Two users at the same time

| Scenario | Result |
|----------|--------|
| Two users, each with **own VDI session**, both click EXE | **OK** — two processes, each on their own localhost:8002 |
| Two people on the **same** Windows desktop session | **Not OK** — second start usually fails (port 8002 in use) |

Your stated model (“each user has their own access”) → first row → localhost is correct.

---

## Network / security notes

- Binding is `127.0.0.1` by default — not reachable from other machines or other users’ sessions.
- Do **not** set `MOA_HOST=0.0.0.0` in VDI unless IT explicitly wants network access (then you need firewall rules, auth, and a different architecture).
- Unsigned EXE/MSI may trigger SmartScreen — IT should **allowlist** the publisher path or sign the binary later.
- Antivirus may need an allow rule for `MOA_Valuation.exe` and the install folder.

---

## What you do **not** need for this plan

- IIS / Tomcat / company domain hostname  
- Load balancer  
- Shared single server process for all users  
- Login/session system (optional later; not required for per-user VDI + localhost)  
- Python on end-user VDIs (only on the Windows build machine)

---

## Rollout checklist

### Build (once, on Windows build PC or CI)

- [ ] Run `packaging\RUN_BUILD.cmd` (or GitHub Actions Windows workflow)
- [ ] Smoke-test `dist\MOA_Valuation\MOA_Valuation.exe` on a clean Windows box
- [ ] Deliver `MOA_Valuation_Setup.msi` and/or portable zip to IT

### IT / VDI

- [ ] Install MSI on golden image **or** place portable folder in common Apps path
- [ ] Publish Start Menu / Desktop shortcut for the user group
- [ ] Allowlist EXE with AV / SmartScreen if required
- [ ] Confirm `%LOCALAPPDATA%` is writable (or set `MOA_OUTPUT_DIR` / `MOA_DATA_DIR`)
- [ ] If using a network drive for finals, create per-user folders and set env vars

### UAT (2 users)

- [ ] User A and User B log into separate VDI sessions
- [ ] Both launch EXE; both get browser on localhost:8002
- [ ] Each completes a small job; outputs appear under each user’s LocalAppData (or their output path)
- [ ] Closing console stops only that user’s app

### Support cheat sheet

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Browser does not open | Firewall/browser blocked localhost | Open `http://127.0.0.1:8002` manually; check console for errors |
| “Address already in use” | Second instance in same session | Close the first console window |
| SmartScreen blocks EXE | Unsigned binary | IT allowlist or code-sign |
| Cannot write output | Profile / AppData redirected or locked | Set `MOA_OUTPUT_DIR` to a writable path |
| Port conflict after crash | Orphan process still holding 8002 | End `MOA_Valuation.exe` in Task Manager |

---

## Decision summary

| Topic | Decision |
|-------|----------|
| URL / host | **Localhost** `127.0.0.1:8002` |
| Domain required? | **No** |
| EXE location | Common folder or Program Files OK |
| Runtime data | Per-user `%LOCALAPPDATA%\MOA Valuation` |
| Multi-user | One EXE process **per user VDI session** |
| Architecture | Desktop-launched local app, not a shared website |
