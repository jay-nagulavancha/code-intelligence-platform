# Dependency Vulnerability Scanning Setup

The OSS Agent now supports scanning dependencies for known vulnerabilities in addition to license information.

## Supported Languages

- **Python**: Uses pip-licenses (license info only)
- **Java (Maven)**: Uses OWASP Dependency-Check (licenses + vulnerabilities)
- **Java (Gradle)**: Uses OWASP Dependency-Check (licenses + vulnerabilities)

## OWASP Dependency-Check

OWASP Dependency-Check scans Java dependencies (JARs) from Maven/Gradle repositories for:
- **Known CVEs** (Common Vulnerabilities and Exposures)
- **CVSS Scores** (severity ratings)
- **License Information**
- **Dependency Versions**

### Installation

#### macOS

```bash
brew install dependency-check
```

#### Linux

1. Download from [OWASP Dependency-Check Releases](https://github.com/jeremylong/DependencyCheck/releases)
2. Extract and add to PATH:
   ```bash
   wget https://github.com/jeremylong/DependencyCheck/releases/download/v9.0.9/dependency-check-9.0.9-release.zip
   unzip dependency-check-9.0.9-release.zip
   export PATH=$PATH:/path/to/dependency-check/bin
   ```

#### Windows

1. Download from [OWASP Dependency-Check Releases](https://github.com/jeremylong/DependencyCheck/releases)
2. Extract ZIP file
3. Add `bin` directory to PATH

### Verify Installation

```bash
dependency-check --version
```

Should output something like:
```
Dependency-Check Core version 9.0.9
```

## How It Works

1. **Language Detection**: OSS Agent detects project language via `ProjectDetector`
2. **Build File Detection**: Looks for `pom.xml` (Maven) or `build.gradle` (Gradle)
3. **Auto-Build**: `ProjectBuilder` automatically builds the project to download dependency JARs (detects Java version, resolves correct JDK, runs `mvn compile` or `gradlew compileJava`)
4. **Dependency Scanning**: Runs OWASP Dependency-Check on the project
5. **Vulnerability Analysis**: Parses JSON report for CVEs and CVSS scores
6. **Output**: Returns standardized format with vulnerabilities and licenses

## Usage

### Automatic Detection

```python
from app.agents.oss_agent import OSSAgent

agent = OSSAgent()

# Auto-detects language and scans dependencies
issues = agent.run("/path/to/java/project")
```

### Explicit Language

```python
# For Java Maven project
issues = agent.run("/path/to/project", language="java")
```

### API Usage

```bash
curl -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d '{
    "repoPath": "/path/to/java/project",
    "scanTypes": ["oss"]
  }'
```

## Output Format

### Java Dependencies with Vulnerabilities

```json
{
  "type": "oss",
  "language": "java",
  "tool": "dependency-check",
  "package": "commons-collections-3.2.1.jar",
  "version": "3.2.1",
  "file_path": "/path/to/target/lib/commons-collections-3.2.1.jar",
  "vulnerabilities": [
    {
      "cve": "CVE-2015-6420",
      "severity": "high",
      "cvss_score": 7.5,
      "cvss_v3": {
        "baseScore": 7.5,
        "baseSeverity": "HIGH"
      },
      "description": "Apache Commons Collections before 3.2.2...",
      "references": ["https://nvd.nist.gov/vuln/detail/CVE-2015-6420"]
    }
  ]
}
```

### Python Dependencies (License Only)

```json
{
  "type": "oss",
  "language": "python",
  "tool": "pip-licenses",
  "package": "requests",
  "version": "2.31.0",
  "license": "Apache-2.0",
  "url": "https://pypi.org/project/requests/",
  "vulnerabilities": []
}
```

## What Gets Scanned

### Maven Projects (`pom.xml`)

- Scans all dependencies declared in `pom.xml`
- Checks JARs in `~/.m2/repository/` (local Maven cache)
- Scans JARs in `target/` directory after build
- Checks transitive dependencies

### Gradle Projects (`build.gradle`)

- Scans all dependencies declared in `build.gradle`
- Checks JARs in `~/.gradle/caches/` (local Gradle cache)
- Scans JARs in `build/libs/` after build
- Checks transitive dependencies

## Vulnerability Severity Levels

Based on CVSS scores:
- **Critical**: CVSS >= 9.0
- **High**: CVSS >= 7.0
- **Medium**: CVSS >= 4.0
- **Low**: CVSS > 0
- **Info**: No known vulnerabilities

## Prerequisites

### For Java Projects

The **auto-build system handles building automatically** (including downloading dependencies). You just need:

1. **Build tool installed**: Maven (`mvn`) or Gradle (`gradle`) in PATH — or a wrapper (`mvnw`/`gradlew`) in the project
2. **Correct JDK installed**: The auto-build detects the required Java version from `pom.xml`/`build.gradle` and resolves the JDK automatically

### Manual Build (optional)

If auto-build fails, you can build manually:
```bash
# Maven
mvn dependency:resolve
# or
mvn package

# Gradle
./gradlew dependencies
# or
./gradlew build
```

Ensure dependencies are downloaded:
- Maven: Check `~/.m2/repository/`
- Gradle: Check `~/.gradle/caches/`

## Example: Finding Vulnerable Dependencies

```python
from app.agents.oss_agent import OSSAgent

agent = OSSAgent()
results = agent.run("/path/to/java/project")

# Filter for vulnerabilities
vulnerable_deps = []
for dep in results:
    if dep.get("vulnerabilities"):
        for vuln in dep["vulnerabilities"]:
            if vuln["severity"] in ["critical", "high"]:
                vulnerable_deps.append({
                    "package": dep["package"],
                    "version": dep["version"],
                    "cve": vuln["cve"],
                    "severity": vuln["severity"],
                    "cvss": vuln["cvss_score"]
                })

print(f"Found {len(vulnerable_deps)} high/critical vulnerabilities")
```

## Integration with Security Scanning

Combine dependency scanning with code scanning:

```python
from app.agents.security_agent import SecurityAgent
from app.agents.oss_agent import OSSAgent

# Code-level vulnerabilities
security_agent = SecurityAgent()
code_issues = security_agent.run("/path/to/java/project")

# Dependency vulnerabilities
oss_agent = OSSAgent()
dep_issues = oss_agent.run("/path/to/java/project")

# Combine results
all_security_issues = code_issues + dep_issues
```

## Troubleshooting

### "OWASP Dependency-Check is not installed"

**Solution**: Install Dependency-Check using one of the methods above.

### "pom.xml not found"

**Solution**: 
- Ensure you're scanning a Maven project
- Check that `pom.xml` exists in the project root
- For Gradle projects, ensure `build.gradle` exists

### "No dependencies found"

**Solution**:
1. Build the project first: `mvn dependency:resolve` or `./gradlew dependencies`
2. Ensure dependencies are downloaded to local cache
3. Check that `pom.xml` or `build.gradle` has dependencies declared

### "Scan taking too long"

**Solution**:
- First run downloads vulnerability database (can take 10-15 minutes)
- Subsequent scans are faster (uses cached database)
- Database is stored in `~/.dependency-check/data/`

### "Failed to parse dependency-check report"

**Solution**:
- Ensure Dependency-Check completed successfully
- Check that JSON report was generated
- Verify file permissions

## Database Updates

Dependency-Check uses a local vulnerability database that needs periodic updates:

```bash
# Update database manually
dependency-check --updateonly

# Or let it update automatically on first run
```

Database location: `~/.dependency-check/data/`

## Best Practices

1. **Regular Scanning**: Scan dependencies regularly (weekly/monthly)
2. **CI/CD Integration**: Include in build pipeline
3. **Update Dependencies**: Keep dependencies up to date
4. **Review Findings**: Not all vulnerabilities may be exploitable in your context
5. **Prioritize**: Focus on critical and high severity issues first

## Future Enhancements

- Support for npm/package.json (JavaScript)
- Support for Go modules
- Support for Rust Cargo
- Integration with Snyk API
- Support for Python vulnerability scanning (safety, pip-audit)
- License compliance checking
- Dependency update recommendations
