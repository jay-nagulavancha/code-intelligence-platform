# Java Security Scanning Setup

The Security Agent now supports both Python and Java projects. For Java projects, it uses **SpotBugs** for security vulnerability scanning.

## Supported Languages

- **Python**: Uses Bandit (already installed via pip)
- **Java**: Uses SpotBugs (requires separate installation)

## Installing SpotBugs

### macOS

```bash
brew install spotbugs
```

### Linux

1. Download SpotBugs from [GitHub Releases](https://github.com/spotbugs/spotbugs/releases)
2. Extract the archive:
   ```bash
   wget https://github.com/spotbugs/spotbugs/releases/download/4.8.3/spotbugs-4.8.3.tgz
   tar -xzf spotbugs-4.8.3.tgz
   ```
3. Add to PATH:
   ```bash
   export PATH=$PATH:/path/to/spotbugs-4.8.3/bin
   ```

### Windows

1. Download SpotBugs from [GitHub Releases](https://github.com/spotbugs/spotbugs/releases)
2. Extract the ZIP file
3. Add `bin` directory to your PATH

### Verify Installation

```bash
spotbugs -version
```

Should output something like:
```
SpotBugs version 4.8.3
```

## How It Works

1. **Language Detection**: The Security Agent automatically detects the project language by looking for:
   - `pom.xml` or `build.gradle` for Java
   - `requirements.txt` or `.py` files for Python
   - Other language indicators

2. **Java Scanning**:
   - Looks for compiled classes in `target/classes` (Maven) or `build/classes` (Gradle)
   - Runs SpotBugs on the compiled classes
   - Parses XML output and converts to standard format

3. **Python Scanning**:
   - Runs Bandit on Python source files
   - Returns JSON-formatted results

## Prerequisites for Java Scanning

### Build Your Java Project First

SpotBugs requires compiled `.class` files. Make sure your project is built:

**Maven:**
```bash
mvn compile
# or
mvn package
```

**Gradle:**
```bash
./gradlew build
# or
./gradlew compileJava
```

## Usage

The Security Agent automatically detects the language:

```python
from app.agents.security_agent import SecurityAgent

agent = SecurityAgent()

# Auto-detects language
issues = agent.run("/path/to/java/project")

# Or explicitly specify language
issues = agent.run("/path/to/project", language="java")
```

## API Usage

The scan endpoint automatically detects the language:

```bash
curl -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d '{
    "repoPath": "/path/to/java/project",
    "scanTypes": ["security"]
  }'
```

## Output Format

Java security issues include:
- `type`: "security"
- `language`: "java"
- `tool`: "spotbugs"
- `severity`: "high", "medium", or "low"
- `category`: Bug category
- `priority`: SpotBugs priority (1-3)
- `message`: Description of the issue
- `file`: Source file path
- `line`: Line number

## Troubleshooting

### "No compiled classes found"

**Solution**: Build your Java project first:
```bash
# Maven
mvn compile

# Gradle
./gradlew build
```

### "SpotBugs is not installed"

**Solution**: Install SpotBugs using one of the methods above.

### "SpotBugs failed to parse results"

**Solution**: Check that SpotBugs output XML is valid. The agent will return an info message if parsing fails.

## Adding More Languages

To add support for more languages:

1. Add language detection in `project_detector.py`
2. Add a `_scan_<language>()` method in `SecurityAgent`
3. Update the `run()` method to handle the new language

Example languages to add:
- JavaScript/TypeScript: ESLint with security plugins
- Go: Gosec
- Rust: Clippy with security lints
- C/C++: Cppcheck

## Future Enhancements

- Support for JavaScript/TypeScript (ESLint)
- Support for Go (Gosec)
- Support for Rust (Clippy)
- Multi-language project scanning
- Custom tool configuration
