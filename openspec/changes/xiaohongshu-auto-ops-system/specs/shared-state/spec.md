## ADDED Requirements

### Requirement: Shared SQLite Database
The system SHALL use SQLite database for cross-process data sharing.

#### Scenario: Database location
- **WHEN** system starts
- **THEN** SQLite database SHALL be created at data/shared_state.db
- **AND** use WAL mode for concurrent read/write support

#### Scenario: Task queue management
- **WHEN** task is created
- **THEN** task SHALL be inserted into task_queue table
- **AND** include: target_user_id, target_nickname, device_id, status, created_at

#### Scenario: Operation record tracking
- **WHEN** any device performs like/favorite operation
- **THEN** operation SHALL be recorded to operation_records table
- **AND** include: target_user_id, device_id, operation_type, operated_at
- **AND** this record is visible to all processes

### Requirement: Operation Count Query
The system SHALL provide functions to query operation counts for frequency control.

#### Scenario: Daily operation count for user
- **WHEN** about to operate on target user
- **THEN** system SHALL query: SELECT COUNT(*) FROM operation_records WHERE target_user_id=? AND date(operated_at)=date('now')

#### Scenario: Check minimum interval
- **WHEN** about to operate on target user
- **THEN** system SHALL query last operation timestamp
- **AND** calculate time since last operation

### Requirement: Device Status Tracking
The system SHALL track device status in shared database.

#### Scenario: Heartbeat update
- **WHEN** device process is running
- **THEN** device SHALL update last_heartbeat every 5 seconds
- **AND** update current_task_id and status

#### Scenario: Device offline detection
- **WHEN** device heartbeat is older than 30 seconds
- **THEN** main process SHALL mark device as offline
- **AND** reassign its tasks

### Requirement: Status Push to Web Panel
The system SHALL push status updates to web dashboard via WebSocket.

#### Scenario: WebSocket connection
- **WHEN** web client connects to ws://host:8080/ws
- **THEN** client SHALL be added to subscribers list
- **AND** receive current state snapshot

#### Scenario: Status push
- **WHEN** device status changes (task start/complete/error)
- **THEN** main process SHALL broadcast update to all WebSocket subscribers
- **AND** include: device_id, status, progress, current_operation, timestamp

#### Scenario: Client disconnect
- **WHEN** WebSocket client disconnects
- **THEN** client SHALL be removed from subscribers list
- **AND** no memory leak occurs

### Requirement: Process-safe Operations
The system SHALL handle concurrent access safely.

#### Scenario: Concurrent task assignment
- **WHEN** two devices query for pending tasks simultaneously
- **THEN** database SHALL use row-level locking
- **AND** only one device receives each task

#### Scenario: Connection pool
- **WHEN** multiple processes need database access
- **THEN** each process SHALL use its own connection
- **AND** SQLite SHALL handle concurrency via WAL mode
