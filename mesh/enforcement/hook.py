"""Git hook installation and management module."""

import os
import stat
import subprocess
from pathlib import Path


class HookManager:
    """Manages git pre-commit hook installation and removal."""

    HOOK_SCRIPT = """#!/bin/sh
# Installed by Mesh — do not remove this line
python -m mesh check --pre-commit
MESH_EXIT=$?
if [ $MESH_EXIT -ne 0 ]; then
    echo ""
    echo "Fix violations above or run 'mesh ignore <id>' to suppress."
    echo "Run 'mesh explain <id>' for detailed fix guidance."
    exit 1
fi
exit 0
"""

    def __init__(self, codebase_root: Path):
        """Initialize the hook manager.

        Args:
            codebase_root: Root directory of the codebase.
        """
        self.codebase_root = codebase_root.resolve()
        self.git_dir = self.codebase_root / ".git"
        self.hooks_dir = self.git_dir / "hooks"
        self.hook_file = self.hooks_dir / "pre-commit"

    def install_hook(self) -> dict:
        """Install the Mesh pre-commit hook.

        Returns:
            Dict with 'success' bool and 'message' str.
        """
        if not self.git_dir.exists():
            return {
                "success": False,
                "message": "Not a git repository. Run 'git init' first.",
            }

        self.hooks_dir.mkdir(parents=True, exist_ok=True)

        try:
            if self.hook_file.exists():
                existing_content = self.hook_file.read_text()
                if "Installed by Mesh" not in existing_content:
                    new_content = existing_content.rstrip() + "\n\n" + self.HOOK_SCRIPT
                    self.hook_file.write_text(new_content)
                    message = (
                        "Mesh hook appended to existing pre-commit hook.\n"
                        "  Existing hook content preserved."
                    )
                else:
                    message = "Mesh hook already installed."
                    return {"success": True, "message": message}
            else:
                self.hook_file.write_text(self.HOOK_SCRIPT)
                message = "Mesh pre-commit hook installed."

            os.chmod(
                self.hook_file,
                stat.S_IRWXU
                | stat.S_IRGRP
                | stat.S_IXGRP
                | stat.S_IROTH
                | stat.S_IXOTH,
            )

            return {
                "success": True,
                "message": message,
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to install hook: {e}",
            }

    def uninstall_hook(self) -> dict:
        """Remove the Mesh pre-commit hook.

        Returns:
            Dict with 'success' bool and 'message' str.
        """
        if not self.hook_file.exists():
            return {
                "success": False,
                "message": "No pre-commit hook found.",
            }

        try:
            existing_content = self.hook_file.read_text()

            lines = existing_content.split("\n")
            new_lines = []
            in_mesh_section = False

            for line in lines:
                if "# Installed by Mesh" in line:
                    in_mesh_section = True
                    continue

                if in_mesh_section:
                    if (
                        line.strip() == ""
                        or line.startswith("#")
                        or "mesh " in line
                        or "MESH_" in line
                    ):
                        continue
                    else:
                        in_mesh_section = False

                new_lines.append(line)

            new_content = "\n".join(new_lines)

            if new_content.strip() == "":
                self.hook_file.unlink()
                message = "Mesh hook removed. Pre-commit hook file deleted."
            else:
                self.hook_file.write_text(new_content)
                message = "Mesh hook removed. Other hook content preserved."

            return {
                "success": True,
                "message": message,
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to uninstall hook: {e}",
            }

    def is_installed(self) -> bool:
        """Check if Mesh hook is installed.

        Returns:
            True if hook is installed.
        """
        if not self.hook_file.exists():
            return False

        try:
            content = self.hook_file.read_text()
            return "Installed by Mesh" in content
        except Exception:
            return False

    def get_hook_status(self) -> dict:
        """Get detailed hook status.

        Returns:
            Dict with hook status information.
        """
        result = {
            "installed": self.is_installed(),
            "hook_file": str(self.hook_file),
            "executable": False,
            "content_preview": "",
        }

        if self.hook_file.exists():
            try:
                mode = os.stat(self.hook_file).st_mode
                result["executable"] = bool(mode & stat.S_IXUSR)

                content = self.hook_file.read_text()
                lines = content.strip().split("\n")
                result["content_preview"] = "\n".join(lines[:5])

            except Exception:
                pass

        return result

    def run_hook(self) -> int:
        """Run the pre-commit hook manually.

        Returns:
            Exit code from hook execution.
        """
        if not self.hook_file.exists():
            return 1

        try:
            result = subprocess.run(
                [str(self.hook_file)],
                cwd=self.codebase_root,
                capture_output=True,
                text=True,
            )
            return result.returncode
        except Exception:
            return 1
