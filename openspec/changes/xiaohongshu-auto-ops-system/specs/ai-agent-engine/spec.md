## ADDED Requirements

### Requirement: Exception Sensing
The AI Agent SHALL感知 and collect data when main workflow encounters exceptions.

#### Scenario: Screen capture on exception
- **WHEN** workflow exception occurs
- **THEN** system SHALL capture current screen as base64 encoded screenshot
- **AND** compute SHA256 hash of screenshot for case matching

#### Scenario: Control tree collection
- **WHEN** workflow exception occurs
- **THEN** system SHALL collect current page Poco control tree structure as JSON

#### Scenario: Log collection
- **WHEN** workflow exception occurs
- **THEN** system SHALL read the last 10 operation log entries

#### Scenario: Context packaging
- **WHEN** exception data is collected
- **THEN** system SHALL package data as: exception_type, exception_description, retry_count, screenshot_base64, control_tree_json, recent_logs

### Requirement: Case Library Retrieval
The AI Agent SHALL search case library before calling LLM.

#### Scenario: Exact screen match
- **WHEN** new exception occurs
- **AND** case library contains entry with identical screen_hash
- **THEN** system SHALL retrieve that case
- **AND** if case.success is true, apply the stored action directly

#### Scenario: Similar case match
- **WHEN** new exception occurs
- **AND** case library contains entries with same exception_type
- **AND** screen embedding cosine similarity > 0.85 with an existing case
- **THEN** system SHALL retrieve the highest-used-count matching case
- **AND** apply the stored action

#### Scenario: No matching case
- **WHEN** new exception occurs
- **AND** case library has no matching or similar cases
- **THEN** system SHALL call LLM for decision

### Requirement: LLM Decision Making
The AI Agent SHALL use LLM to analyze situation and generate handling instructions.

#### Scenario: Exception analysis with LLM
- **WHEN** case library has no suitable case
- **THEN** system SHALL send to Volcano Engine Doubao model with system prompt
- **AND** include: current screenshot, control tree, exception context, recent logs
- **AND** receive structured JSON instruction for next action

#### Scenario: LLM rate limiting
- **WHEN** multiple devices encounter exceptions simultaneously
- **THEN** system SHALL limit concurrent LLM calls to 3
- **AND** queue excess calls with 5-second timeout
- **AND** fall back to preset strategy if timeout exceeded

#### Scenario: Available actions
- **WHEN** LLM returns decision
- **THEN** returned instructions SHALL be from: click(x,y), swipe(x1,y1,x2,y2,duration), back(), restart_app(), wait(seconds), human_alert(reason), skip(reason)

### Requirement: Action Validation
The AI Agent SHALL validate LLM decisions before execution.

#### Scenario: Valid action format
- **WHEN** LLM returns an action instruction
- **THEN** system SHALL validate: action type is in allowed set, coordinates within device resolution bounds, duration within valid range

#### Scenario: Invalid action format
- **WHEN** LLM returns malformed or invalid action
- **THEN** system SHALL log the invalid response
- **AND** retry LLM call up to 2 times
- **AND** if all retries fail, trigger human_alert

### Requirement: Action Execution
The AI Agent SHALL execute validated actions and record results.

#### Scenario: Action execution
- **WHEN** action is validated
- **THEN** system SHALL execute the action via device control layer
- **AND** wait for result with 3-second timeout

#### Scenario: Execution success
- **WHEN** action executes successfully
- **THEN** system SHALL record success to case library if this was LLM-generated decision

#### Scenario: Execution failure
- **WHEN** action execution fails or times out
- **THEN** system SHALL record failure to case library
- **AND** retry from case library retrieval (not original LLM call)

### Requirement: Self-Learning
The AI Agent SHALL learn from successful and failed exception handling cases.

#### Scenario: Success case recording
- **WHEN** AI Agent successfully handles an exception using LLM decision
- **THEN** system SHALL record case to library with: exception_type, screen_hash, screen_embedding, control_tree, action_taken, success=true

#### Scenario: Failure case recording
- **WHEN** AI Agent fails to handle exception after applying stored case
- **THEN** system SHALL update case record: success=false, increment used_count

#### Scenario: Case library cleanup
- **WHEN** case library has entries older than 30 days with used_count < 3
- **THEN** system SHALL consider these for archival
- **AND** never delete cases completely, only mark as archived

### Requirement: Human Alert Escalation
The AI Agent SHALL trigger human intervention when automated handling fails.

#### Scenario: Consecutive AI failures
- **WHEN** 3 consecutive AI-handled exceptions fail on same device
- **THEN** system SHALL trigger human_alert with context summary

#### Scenario: Unhandleable exception
- **WHEN** exception type is identified as requiring human intervention (account banned, verification required)
- **THEN** system SHALL immediately trigger human_alert

#### Scenario: Human resolution
- **WHEN** human resolves the alert and clicks "Continue"
- **THEN** system SHALL resume workflow from current state
- **AND** record resolution to case library
