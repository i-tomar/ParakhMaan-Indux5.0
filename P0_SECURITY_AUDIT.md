# ParakhMaan 2.0 — P0 Safety and Security Audit Report

**Date:** November 2026  
**Auditor:** Senior Backend, Computer-Vision and Industrial Automation Engineer  
**Scope:** `ParakhMaan-2.0` Branch — Real-Time Live Inspection, Actuators, Session Isolation, WebSockets, and RTSP  
**Status:** Audit Completed; Remediations Planned and Verified

---

## Executive Summary

ParakhMaan 2.0 provides an industrial visual inspection platform combining YOLO11-seg segmentation, PatchCore anomaly detection, OpenCV corroboration, and real-time conveyor tracking. An audit of the real-time execution subsystem (`live.py`, `pipeline.py`, `actuator.py`, and `sources.py`) identified **four critical P0 safety and security vulnerabilities**:

1. **Unrestricted Actuator Execution (Physical Safety & Process Disruption):** Any authenticated user (including basic `INSPECTOR` roles) can initiate sessions bound to production lines configured with `SERIAL` or `WEBHOOK` actuators without explicit hardware-arming, safety interlocks, or audit logging.
2. **Missing Session Ownership & Scope Access Control (Insecure Direct Object Reference):** Live sessions do not track their creator or organizational scope. Any authenticated user can read live telemetry, terminate active inspection sessions, or eavesdrop on WebSocket video feeds of other operators.
3. **Unbounded WebSocket Ingestion (Denial of Service & Memory Exhaustion):** The WebSocket endpoint accepts arbitrary byte streams with no payload size bounds, no maximum decoded image dimension/pixel caps, and no frame-rate throttling, allowing denial of service and decompression resource exhaustion.
4. **Unrestricted RTSP Ingestion (Server-Side Request Forgery & Resource Locking):** The RTSP source accepts arbitrary destination URLs with only a prefix check (`rtsp://`), enabling SSRF attacks against internal network equipment, cloud metadata endpoints (`169.254.169.254`), and hanging video capture threads without timeouts.

---

## Detailed Findings

### 1. Actuator Authorisation & Hardware Arming
- **Files:** `backend/app/api/live.py` (Lines 61–69), `backend/app/services/realtime/pipeline.py` (Lines 79–96, 196–208), `backend/app/services/line/actuator.py` (Lines 100–107).
- **Vulnerability:** When a session is initiated with `line_id`, `LiveSession.start()` reads `line.actuator_kind` from the database and instantiates `SerialActuator` or `WebhookActuator` immediately.
  - A regular `INSPECTOR` account can trigger physical solenoid diverters, pneumatic pushers, or external PLC webhooks.
  - No explicit "ARM" operation exists; hardware actuation is enabled by default if configured on the line.
  - No audit logs are written to record who armed hardware, who disarmed it, or who started/stopped an active line session.
- **Risk:** High. Unauthorized physical actuation can cause equipment damage, operator safety hazards, or line jams.
- **Required Remediation:**
  - Actuator must default to `SimulatedActuator` for all sessions unless explicitly armed.
  - Arming real hardware (`SERIAL` or `WEBHOOK`) must be restricted to `SUPERVISOR` or `ADMIN` roles.
  - Any request from an `INSPECTOR` attempting to arm or activate physical hardware must be rejected with HTTP 403.
  - Dedicated arm/disarm actions and session lifecycle events must record entries in `AuditEvent` and application audit logs.

---

### 2. Live Session Ownership & Multi-Tenant Isolation
- **Files:** `backend/app/api/live.py` (Lines 61–85, 88–98), `backend/app/services/realtime/pipeline.py` (Lines 36–77, 267–286).
- **Vulnerability:**
  - `SessionConfig` and `LiveSession` lack `user_id` and line/plant ownership metadata.
  - `GET /sessions/{session_id}` and `POST /sessions/{session_id}/stop` allow any logged-in user to inspect or terminate another user's session.
  - `GET /sessions/{session_id}/stream` (WebSocket) checks if `token` is valid, but does not verify whether the token's subject matches the session creator or holds supervisory privileges.
- **Risk:** High. Operators on different shifts or lines can cross-terminate ongoing inspection runs or hijack live video feeds.
- **Required Remediation:**
  - Store `user_id` and creating role on `LiveSession`.
  - Enforce authorization: only the session owner or a user with `SUPERVISOR`/`ADMIN` role can query stats, stop the session, or connect via WebSocket.
  - Cross-user access by standard inspectors must return HTTP 403 Forbidden (REST) or close with WebSocket code 4403.

---

### 3. WebSocket Resource Exhaustion & Payload Validation
- **Files:** `backend/app/api/live.py` (Lines 88–107).
- **Vulnerability:**
  - `websocket.receive_bytes()` reads incoming binary messages with no maximum byte limit.
  - Decoded frames from `cv2.imdecode` have no maximum width, height, or pixel count checks.
  - There is no rate limiter: a client can flood hundreds of frames per second, starving backend CPU/memory.
  - Malformed frames (where `cv2.imdecode` returns `None`) are silently skipped without incrementing error telemetry or notifying the client.
- **Risk:** Medium to High. Memory exhaustion via decompression bombs or network flooding can crash the server process.
- **Required Remediation:**
  - Enforce maximum encoded payload size (e.g., 5 MB limit per frame).
  - Enforce maximum decoded dimensions (e.g., max 3840x2160, max 8,294,400 pixels).
  - Enforce per-session FPS cap (e.g., maximum 35 FPS with token bucket or rate tracker).
  - Return explicit client error / WebSocket close on malformed image data.

---

### 4. Unvalidated RTSP Ingestion & SSRF
- **Files:** `backend/app/api/live.py` (Lines 56–58), `backend/app/services/realtime/sources.py` (Lines 21–40).
- **Vulnerability:**
  - `req.source_kind == "RTSP"` only checks `req.source.startswith("rtsp://")`.
  - An attacker or misconfigured client can pass `rtsp://127.0.0.1:port/`, `rtsp://169.254.169.254/`, or internal IP ranges, causing the backend server to establish connections to internal services (SSRF).
  - `cv2.VideoCapture` on unreachable destinations blocks the worker thread without a bounded connection timeout.
- **Risk:** Medium to High. Internal network reconnaissance, cloud credential access, and hung threads.
- **Required Remediation:**
  - Parse the RTSP URL and validate hostname/IP against an explicit allowlist (`RTSP_ALLOWED_HOSTS` or allowlisted IP ranges/patterns).
  - Explicitly block loopback (`127.0.0.0/8`, `::1`), link-local/cloud metadata (`169.254.169.254`), and unapproved hostnames.
  - Validate connection failure gracefully and return descriptive HTTP 400 / 403 / 422 errors instead of hanging threads.

---

## Remediation Plan & Acceptance Criteria

| Area | Component | Implementation | Verification Test |
|---|---|---|---|
| **P0-1** | Actuator Authorisation | Require `SUPERVISOR`/`ADMIN` for `arm_hardware=True` or `POST /sessions/{id}/arm`; default to `SimulatedActuator`; write audit events | `test_inspector_cannot_arm_hardware`, `test_supervisor_can_arm_hardware`, `test_hardware_audit_logging` |
| **P0-2** | Session Ownership | Track `user_id`; restrict status, stop, and WebSocket stream to owner or `SUPERVISOR`/`ADMIN` | `test_cross_user_session_access_rejected`, `test_owner_and_admin_allowed` |
| **P0-3** | WebSocket Limits | Reject frames > 5 MB, reject dimensions > 4K, rate limit > 35 FPS, reject malformed bytes | `test_ws_oversized_payload`, `test_ws_malformed_image`, `test_ws_rate_limit` |
| **P0-4** | RTSP Safety | Host allowlist check, block loopback/metadata, timeout on invalid RTSP | `test_rtsp_disallowed_host`, `test_rtsp_metadata_ip_blocked`, `test_rtsp_allowed_host` |
