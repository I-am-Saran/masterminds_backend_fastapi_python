from enum import Enum

#******************BUG STATUS***************************
class BugStatus(str, Enum):
    OPEN = "Open"
    DEV_IN_PROGRESS = "Dev In Progress"
    RESOLVED = "Resolved"
    NEED_CLARIFICATION_FROM_QA = "Need Clarification from QA"
    NEED_CLARIFICATION_FROM_DEV = "Need Clarification from Dev"
    NEED_CLARIFICATION_FROM_PROD = "Need Clarification from Prod"
    NEED_CLARIFICATION_FROM_DEVOPS = "Need Clarification from DevOps"
    NEED_CLARIFICATION_FROM_COMPLIANCE = "Need Clarification from Compliance"
    NEED_CLARIFICATION_FROM_SECURITY = "Need Clarification from Security"
    NEED_CLARIFICATION_FROM_INFRA = "Need Clarification from Infra"
    NEED_CLARIFICATION_FROM_VENDOR = "Need Clarification from Vendor"
    REVIEW_IN_PROGRESS = "Review in Progress"
    DUPLICATE = "Duplicate"
    QA_PASSED = "QA Passed"
    CLOSED = "Closed"
    QA_REOPENED = "QA Reopened"
    READY_FOR_QA = "Ready for QA"
    QA_IN_PROGRESS = "QA In Progress"
    DEFERRED = "Deferred"
    DESCOPED = "Descoped"
    INVALID = "Invalid"
    READY_FOR_UAT = "Ready for UAT"
    REJECT = "Reject"
    UAT_PASSED = "UAT Passed"
    UAT_REOPENED = "UAT Reopened"
    READY_FOR_PRODUCTION = "Ready for Production"

class Priority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    BLOCKER = "Blocker"

class Severity(str, Enum):
    TRIVIAL = "Trivial"
    MINOR = "Minor"
    MAJOR = "Major"
    CRITICAL = "Critical"
    BLOCKER = "Blocker"

class DefectType(str, Enum):
    FUNCTIONAL = "Functional"
    UI = "UI"
    PERFORMANCE = "Performance"
    SECURITY = "Security"
    COMPATIBILITY = "Compatibility"

class Resolution(str, Enum):
    UNRESOLVED = "Unresolved"
    FIXED = "Fixed"
    WONT_FIX = "Won't Fix"
    DUPLICATE = "Duplicate"
    INVALID = "Invalid"
    WORKS_AS_DESIGNED = "Works as Designed"

class AutomationIntent(str, Enum):
    YES = "Yes"
    NO = "No"

class AutomationStatus(str, Enum):
    PENDING = "Pending"
    AUTOMATED = "Automated"
    SKIPPED = "Skipped"
    IN_PROGRESS = "In Progress"

class DeviceType(str, Enum):
    WEB = "Web"
    MOBILE = "Mobile"
    TABLET = "Tablet"
    DESKTOP = "Desktop"

class BrowserTested(str, Enum):
    CHROME = "Chrome"
    FIREFOX = "Firefox"
    EDGE = "Edge"
    SAFARI = "Safari"
    OPERA = "Opera"
    IE = "Internet Explorer"

class OS(str, Enum):
    WINDOWS = "Windows"
    MACOS = "MacOS"
    LINUX = "Linux"
    ANDROID = "Android"
    IOS = "iOS"
    OTHER = "Other"

class Hardware(str, Enum):
    PC = "PC"
    MOBILE = "Mobile"
    TABLET = "Tablet"
    OTHER = "Other"

class TestingPhase(str, Enum):
    IDEATION = "Ideation"
    PRE_PROD_TESTING = "Pre prod testing"
    PRODUCTION_TESTING = "Production testing"
    SYSTEM_INTEGRATION_TESTING = "System integration testing"
    SYSTEM_TESTING = "System testing"
    TECHNICAL_DESIGN = "Technical Design"
    UIUX_DESIGN = "UIUX Design"
    UNIT = "Unit"
    UNIT_TESTING = "Unit testing"
    USER_ACCEPTANCE_TESTING = "User acceptance testing"
    REGRESSION = "Regression"
    UAT = "UAT"
    SMOKE = "Smoke"
    INTEGRATION = "Integration"

class TicketType(str, Enum):
    BUG = "Bug"
    CHANGE_REQUEST = "Change Request"
    SUGGESTIONS = "Suggestions"
    NEW_FEATURE = "New Feature"
    ENHANCEMENT = "Enhancement"

class Classification(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"

class InternallyReviewed(str, Enum):
    YES = "Yes"
    NO = "No"

class ReviewedInTriage(str, Enum):
    YES = "Yes"
    NO = "No"

class RootCauseCategory(str, Enum):
    CODE_ISSUE = "Code Issue"
    DESIGN_ISSUE = "Design Issue"
    CONFIGURATION_ISSUE = "Configuration Issue"
    ENVIRONMENT_ISSUE = "Environment Issue"
    DATA_ISSUE = "Data Issue"
    UNKNOWN = "Unknown"
