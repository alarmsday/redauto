## ADDED Requirements

### Requirement: Overview Dashboard
The system SHALL display overview statistics on the main dashboard.

#### Scenario: Overview page display
- **WHEN** user accesses monitoring dashboard
- **THEN** dashboard SHALL show: total devices, online devices, task progress, processed posts count, exception count

### Requirement: Device Monitoring Page
The system SHALL display detailed status for each device.

#### Scenario: Device status display
- **WHEN** user views device monitoring page
- **THEN** system SHALL show per device: current status, runtime, task progress, current operation screenshot

### Requirement: Exception Alert Page
The system SHALL display all exception records.

#### Scenario: Exception list display
- **WHEN** user views exception alert page
- **THEN** system SHALL show: exception timestamp, device_id, exception type, handling status

#### Scenario: New exception notification
- **WHEN** new exception occurs
- **THEN** system SHALL trigger sound and desktop notification alert

### Requirement: Report Page
The system SHALL display historical task statistics.

#### Scenario: Statistics display
- **WHEN** user views report page
- **THEN** system SHALL show historical task statistics
- **AND** support exporting to Excel format

### Requirement: Web Access
The system SHALL be accessible via web browser on local network.

#### Scenario: Web access
- **WHEN** user accesses http://{computer_ip}:8080
- **THEN** system SHALL display monitoring dashboard
- **AND** support access from mobile browser
