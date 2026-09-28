# PyOccult
Python Occultation Searcher

# Install

# Python Virtual Environment Setup Guide

To set up a Python virtual environment and install dependencies from an existing `requirements.txt` file, open your terminal or command prompt and follow these three steps:

## 1. Create the Virtual Environment
Navigate to your project folder and run the `venv` command. Replacing `.venv` with your preferred environment name is optional, though `.venv` is the standard convention.

* **Windows / macOS / Linux:**
  ```bash
  python -m venv .venv
  ```

## 2. Activate the Virtual Environment
Before installing packages, you must activate the environment. The command depends on your operating system:

* **macOS / Linux:**
  ```bash
  source .venv/bin/activate
  ```
* **Windows (Command Prompt):**
  ```cmd
  .venv\Scripts\activate.bat
  ```
* **Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
*Once activated, your terminal prompt will show `(.venv)` at the beginning of the line.*

## 3. Install from requirements.txt
With the environment active, run `pip` to download and install all the listed packages into your isolated environment:

```bash
pip install -r requirements.txt
```

---

## Quick Tips
* **Deactivate:** When you are done working, simply type `deactivate` to exit the virtual environment.
* **Version Control:** Do not upload your `.venv` folder to GitHub. Add `.venv/` to your `.gitignore` file, but **do** commit your `requirements.txt` file.
* **Updating the list:** If you install new packages later and want to update your file, run:
  ```bash
  pip freeze > requirements.txt
  ```

  ```
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  echo 'EDIT IT, RUN IT:'
  ./pyoccult.py
  ```
