# Upload Streamline to GitHub with VS Code

## Files to keep out of GitHub

The root `.gitignore` already excludes these local files:

| Excluded files | Reason |
| --- | --- |
| `venv/`, `.venv/` | Local Python environments; recreate them on each computer. |
| `downloads/`, `test_downloads/`, `tests/test_downloads/` | Personal or test media. |
| MP4, MP3, MKV, WebM, M4A, and Opus files | Downloaded media, including files saved outside the default folder. |
| `.part`, `.part-Frag*`, `.ytdl`, `.temp` files | Unfinished downloads and fragments. |
| `.audio_download_archive`, `.video_download_archive` | Your personal download history. |
| `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.test-temp/` | Generated caches and test output. |
| `.coverage`, `htmlcov/` | Local test coverage reports. |
| `.streamline.log`, other `*.log` files | Local activity and diagnostics. |
| `release/`, `*.zip` | Generated source bundles; attach the ZIP to a release if desired. |
| Root `dashboard-*.jpg` files | Local verification screenshots. The README image in `docs/images/` is included. |
| `.env`, `.env.*`, `.aws/` | Private configuration or credentials. `.env.example` is allowed. |
| `.codex/`, `.agents/`, `.vscode/`, `.idea/` | Local assistant/editor settings. |
| `.DS_Store`, `Thumbs.db`, `New Text Document.txt` | OS metadata and the empty scratch file. |

Upload the Python source, `dashboard.html`, all four launchers,
`requirements.txt`, `readme.md`, `license.md`, `tests/`, `docs/`, `.github/`,
`.gitignore`, and `.gitattributes`. Keep the original copyright and credit.

## Publish a new repository

1. Install [Git](https://git-scm.com/downloads) and
   [VS Code](https://code.visualstudio.com/). Restart VS Code after installing Git.
2. Extract `Streamline-GitHub-Source.zip`. Open its **Streamline** folder with
   **File → Open Folder** in VS Code. This clean copy contains source files only.
   Open the folder that directly contains `readme.md` and `.gitignore`.
3. Open **Source Control** using the branch icon on the left, or
   **Ctrl+Shift+G** on Windows/Linux (**Control+Shift+G** on macOS).
4. Select **Initialize Repository**. This creates the local Git history.
5. Review the **Changes** list. It should contain source files and documentation,
   with none of the excluded items above. Select a file to inspect its changes.
6. Select **+** next to **Changes** to stage the reviewed files. Enter a commit
   message such as `Add Streamline downloader dashboard`, then select **Commit**.
   If Git asks for a name/email, follow VS Code's prompt to configure them first.
7. Select **Publish to GitHub**, or open the Command Palette with
   **Ctrl+Shift+P** / **Cmd+Shift+P** and run **Publish to GitHub**.
8. Sign in to your GitHub account if prompted. Choose a repository name and
   **Public** or **Private** visibility. Public repositories expose the committed
   files to everyone; private repositories limit access to people you authorize.
9. Complete the publication. Open the repository link and check that the README,
   screenshot, launchers, license, and tests are present.
10. Open GitHub's **Actions** tab to see the Windows, Ubuntu, and macOS checks.
    These are offline tests; they do not download videos.

The built-in Git tools handle this flow; a GitHub extension is not required.
See [VS Code's source-control quickstart](https://code.visualstudio.com/docs/sourcecontrol/quickstart).

## If you already have a GitHub repository

For an existing repository, use **Git: Clone** in the Command Palette and open
that cloned folder. Copy the extracted Streamline source files into it, including
the hidden configuration files. Review any existing README/license differences,
stage your changes, commit, then use **Sync Changes** or **Push**. This preserves
the existing repository history. See
[VS Code's repository guide](https://code.visualstudio.com/docs/sourcecontrol/repos-remotes).

## Publishing later updates

Edit your files, review **Source Control → Changes**, stage them, enter a clear
commit message, commit, and select **Sync Changes**. Keep using the same local
repository folder so your changes retain their history.

`.gitignore` affects untracked files. It does not remove files already committed
or erase earlier uploads. If a local environment or download was committed before,
remove it from Git tracking while keeping your local copy before pushing again.
See [GitHub's ignore-file guide](https://docs.github.com/en/get-started/git-basics/ignoring-files).

On macOS/Linux, run the README's `chmod` command once before using the launchers.
When committing from those platforms, preserve their executable permissions with:

```sh
git update-index --chmod=+x "Start Downloader.sh" "Start Downloader.command"
```
