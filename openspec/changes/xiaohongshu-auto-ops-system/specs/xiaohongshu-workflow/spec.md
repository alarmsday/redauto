## ADDED Requirements

### Requirement: User Matching
The system SHALL match posts from target users configured by Xiaohongshu ID or nickname.

#### Scenario: Xiaohongshu ID matching
- **WHEN** post author ID matches configured target user ID
- **THEN** system SHALL mark this post as a target post

#### Scenario: Nickname matching
- **WHEN** post author nickname matches configured target user nickname
- **THEN** system SHALL mark this post as a target post
- **AND** system SHALL support both exact and fuzzy matching modes

#### Scenario: Per-user daily limit
- **WHEN** target user has already been operated on 3 or more times today
- **THEN** system SHALL skip all remaining posts from that user for the rest of the day
- **AND** log the skip reason

### Requirement: Like Operation
The system SHALL click the like button on target posts.

#### Scenario: Like button interaction
- **WHEN** system identifies like button on post detail page
- **THEN** system SHALL click the like button
- **AND** record the operation to operation_records table

#### Scenario: Like operation skipped due to limit
- **WHEN** target user's daily operation limit is reached
- **THEN** system SHALL skip the like operation
- **AND** log the skip reason

### Requirement: Favorite Operation
The system SHALL click the favorite (收藏) button on target posts.

#### Scenario: Favorite button interaction
- **WHEN** system identifies favorite button on post detail page
- **THEN** system SHALL click the favorite button
- **AND** record the operation to operation_records table

#### Scenario: Favorite operation skipped due to limit
- **WHEN** target user's daily operation limit is reached
- **THEN** system SHALL skip the favorite operation
- **AND** log the skip reason

### Requirement: Screenshot Capture
The system SHALL capture screenshots at key workflow stages.

#### Scenario: Discovery page screenshot
- **WHEN** target user post is identified on discovery page
- **THEN** system SHALL capture discovery page screenshot and save to user's directory

#### Scenario: Operation completion screenshot
- **WHEN** like and favorite operations complete on post detail page
- **THEN** system SHALL capture operation completion screenshot and save to user's directory

### Requirement: Operation Frequency Control
The system SHALL control operation frequency to avoid excessive actions on same user.

#### Scenario: Daily operation limit check
- **WHEN** about to operate on target user's post
- **THEN** system SHALL query operation_records for today
- **AND** count operations for this target_user_id
- **AND** if count >= 3, skip the operation

#### Scenario: Minimum interval enforcement
- **WHEN** target user was last operated on less than 3 minutes ago
- **THEN** system SHALL wait until 3 minutes have passed before processing again

### Requirement: Browsing Simulation
The system SHALL simulate genuine user browsing behavior before operations.

#### Scenario: Image post browsing
- **WHEN** post contains multiple images
- **THEN** system SHALL swipe through all images with 2-5 seconds random停留 per image
- **AND** swipe trajectory SHALL include S-curve micro-offset

#### Scenario: Video post browsing
- **WHEN** post contains a video
- **THEN** system SHALL randomly seek to 2/3 to 90% of video duration
- **AND** watch for 10-30 seconds before proceeding

### Requirement: Post Processing Loop
The system SHALL continue scanning posts until all target users are processed or daily limits reached.

#### Scenario: Continue to next post
- **WHEN** current post is processed (like + favorite)
- **AND** target user's daily limit not reached
- **THEN** system SHALL return to discovery page and continue scanning

#### Scenario: Move to next user
- **WHEN** current user's daily limit is reached
- **THEN** system SHALL skip to next target user's posts
- **AND** continue processing other target users

#### Scenario: Random non-target interaction
- **WHEN** scanning discovery page
- **THEN** system SHALL occasionally interact with non-target posts
- **AND** simulate real user behavior to avoid detection
