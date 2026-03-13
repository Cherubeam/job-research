# Understanding Python Concepts in config.py

This guide explains the Python syntax and patterns used in the configuration system.

---

## 1. Type Hints and Default Values

### Basic Syntax
```python
search_stepstone: bool = True
```

Let's break this down:

| Part | Meaning |
|------|---------|
| `search_stepstone` | **Variable name** - what we call it |
| `:` | **Type hint separator** - coming up next is the type |
| `bool` | **Type hint** - this should be a boolean (True/False) |
| `=` | **Assignment operator** - assign a value |
| `True` | **Default value** - use this if nothing else is provided |

### Another Example
```python
keywords: str = "AI Engineer"
```

- `keywords` - variable name
- `str` - type hint (string/text)
- `"AI Engineer"` - default value

### Why Type Hints?
Type hints help you (and Python) understand what type of data each variable should hold. They don't enforce anything, but they help catch mistakes:

```python
# Type hint says it should be bool
search_stepstone: bool = True

# Later in code, if you accidentally assign text:
search_stepstone = "yes"  # Python allows this, but it violates your hint
```

IDEs and tools can catch these mistakes before runtime.

---

## 2. @dataclass Decorator

### What It Is
`@dataclass` is a **decorator** - a Python feature that automatically generates boilerplate code for you.

### Without @dataclass (manual)
```python
class JobBoardConfig:
    def __init__(self, search_stepstone=True, search_linkedin=True, search_indeed=True):
        self.search_stepstone = search_stepstone
        self.search_linkedin = search_linkedin
        self.search_indeed = search_indeed

    def __repr__(self):
        return f"JobBoardConfig(search_stepstone={self.search_stepstone}, search_linkedin={self.search_linkedin}, ...)"
```

That's a lot of repetitive code!

### With @dataclass (automatic)
```python
@dataclass
class JobBoardConfig:
    """Configuration for job board searches"""
    search_stepstone: bool = True
    search_linkedin: bool = True
    search_indeed: bool = True
```

The `@dataclass` decorator automatically creates:
1. ✅ The `__init__()` method (constructor)
2. ✅ The `__repr__()` method (string representation)
3. ✅ The `__eq__()` method (equality comparison)
4. ✅ Default values handling

### How to Use It
```python
# Create an instance with defaults
config = JobBoardConfig()
print(config.search_stepstone)  # True

# Override defaults
config = JobBoardConfig(search_stepstone=False, search_linkedin=True)
print(config.search_stepstone)  # False
print(config.search_linkedin)   # True
```

### Benefits
- **Less code** - No need to write `__init__()` and `__repr__()`
- **Cleaner** - Easy to read and understand
- **Less error-prone** - Fewer places to make mistakes

---

## 3. @classmethod Decorator

### What It Is
A `@classmethod` is a special method that:
- Takes the **class itself** as the first argument (called `cls`)
- Can be called on the class without creating an instance
- Often used to create alternative constructors

### Without @classmethod (manual instance creation)
```python
# User has to create Config object first
config = Config()  # Create empty config
# Then they have to manually load from .env...
# (This would require writing custom code)
```

### With @classmethod (alternative constructor)
```python
@classmethod
def from_env(cls) -> "Config":
    """Load configuration from environment variables"""
    load_dotenv()

    search_params = JobSearchParams(
        keywords=os.getenv("JOB_KEYWORDS", "AI Engineer"),
        # ... more loading code
    )

    return cls(
        search_params=search_params,
        # ... more parameters
    )

# Usage
config = Config.from_env()  # Load from .env in one line!
```

### Key Differences

**Regular method (instance method):**
```python
class Config:
    def to_dict(self) -> dict:
        """self refers to the instance"""
        return {...}

config = Config()
result = config.to_dict()  # Call on instance
```

**Class method:**
```python
class Config:
    @classmethod
    def from_env(cls) -> "Config":
        """cls refers to the class itself"""
        return cls(...)  # Returns new instance

result = Config.from_env()  # Call on class, not instance
```

### Why Use @classmethod?
Alternative constructors! You can create objects in different ways:

```python
# Way 1: Create from environment variables
config = Config.from_env()

# Way 2: Create from JSON file
config = Config.from_json(Path("config.json"))

# Way 3: Create with defaults
config = Config()
```

Each method is a different way to initialize the object.

---

## 4. Defaults vs .env - How They Work Together

This is the key concept to understand!

### The Hierarchy (Priority Order)

```
User Input (Gradio UI) - HIGHEST PRIORITY
        ↓
Environment Variables (.env file)
        ↓
Hard-coded Defaults (in config.py)
        ↓
Built-in Python Defaults - LOWEST PRIORITY
```

### Step-by-Step Example

#### Step 1: Define Hard-coded Defaults (config.py)
```python
@dataclass
class JobBoardConfig:
    search_stepstone: bool = True  # DEFAULT: true
```

#### Step 2: Define .env Overrides
```bash
# .env file
SEARCH_STEPSTONE=false  # OVERRIDE the default
```

#### Step 3: Load from .env Using from_env()
```python
@classmethod
def from_env(cls) -> "Config":
    # Read from .env, use hard-coded default if not found
    search_stepstone = os.getenv("SEARCH_STEPSTONE", "true").lower() == "true"
    #                  ↑                              ↑
    #                  Read from .env              If not in .env, use "true"

    return cls(
        search_stepstone=search_stepstone,  # Use the value from .env (or default)
    )
```

#### Step 4: User Can Override in UI
```python
# User fills form in Gradio UI and clicks Search
# app.py passes the UI values to run_job_research()

config.search_stepstone = False  # User's choice overrides everything
```

### Complete Flow Diagram

```
Default in code:        search_stepstone = True
                                 ↓
.env file exists?      SEARCH_STEPSTONE=false
                        (overrides code default)
                                 ↓
from_env() reads:      search_stepstone = False
                                 ↓
User enters in UI:     "Actually, search it"
                                 ↓
app.py receives:       search_stepstone = True
                        (user's choice wins!)
```

### Concrete Example

**config.py (hard-coded defaults):**
```python
@dataclass
class JobBoardConfig:
    search_stepstone: bool = True      # DEFAULT
    search_linkedin: bool = True       # DEFAULT
```

**.env file (override defaults):**
```bash
SEARCH_STEPSTONE=false
# SEARCH_LINKEDIN not specified, so uses default (True)
```

**Loading in code:**
```python
config = Config.from_env()  # Reads .env

print(config.job_boards.search_stepstone)  # False (from .env)
print(config.job_boards.search_linkedin)   # True (from default, .env doesn't override)
```

**User changes in UI:**
```python
# User fills form:
# - StepStone: ON
# - LinkedIn: OFF

# app.py receives:
config.job_boards.search_stepstone = True   # User choice
config.job_boards.search_linkedin = False   # User choice
```

---

## 5. Special Syntax: field() and default_factory

### Problem with Mutable Defaults

In Python, never use mutable defaults like this:

```python
# ❌ WRONG - All instances share the same list!
class JobSearchParams:
    def __init__(self, industries=[]):
        self.industries = industries

param1 = JobSearchParams()
param1.industries.append("Tech")

param2 = JobSearchParams()
print(param2.industries)  # ["Tech"] - OOPS! Shared!
```

### Solution: Use field() with default_factory

```python
from dataclasses import dataclass, field

@dataclass
class JobSearchParams:
    industries: list[str] = field(default_factory=lambda: ["All"])
    #                       ↑                          ↑
    #                    Use field()            Provide a callable
```

### How default_factory Works

```python
# default_factory takes a function
# That function is called EACH TIME to create a new value

# Version 1: Using lambda
field(default_factory=lambda: ["All"])  # Creates ["All"] each time

# Version 2: Using list (simpler)
field(default_factory=list)  # Creates [] each time
```

### Real Example
```python
@dataclass
class JobSearchParams:
    industries: list[str] = field(default_factory=lambda: ["All"])

# Each instance gets its own list
param1 = JobSearchParams()
param1.industries.append("Tech")

param2 = JobSearchParams()
print(param2.industries)  # ["All"] - separate list!
```

---

## 6. Optional Type Hint

### What Optional Means

```python
email_recipient: Optional[str] = None
```

This means:
- The variable can be a string (`str`)
- **OR** it can be `None` (nothing/null)
- The default is `None`

### Visual

```
┌─────────────────────────────┐
│  Optional[str]              │
│ ├─ str: "user@example.com"  │  <- Can be a string
│ └─ None: no value           │  <- Or None
└─────────────────────────────┘
```

### Practical Example
```python
email_recipient: Optional[str] = None

# Valid:
email_recipient = "user@example.com"  # ✅ Correct type
email_recipient = None                # ✅ Also correct (Optional allows this)

# Invalid:
email_recipient = 123  # ❌ Wrong type (not str or None)
```

---

## Summary Table

| Concept | Syntax | Purpose |
|---------|--------|---------|
| **Type Hint** | `name: type = default` | Declare what type a variable should be |
| **@dataclass** | `@dataclass` above class | Auto-generate `__init__`, `__repr__`, etc. |
| **@classmethod** | `@classmethod def method(cls):` | Alternative constructor (called on class) |
| **field()** | `field(default_factory=list)` | Safe default for mutable types |
| **Optional** | `Optional[str]` | Variable can be str OR None |

---

## How It All Works Together in Your Project

```python
# 1. Define structure with @dataclass and type hints
@dataclass
class JobBoardConfig:
    search_stepstone: bool = True  # Has default

# 2. Create alternative constructor with @classmethod
    @classmethod
    def from_env(cls):
        # Reads .env, uses hard-coded default if not found
        value = os.getenv("SEARCH_STEPSTONE", "true").lower() == "true"
        return cls(search_stepstone=value)

# 3. Use it
config = JobBoardConfig.from_env()  # Loads from .env
config.search_stepstone = False     # User can override
```

The flow:
1. **Defaults in code** provide fallback values
2. **@classmethod loads from .env** to override defaults
3. **User input in UI** overrides everything

---

## Practice Questions

Try to answer these to test your understanding:

1. What does `keywords: str = "AI Engineer"` mean?
   - Answer: A variable named "keywords" that should contain a string, with default value "AI Engineer"

2. Why use `@dataclass`?
   - Answer: To automatically generate boilerplate code like `__init__()` and `__repr__()`

3. What's the difference between `def method(self)` and `@classmethod def method(cls)`?
   - Answer: Regular method works on instances, classmethod works on the class itself

4. Why use `field(default_factory=list)` instead of `= []`?
   - Answer: To ensure each instance gets its own list, not a shared list

5. What does `Optional[str]` mean?
   - Answer: The variable can be a string OR None (null value)

Feel free to ask if any of this is still unclear!
