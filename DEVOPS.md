# DevOps Guide - Bee-Tek Shoe Reader App

## Project Overview

**Purpose**: Desktop GUI application for monitoring Bee-Tek card-dealing shoe hardware and relaying card data to backend server via HTTP POST.

**Tech Stack**:
- **Language**: Python 3.12
- **GUI Framework**: Kivy 2.3.1
- **Packaging**: PyInstaller → AppImage (Linux)
- **Deployment**: Zero-install AppImage for end users

---

## Build Process

### 1. Prerequisites
- Python 3.12+ with venv
- PyInstaller 6.16.0
- appimagetool (Linux AppImage builder)
- Dependencies in `requirements.txt`

### 2. Build Steps

#### A. Setup Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### B. Build Executable with PyInstaller
```bash
# Make sure venv is activated first
source venv/bin/activate

pyinstaller \
  --onefile \
  --windowed \
  --icon=wildace.jpeg \
  --add-data="bee.png:." \
  --name=BeetekShoeMonitor \
  main.py
```

**Output**: `dist/BeetekShoeMonitor` (single executable)

#### C. Create AppDir Structure
```bash
mkdir -p BeetekShoeMonitor.AppDir/usr/bin
cp dist/BeetekShoeMonitor BeetekShoeMonitor.AppDir/usr/bin/
cp bee.png BeetekShoeMonitor.AppDir/
cp wildace.jpeg BeetekShoeMonitor.AppDir/wildace.png

# Create desktop entry
cat > BeetekShoeMonitor.AppDir/BeetekShoeMonitor.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=Bee-Tek Shoe Monitor
Comment=Monitor card-dealing shoe and send data via HTTP
Exec=BeetekShoeMonitor
Icon=wildace
Categories=Utility;
Terminal=false
EOF

# Create AppRun launcher
cat > BeetekShoeMonitor.AppDir/AppRun << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
exec "${HERE}/usr/bin/BeetekShoeMonitor" "$@"
EOF
chmod +x BeetekShoeMonitor.AppDir/AppRun
```

#### D. Download appimagetool (first time only)
```bash
# Download if you don't have it
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
```

#### E. Build AppImage
```bash
# Run appimagetool to create final AppImage
./appimagetool-x86_64.AppImage \
  BeetekShoeMonitor.AppDir \
  BeetekShoeMonitor-x86_64.AppImage
```

**Output**: `BeetekShoeMonitor-x86_64.AppImage` (~39MB)

---

## CI/CD Pipeline Design

### Suggested GitHub Actions Workflow

**File**: `.github/workflows/build.yml`

```yaml
name: Build AppImage

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main]
  release:
    types: [created]

jobs:
  build:
    runs-on: ubuntu-22.04
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Setup Python 3.12
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        python -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: Build executable with PyInstaller
      run: |
        source venv/bin/activate
        pyinstaller \
          --onefile \
          --windowed \
          --icon=wildace.jpeg \
          --add-data="bee.png:." \
          --name=BeetekShoeMonitor \
          main.py
    
    - name: Create AppDir structure
      run: |
        mkdir -p BeetekShoeMonitor.AppDir/usr/bin
        cp dist/BeetekShoeMonitor BeetekShoeMonitor.AppDir/usr/bin/
        cp bee.png BeetekShoeMonitor.AppDir/
        cp wildace.jpeg BeetekShoeMonitor.AppDir/wildace.png
        
        cat > BeetekShoeMonitor.AppDir/BeetekShoeMonitor.desktop << 'EOF'
        [Desktop Entry]
        Type=Application
        Name=Bee-Tek Shoe Monitor
        Comment=Monitor card-dealing shoe and send data via HTTP
        Exec=BeetekShoeMonitor
        Icon=wildace
        Categories=Utility;
        Terminal=false
        EOF
        
        cat > BeetekShoeMonitor.AppDir/AppRun << 'EOF'
        #!/bin/bash
        HERE="$(dirname "$(readlink -f "${0}")")"
        export PATH="${HERE}/usr/bin:${PATH}"
        exec "${HERE}/usr/bin/BeetekShoeMonitor" "$@"
        EOF
        chmod +x BeetekShoeMonitor.AppDir/AppRun
    
    - name: Download appimagetool
      run: |
        wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
        chmod +x appimagetool-x86_64.AppImage
    
    - name: Build AppImage
      run: |
        ./appimagetool-x86_64.AppImage \
          BeetekShoeMonitor.AppDir \
          BeetekShoeMonitor-x86_64.AppImage
    
    - name: Upload AppImage artifact
      uses: actions/upload-artifact@v4
      with:
        name: BeetekShoeMonitor-AppImage
        path: BeetekShoeMonitor-x86_64.AppImage
        retention-days: 30
    
    - name: Upload to Release (on tag)
      if: startsWith(github.ref, 'refs/tags/')
      uses: softprops/action-gh-release@v1
      with:
        files: BeetekShoeMonitor-x86_64.AppImage
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Release Process

### Manual Release (Current)
1. Build AppImage locally (as shown above)
2. Test on target system
3. Upload to GitHub Releases manually
4. Share download link with end users

### Automated Release (Recommended)
1. **Version Tagging**:
   ```bash
   git tag -a v1.0.0 -m "Release v1.0.0"
   git push origin v1.0.0
   ```

2. **GitHub Actions**:
   - Automatically builds AppImage
   - Runs tests (if added)
   - Uploads to GitHub Release
   - Generates release notes

3. **Versioning Strategy**:
   - `v1.0.0` - Major release (stable)
   - `v1.1.0` - Minor features
   - `v1.1.1` - Patches/bugfixes
   - `v1.0.0-rc1` - Release candidates

---

## Testing

### Unit Tests (Future)
```bash
# Add to CI pipeline
pytest tests/
```

### Manual Testing Checklist
- [ ] AppImage runs without errors
- [ ] Serial port connection works (`/dev/ttyUSB0`)
- [ ] Card parsing works (Game & Manual Burn modes)
- [ ] HTTP POST sends correct JSON format
- [ ] UI displays cards with correct symbols
- [ ] bee.png icon displays correctly
- [ ] Configuration saves/loads from shoe.json

---

## Deployment

### Target Platform
- **OS**: Linux (Ubuntu 22.04+, Debian, etc.)
- **Architecture**: x86_64
- **Requirements**: None (AppImage is self-contained)

### Installation for End Users
```bash
chmod +x BeetekShoeMonitor-x86_64.AppImage
./BeetekShoeMonitor-x86_64.AppImage
```

### System Integration (Optional)
```bash
# Install to ~/.local/bin for system-wide access
mkdir -p ~/.local/bin
cp BeetekShoeMonitor-x86_64.AppImage ~/.local/bin/
```

---

## Configuration

### Runtime Configuration
File: `shoe.json` (auto-created on first run)
```json
{
  "ip": "192.168.1.140",
  "port": 9000,
  "url": "api/holdem/beetek/card"
}
```

**Note**: Users can change these values via the GUI (Save button)

### Serial Port Permissions
Users need to be in `dialout` group:
```bash
sudo usermod -a -G dialout $USER
# Log out and log back in
```

---

## Monitoring & Logs

### Application Logs
- **Location**: Terminal/console output (when run from CLI)
- **Format**: `[INFO] ✅ Sent 7S -> 200`
- **Key Events**:
  - Serial connection status
  - Card parsing success/failure
  - HTTP POST responses
  - Alarms from Bee-Tek shoe

### Debug Mode
Run with verbose output:
```bash
./BeetekShoeMonitor-x86_64.AppImage --verbose  # (if implemented)
```

---

## Architecture

```
┌─────────────────────┐     Serial      ┌──────────────────────┐
│  Bee-Tek Shoe (HW)  │─────USB─────────│  Kivy App (Python)   │
│  Emits: [Game]<4S>  │   9600 baud     │  • SerialMonitor     │
└─────────────────────┘                 │  • Card Parser       │
                                        │  • UI Display        │
                                        │  • HTTP Client       │
                                        └──────────┬───────────┘
                                                   │ HTTP POST
                                                   │ JSON
                                                   ▼
                                        ┌──────────────────────┐
                                        │  Backend Server      │
                                        │  (Your API)          │
                                        └──────────────────────┘
```

---

## Troubleshooting

### Build Failures

**Issue**: PyInstaller missing dependencies
```bash
pip install --upgrade pyinstaller
pip install -r requirements.txt
```

**Issue**: appimagetool not found
```bash
# Download it first
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
```

### Runtime Errors

**Issue**: `bee.png not found`
- Ensure `--add-data="bee.png:."` in PyInstaller command
- Verify `resource_path()` function in main.py

**Issue**: Serial port permission denied
- Add user to dialout group (see above)

---

## Next Steps for DevOps

1. **Review this document** and understand build process
2. **Create `.github/workflows/build.yml`** with above workflow
3. **Test CI pipeline** by pushing to `dev` branch
4. **Setup branch protection** for `main` branch
5. **Configure release automation** for version tags
6. **Add build status badges** to README.md
7. **Setup artifact storage** (GitHub Releases or S3)
8. **Add automated testing** (pytest) if needed

