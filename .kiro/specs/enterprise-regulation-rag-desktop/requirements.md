# Requirements Document

## Introduction

This document specifies the requirements for the **Enterprise Regulation RAG Desktop** feature. The
feature wraps the existing Python Self-RAG engine (LangChain + LangGraph + ChromaDB) in a Tauri
desktop client (Rust shell hosting a React + TypeScript UI) that talks over local HTTP to a FastAPI
side-car service. The side-car adds a local account system (SQLite + bcrypt + JWT dual-token auth +
role-based access control), position-aware retrieval (query augmentation derived from the
authenticated user's profile), per-user query history, admin user/knowledge-base management, and a
three-column role-based UI with progressive disclosure.

These requirements are derived from the approved design document (`design.md`), which is the source of
truth. A guiding constraint is **zero RAG-core changes**: all new behavior is additive and the
existing `RAG2API`, LangGraph nodes, settings factory, and ingestion loader are reused unchanged.

## Glossary

- **Desktop_Shell**: The Tauri Rust shell responsible for the native window and the side-car process lifecycle.
- **Sidecar_Service**: The local FastAPI + Uvicorn service bound to `127.0.0.1:8756` that hosts all API routers.
- **Auth_Service**: The authentication subsystem that hashes/verifies passwords and issues/validates JWTs.
- **RBAC_Guard**: The authorization mechanism (`require_role`) that gates routes by role.
- **Profile_Injector**: The pure function `build_augmented_query(profile, question)` that produces a position-aware augmented query.
- **Query_Service**: The `/ask` router that orchestrates a single employee question end-to-end.
- **History_Service**: The router that lists, retrieves, and deletes per-user query history.
- **Admin_Service**: The admin-only router for user CRUD.
- **KB_Service**: The router that manages knowledge-base documents via the existing ingestion loader.
- **System_Service**: The router exposing health and statistics.
- **UI_Client**: The React + TypeScript application rendered inside the Tauri WebView.
- **RAG_Core**: The existing, unchanged `RAG2API` singleton and its LangGraph Self-RAG workflow.
- **UserContext**: The authenticated user identity (id, username, role, position, tasks) resolved from a validated access token.
- **UserProfile**: The position (职位) and tasks (任务) pair used for query augmentation.
- **Access_Token**: A short-lived JWT carrying user claims (sub, username, role, position, tasks, type=access).
- **Refresh_Token**: A long-lived JWT persisted in SQLite to support revocation.
- **QueryHistory**: A per-user SQLite record storing the original question, answer, grade, iterations, success, and source count.
- **Admin**: A user whose role is "admin".
- **Employee**: A user whose role is "employee".
- **Supported_Extension**: A knowledge-base file extension accepted by the loader (`.txt`, `.md`, `.rst`, `.log`).
- **Confidence_Badge**: A UI element deriving a trust label from `grade` + `iterations`.
- **Relevance_Label**: A human-readable band (高/中/低) translated from a source's cosine similarity score.
- **Developer_Mode**: An admin-only UI toggle that reveals engineering metrics.

## Requirements

### Requirement 1: Desktop Client and Side-car Lifecycle

**User Story:** As an employee, I want a desktop application that manages a local backend service automatically, so that I can use the regulation query system without manual server setup.

#### Acceptance Criteria

1. WHEN the Desktop_Shell starts, THE Desktop_Shell SHALL spawn the Sidecar_Service as a child process.
2. THE Sidecar_Service SHALL bind only to the loopback address `127.0.0.1` on port `8756`.
3. WHILE the Desktop_Shell is running, THE Desktop_Shell SHALL monitor the Sidecar_Service process status.
4. THE UI_Client SHALL send all API requests to `http://127.0.0.1:8756`.
5. WHEN the UI_Client holds an Access_Token, THE UI_Client SHALL attach it as an `Authorization: Bearer` header on each API request.

### Requirement 2: Password Hashing and Storage

**User Story:** As a system, I want all passwords stored as bcrypt hashes, so that credentials are never exposed in plaintext.

#### Acceptance Criteria

1. WHEN a user account is created, THE Auth_Service SHALL store the password as a bcrypt hash.
2. THE Auth_Service SHALL store the `password_hash` field as a bcrypt hash and never as plaintext.
3. WHEN a plaintext password is verified against a stored hash, THE Auth_Service SHALL return true if and only if the plaintext matches the hash that produced it.
4. THE Auth_Service SHALL exclude plaintext passwords from all log output.

### Requirement 3: Password Policy

**User Story:** As a system, I want to enforce a password policy, so that accounts are protected by sufficiently strong passwords.

#### Acceptance Criteria

1. IF a submitted password has fewer than 8 characters, THEN THE Auth_Service SHALL reject the password.
2. IF a submitted password does not contain at least one letter and at least one digit, THEN THE Auth_Service SHALL reject the password.
3. WHEN a submitted password has at least 8 characters and contains at least one letter and at least one digit, THE Auth_Service SHALL accept the password.

### Requirement 4: Login and Dual-Token Issuance

**User Story:** As an employee, I want to log in with my username and password, so that I receive tokens that authorize my subsequent requests.

#### Acceptance Criteria

1. WHEN a login request presents a valid username and matching password, THE Auth_Service SHALL issue an Access_Token and a Refresh_Token and return the user role.
2. WHEN an Access_Token is issued, THE Auth_Service SHALL embed the claims id, username, role, position, and tasks in the token.
3. WHEN a Refresh_Token is issued, THE Auth_Service SHALL persist the Refresh_Token in SQLite to support revocation.
4. IF a login request presents an unknown username or a non-matching password, THEN THE Auth_Service SHALL respond with HTTP 401 and a generic error message.

### Requirement 5: Token Validation and Refresh

**User Story:** As an employee, I want my session to be validated on every protected request and renewable, so that I stay authenticated without re-entering credentials frequently.

#### Acceptance Criteria

1. WHEN a request to a protected route presents a valid, unexpired Access_Token, THE Auth_Service SHALL resolve a UserContext from the token claims.
2. IF a request to a protected route presents a missing, malformed, or expired token, THEN THE Auth_Service SHALL respond with HTTP 401.
3. IF a token presented to a protected route is not of type "access", THEN THE Auth_Service SHALL respond with HTTP 401.
4. WHEN a valid, non-revoked Refresh_Token is presented to the `/auth/refresh` endpoint, THE Auth_Service SHALL issue a new Access_Token.
5. IF a presented Refresh_Token is revoked or expired, THEN THE Auth_Service SHALL respond with HTTP 401.

### Requirement 6: Role-Based Access Control

**User Story:** As a system, I want to restrict routes by role, so that only authorized users perform privileged operations.

#### Acceptance Criteria

1. WHERE a route is restricted to one or more roles, THE RBAC_Guard SHALL allow the request only when the UserContext role is among the allowed roles.
2. IF an Employee requests a route restricted to Admin, THEN THE RBAC_Guard SHALL respond with HTTP 403.
3. WHEN an Admin requests a route restricted to Admin, THE RBAC_Guard SHALL allow the request.
4. WHERE a route requires authentication but no specific role, THE RBAC_Guard SHALL allow any request bearing a valid Access_Token.

### Requirement 7: Initial Admin Bootstrap

**User Story:** As a system operator, I want an initial admin account seeded on first run, so that the system is administrable from the start without manual database edits.

#### Acceptance Criteria

1. WHEN the Sidecar_Service initializes and no Admin account exists, THE Auth_Service SHALL create a single Admin account from configured environment variables.
2. WHEN the Sidecar_Service initializes and an Admin account already exists, THE Auth_Service SHALL NOT create an additional bootstrap Admin account.
3. WHEN the bootstrap Admin logs in for the first time, THE Auth_Service SHALL require the bootstrap Admin to change the password before normal operation.

### Requirement 8: Position-Aware Query Augmentation

**User Story:** As an employee, I want retrieval to be tailored to my position and tasks, so that the answers reference regulations relevant to my role.

#### Acceptance Criteria

1. WHEN an employee question is processed, THE Query_Service SHALL derive the UserProfile (position + tasks) from the validated Access_Token, not from any client-supplied profile.
2. WHEN the Profile_Injector builds an augmented query, THE Profile_Injector SHALL include the original question text within the augmented query so the original question remains the dominant clause.
3. THE Profile_Injector SHALL be a pure function that returns the same augmented query for the same UserProfile and question inputs.
4. WHERE the UserProfile position is empty and the tasks list is empty, THE Profile_Injector SHALL still produce an augmented query containing the original question.
5. WHEN the Profile_Injector includes tasks, THE Profile_Injector SHALL omit task entries that are empty or whitespace-only.
6. THE Query_Service SHALL pass the augmented query to RAG_Core without modifying RAG_Core.

### Requirement 9: Query Execution and Response

**User Story:** As an employee, I want to ask a regulation question and receive a structured answer with supporting sources, so that I can trust and verify the response.

#### Acceptance Criteria

1. WHEN a valid question is submitted to `/ask`, THE Query_Service SHALL invoke RAG_Core with the augmented query and return answer, grade, reason, iterations, success, and sources.
2. IF a question is empty or whitespace-only, THEN THE Query_Service SHALL respond with HTTP 422.
3. IF RAG_Core returns success=false, THEN THE Query_Service SHALL respond with HTTP 200 carrying success=false and the error text in the answer field.
4. WHEN the Query_Service maps the RAG_Core result, THE Query_Service SHALL populate the sources list from the returned context.

### Requirement 10: Query History Persistence

**User Story:** As an employee, I want my questions and answers recorded, so that I can revisit previous conversations.

#### Acceptance Criteria

1. WHEN the Query_Service returns a response for `/ask`, THE Query_Service SHALL attempt to persist a QueryHistory record for the requesting user.
2. WHEN a QueryHistory record is persisted, THE Query_Service SHALL store the original employee question and never the augmented query.
3. WHEN a QueryHistory record is persisted, THE Query_Service SHALL store the answer, grade, iterations, success, and source count.
4. IF persisting a QueryHistory record fails, THEN THE Query_Service SHALL log the failure and return the `/ask` response unchanged.

### Requirement 11: Query History Retrieval and Isolation

**User Story:** As an employee, I want to view and manage only my own query history, so that my conversations remain private.

#### Acceptance Criteria

1. WHEN an employee requests `GET /history`, THE History_Service SHALL return only QueryHistory records whose user_id matches the requester's id resolved from the Access_Token.
2. WHEN the History_Service returns a history list, THE History_Service SHALL order records by creation time newest first and apply the requested pagination.
3. WHEN an employee requests `GET /history/{id}` for a record they own, THE History_Service SHALL return that record.
4. IF an employee requests `GET /history/{id}` for a non-existent record or a record owned by another user, THEN THE History_Service SHALL respond with HTTP 404.
5. WHEN an employee requests `DELETE /history/{id}` for a record they own, THE History_Service SHALL delete that record.
6. IF an employee requests `DELETE /history/{id}` for a non-existent record or a record owned by another user, THEN THE History_Service SHALL respond with HTTP 404.
7. WHERE the requester is an Admin, THE History_Service SHALL allow `GET /admin/history` to list all users' history.

### Requirement 12: Admin User Management

**User Story:** As an admin, I want to create, read, update, and delete employee accounts including their position and tasks, so that retrieval is correctly tailored per employee.

#### Acceptance Criteria

1. WHERE the requester is an Admin, THE Admin_Service SHALL allow create, list, read, update, and delete operations on user accounts.
2. WHEN an Admin creates a user, THE Admin_Service SHALL store the assigned position and tasks for that user.
3. WHEN an Admin updates a user's position or tasks, THE Admin_Service SHALL persist the updated values.
4. IF an Admin creates a user with a username that already exists, THEN THE Admin_Service SHALL respond with HTTP 409.
5. IF an Employee requests any `/admin/users` operation, THEN THE RBAC_Guard SHALL respond with HTTP 403.

### Requirement 13: Knowledge-Base Management

**User Story:** As an admin, I want to upload, list, and delete regulation documents, so that the knowledge base stays current.

#### Acceptance Criteria

1. WHERE the requester is an Admin, THE KB_Service SHALL accept document uploads via `/kb/upload`.
2. WHEN an uploaded file has a Supported_Extension, THE KB_Service SHALL persist the file and vectorize it via the existing ingestion loader, returning the filename and number of chunks added.
3. IF an uploaded file has an extension that is not a Supported_Extension, THEN THE KB_Service SHALL respond with HTTP 415.
4. WHEN any authenticated user requests `GET /kb/list`, THE KB_Service SHALL return the list of knowledge-base entries.
5. WHERE the requester is an Admin, THE KB_Service SHALL delete the identified knowledge-base entry on `DELETE /kb/{id}`.
6. IF an Employee requests `/kb/upload` or `DELETE /kb/{id}`, THEN THE RBAC_Guard SHALL respond with HTTP 403.

### Requirement 14: Three-Column Role-Based Layout

**User Story:** As an employee, I want a focused three-column interface, so that I can see my profile, ask questions, and review sources without engineering clutter.

#### Acceptance Criteria

1. THE UI_Client SHALL render a three-column layout with a left column (profile card, KB scope selector, session history), a middle column (chat window, confidence badge), and a right collapsible column (source panel).
2. THE UI_Client SHALL display the logged-in user's position and tasks in the profile card as read-only for Employee users.
3. WHEN an employee selects a session history item, THE UI_Client SHALL reload that question and answer into the chat view.
4. THE UI_Client SHALL populate the session history from `GET /history` showing the requester's own records newest first.

### Requirement 15: Confidence Badge and Source Relevance

**User Story:** As an employee, I want trust signals in plain language, so that I can gauge answer reliability without seeing raw scores.

#### Acceptance Criteria

1. WHEN the UI_Client renders a Confidence_Badge, THE UI_Client SHALL derive the trust level from the answer's grade and iterations and SHALL NOT display raw numeric scores.
2. WHERE the answer grade is not "YES", THE UI_Client SHALL render the Confidence_Badge at the 低 level with a manual-confirmation message.
3. WHEN the UI_Client renders a source card, THE UI_Client SHALL display a Relevance_Label of 高, 中, or 低 translated from the cosine score and SHALL NOT display the raw numeric score.
4. WHEN a cosine score is translated to a Relevance_Label, THE UI_Client SHALL map higher scores to higher relevance bands monotonically.

### Requirement 16: Admin Developer Mode and Advanced Settings

**User Story:** As an admin, I want optional access to engineering metrics and tuning settings, so that I can diagnose and configure the system without exposing detail to employees.

#### Acceptance Criteria

1. WHERE the user role is Admin and Developer_Mode is enabled, THE UI_Client SHALL reveal the Developer Metrics panel showing chunks, raw scores, token cost, and latency.
2. WHERE the user role is Employee, THE UI_Client SHALL hide the Developer_Mode toggle and the Developer Metrics panel.
3. IF an Employee attempts to enable Developer_Mode, THEN THE UI_Client SHALL keep Developer_Mode disabled.
4. WHERE the user role is Admin, THE UI_Client SHALL expose Advanced Settings for top_k, the reranker flag, and the hybrid search flag.
5. WHERE the user role is Admin, THE UI_Client SHALL provide a system monitoring and usage view.

### Requirement 17: Security Guarantees

**User Story:** As a system operator, I want the service hardened against local and configuration risks, so that credentials and data stay protected.

#### Acceptance Criteria

1. THE Sidecar_Service SHALL accept connections only on the loopback interface `127.0.0.1`.
2. THE Auth_Service SHALL load the JWT HS256 signing secret from an environment variable or secure local file and SHALL NOT use a hard-coded secret.
3. THE Auth_Service SHALL sign and validate JWTs using the HS256 algorithm.
4. THE Auth_Service SHALL never write plaintext passwords to logs or persistent storage.

### Requirement 18: Dual-Mode Model Backend

**User Story:** As a system operator, I want to switch between cloud and local model backends through configuration, so that I can run the system in either environment without code changes.

#### Acceptance Criteria

1. THE Sidecar_Service SHALL obtain model access exclusively through the existing settings factory (get_llm / get_embeddings).
2. WHERE the configured mode is CLOUD, THE System_Service SHALL surface token cost and latency as meaningful usage metrics.
3. WHERE the configured mode is LOCAL, THE System_Service SHALL surface token cost and latency as informational only.
4. THE Sidecar_Service SHALL NOT import model classes directly outside the settings factory.
