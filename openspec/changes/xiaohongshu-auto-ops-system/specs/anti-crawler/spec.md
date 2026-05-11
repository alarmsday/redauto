## ADDED Requirements

### Requirement: Operation Rate Limiting
The system SHALL limit operations per device to avoid excessive activity.

#### Scenario: Per-device rate limit
- **WHEN** single device is running
- **THEN** operations SHALL be limited to 10-15 per minute
- **AND** this includes all swipe, click, and navigation actions

### Requirement: Per-User Daily Limit (Anti-Crawler Protection)
The system SHALL limit total operations on each target user per day.

#### Scenario: Target user daily limit enforcement
- **WHEN** target user has been operated on 3 times today (like + collect per post = 1 operation)
- **THEN** all posts from that user SHALL be skipped for the remainder of the day
- **AND** this limit is shared across all devices (via SQLite operation_records)

#### Scenario: Limit shared across devices
- **WHEN** device A operates on target user X at 10:00
- **AND** device B encounters target user X at 10:30
- **THEN** device B SHALL see the operation count already includes device A's operation
- **AND** adjust its processing accordingly

### Requirement: Minimum Interval Between Operations
The system SHALL enforce minimum time interval between operations on same user.

#### Scenario: Interval enforcement per user
- **WHEN** target user was last operated on less than 3 minutes ago
- **THEN** system SHALL wait until 3 minutes have passed before processing again
- **AND** this is checked via operation_records timestamp

### Requirement: Device Feature Diversity
The system SHALL ensure devices use different accounts to avoid correlation.

#### Scenario: Independent account per device
- **WHEN** multiple devices are configured
- **THEN** each device SHALL use a unique Xiaohongshu account
- **AND** no two devices SHALL share the same account

### Requirement: Random Behavior Variation
The system SHALL introduce randomness in timing and behavior patterns.

#### Scenario: Random停留 time
- **WHEN** viewing posts
- **THEN**停留 time SHALL vary randomly from 2-5 seconds per image
- **AND** some posts viewed longer, some shorter

#### Scenario: Non-target post interaction
- **WHEN** browsing discovery page
- **THEN** system SHALL occasionally interact with non-target posts to simulate real user behavior
- **AND** not only process target user posts

### Requirement: Daily Limit Clarification
The 3-times-per-user-per-day limit is a trade-off between business goals and anti-detection.

#### Scenario: Business vs anti-crawler balance
- **WHEN** business requirement wants "all posts processed"
- **AND** anti-crawler limit is "3 operations per user per day"
- **THEN** system SHALL prioritize anti-crawler limits
- **AND** accept that not all posts may be processed on heavily posted users
- **AND** log when posts are skipped due to daily limit

### Requirement: Account Protection
The system SHALL implement additional measures to protect account longevity.

#### Scenario: New account ramping
- **WHEN** account is less than 7 days old
- **THEN** system SHALL limit daily operations to 20 total
- **AND** skip heavy posting users

#### Scenario: Daily volume cap per account
- **WHEN** account has processed 50-100 posts today
- **THEN** system SHALL pause that account until next day
- **AND** continue with other accounts if available
