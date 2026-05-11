## ADDED Requirements

### Requirement: Account Pool Configuration
The system SHALL manage multiple Xiaohongshu accounts through a YAML configuration file.

#### Scenario: Account configuration structure
- **WHEN** system loads account configuration
- **THEN** it SHALL support the following fields per account: account (phone/ID), password, device (optional device binding), status (active/inactive)

#### Scenario: Account status toggle
- **WHEN** account status is set to "inactive"
- **THEN** system SHALL skip assigning tasks to that account

### Requirement: Automatic Login
The system SHALL automatically log in to Xiaohongshu using configured credentials.

#### Scenario: Auto-fill login credentials
- **WHEN** device starts and Xiaohongshu app is launched
- **THEN** system SHALL automatically fill in the configured account and password

#### Scenario: Verification code handling
- **WHEN** login requires verification code
- **THEN** system SHALL trigger desktop notification and sound alert
- **AND** pause execution until human enters the code
- **AND** automatically continue after code entry

### Requirement: Account Switching
The system SHALL support automatic account switching based on configured rotation period.

#### Scenario: Scheduled account switch
- **WHEN** configured rotation period elapses
- **THEN** system SHALL log out current account and log in the next account in sequence

### Requirement: Login State Validation
The system SHALL validate login state before each task execution.

#### Scenario: Expired session detection
- **WHEN** task starts and login session is expired
- **THEN** system SHALL automatically perform re-login using configured credentials
