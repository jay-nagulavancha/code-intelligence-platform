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

1. **Language Detection**: The Security Agent automatically detects the project language using `ProjectDetector`, which looks for:
   - `pom.xml` or `build.gradle` / `build.gradle.kts` for Java
   - `requirements.txt` or `.py` files for Python
   - Other language indicators

2. **Auto-Build (Java)**:
   - If no compiled `.class` files are found, `ProjectBuilder` automatically builds the project
   - **Detects required Java version** from `pom.xml` properties (`java.version`, `maven.compiler.release`, `maven.compiler.source`) or `build.gradle` (`sourceCompatibility`)
   - **Resolves the correct JDK** using `/usr/libexec/java_home -v <version>` (macOS) with fallback to scanning `/Library/Java/JavaVirtualMachines/`
   - Runs `mvn compile -q -DskipTests` (Maven) or `gradlew compileJava -q -x test` (Gradle)
   - Prefers Maven/Gradle wrappers (`mvnw`, `gradlew`) when present

3. **Java Scanning**:
   - Looks for compiled classes in `target/classes` (Maven) or `build/classes` (Gradle)
   - Runs SpotBugs on the compiled classes
   - Parses XML output and converts to standard format

4. **Python Scanning**:
   - Runs Bandit on Python source files
   - Returns JSON-formatted results

## Prerequisites for Java Scanning

### Build Tools

SpotBugs requires compiled `.class` files. The **auto-build system handles this automatically**, but you need the build tools installed:

- **Maven**: `mvn` must be in PATH (or a `mvnw` wrapper in the project)
- **Gradle**: `gradle` must be in PATH (or a `gradlew` wrapper in the project)
- **JDK**: The correct Java version must be installed (auto-detected from `pom.xml`)

### Manual Build (optional)

The auto-build runs automatically, but you can also build manually:

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

The auto-build should handle this automatically. If it still fails:

1. Check that Maven/Gradle is installed and in PATH
2. Check that the correct JDK is installed (see the `JAVA_HOME` reported in build output)
3. Try building manually:
```bash
# Maven
mvn compile

# Gradle
./gradlew build
```

### "Auto-build failed: release version 17 not supported"

The project requires a newer JDK. Install the required version:
```bash
# macOS
brew install --cask temurin@17

# Verify
/usr/libexec/java_home -V
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
