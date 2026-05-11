## ADDED Requirements

### Requirement: Directory Structure
The system SHALL create independent directories for each account.

#### Scenario: Account directory creation
- **WHEN** task starts for an account
- **THEN** system SHALL create directory structure: output/{account_name}/

#### Scenario: Subdirectory creation
- **WHEN** account directory is created
- **THEN** system SHALL create subdirectories: 发现页截图/, 操作完成截图/, 异常报告/

### Requirement: Screenshot Naming Convention
The system SHALL save screenshots with standardized naming format.

#### Scenario: Screenshot filename format
- **WHEN** system saves screenshot
- **THEN** filename SHALL follow format: {device_id}_{user_nickname}_{page_type}_{timestamp}.png
- **AND** timestamp format SHALL be YYYYMMDD_HHMMSS

### Requirement: Operation Logging
The system SHALL record all operations to log files.

#### Scenario: Log file creation
- **WHEN** operations are performed for an account
- **THEN** system SHALL create log file at output/{account_name}/操作日志.log

#### Scenario: Log entry format
- **WHEN** operation is executed
- **THEN** log entry SHALL contain: timestamp, device_id, operation_type, status, duration, notes

### Requirement: Statistics Report Generation
The system SHALL generate statistics report after task completion.

#### Scenario: Report content
- **WHEN** task completes
- **THEN** system SHALL generate report containing: total task duration, number of devices, total users processed, total posts processed, successful likes, successful favorites, exception count by type, AI Agent success rate

#### Scenario: Report filename
- **WHEN** task completes
- **THEN** report SHALL be saved as 任务统计报告_{timestamp}.md
