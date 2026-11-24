# RuralLearn

RuralLearn is a Python desktop learning prototype built for a hackathon. It brings lessons, practice quizzes, progress tracking, locally searchable learning material, and an optional AI tutor together in an interface designed to remain useful without an internet connection.

## Problem

Learners in rural and low-connectivity settings may have limited access to reliable online learning tools. Learning resources can be difficult to revisit offline, and learners may have little visibility into their practice history or topics that need more attention.

## Solution

RuralLearn keeps a starter curriculum, quizzes, learner progress, and imported study materials on the learner's own device. Learners can move through lessons, practice and review answers, track progress, and search local material. An optional Ollama connection provides locally generated tutor responses; a clearly identified demo tutor remains available when Ollama is not set up.

## Features

- Dashboard with lesson and quiz activity, recommendations, and service status.
- Lessons across Physics, Chemistry, Mathematics, Biology, English, and Kannada, with summaries, examples, concepts, and questions.
- Multiple-choice practice with saved scores, answer review, explanations, and retakes.
- Progress tracking for lesson completion, quiz history, strengths, and topics to revisit.
- Tutor chat with local lesson search and optional Ollama models.
- Import and search text from local TXT and text-based PDF files.
- Local preferences, chats, imported material, and progress stored on the device.
- Explore cards and the bundled starter curriculum are available offline.

Bundled lessons are sample educational content, not official textbook material. PDF import extracts selectable text; scanned image-only PDFs may have no searchable text.

## Technologies

- Python 3.11+
- PySide6 (Qt desktop interface)
- SQLite (local application data)
- pypdf (PDF text extraction)
- Ollama (optional local model service)

## Requirements

- Windows 10 or later is the supported desktop target.
- Python 3.11 or newer, 64-bit, available as `py` in PowerShell or Command Prompt.
- Internet access is needed to install Python packages. It is not required to use the bundled lessons, quizzes, or progress features after setup.
- Ollama and a downloaded model are optional and are only needed for locally generated tutor answers.

## Install and run

From the project directory in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

You can also double-click `run_rurallearn.bat`. It installs the requirements with the Python launcher and starts the application. The batch file requires network access if the dependencies are not already installed.

The app creates its SQLite database and log in the current user's application data directory through Qt's `AppDataLocation` (typically `%APPDATA%\RuralLearn`). Learner profile details, progress, chats, and imported text are stored locally there rather than in the project folder.

## Optional Ollama tutor

Install Ollama separately, start its local service, and download at least one model. For example:

```powershell
ollama pull llama3.2:3b
```

RuralLearn checks the local Ollama service at `http://localhost:11434` and offers models already installed there. It does not download models itself. Model storage and resource needs depend on the model chosen. Tutor responses are generated locally by Ollama; imported/local lesson passages can be supplied as context.

Without a reachable Ollama service and installed model, the app keeps its other features available and labels the tutor as demo mode. Demo mode returns predefined learning explanations, not generated model responses. Core lessons, quizzes, local search, and saved progress do not need Ollama or an internet connection once the application dependencies are installed.

## Build a Windows executable (optional)

Install PyInstaller separately, then build from the project directory:

```powershell
py -3 -m pip install pyinstaller
py -3 -m PyInstaller --noconfirm RuralLearn.spec
```

The generated build output is local packaging output and should not be committed.

## Project structure

```text
main.py                 Application entry point
rurallearn/
  ui.py                 Desktop screens and navigation
  db.py                 SQLite setup and persistence
  content.py            Bundled sample curriculum and explore cards
  ai.py                 Ollama integration and demo tutor
  retrieval.py          Local TXT/PDF import and retrieval
requirements.txt        Python runtime dependencies
run_rurallearn.bat      Windows launch helper
RuralLearn.spec         PyInstaller build configuration
```
