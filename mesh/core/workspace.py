"""
Workspace detection and management for Mesh.

Detects:
- Git repositories (independent repos with .git/ folder)
- Git submodules (.git as file pointing to parent)
- Monorepo patterns (pnpm, yarn workspaces, etc.)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class RepoInfo:
    id: str
    name: str
    path: Path
    type: str  # 'git' or 'submodule'
    module_name: str | None = None  # Python module name (e.g., 'trace_be_adminv3')

    def __post_init__(self):
        if self.module_name is None:
            self.module_name = self._guess_module_name()

    def _guess_module_name(self) -> str:
        name = self.name
        for suffix in ['v3', 'v2', '-service', '-api', '-backend', '-frontend']:
            name = name.rstrip(suffix)
        name = name.replace('-', '_').replace('/', '_')
        return name


@dataclass
class WorkspaceInfo:
    root: Path
    repos: list[RepoInfo] = field(default_factory=list)
    workspace_type: str = "unknown"
    config_files: list[str] = field(default_factory=list)

    def get_repo(self, repo_id: str) -> RepoInfo | None:
        for repo in self.repos:
            if repo.id == repo_id or repo.name == repo_id:
                return repo
        return None

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "repos": [
                {
                    "id": r.id,
                    "name": r.name,
                    "path": str(r.path),
                    "type": r.type,
                    "module_name": r.module_name,
                }
                for r in self.repos
            ],
            "workspace_type": self.workspace_type,
            "config_files": self.config_files,
        }


def detect_git_repo(path: Path) -> tuple[bool, str]:
    git_path = path / ".git"
    if git_path.exists():
        if git_path.is_dir():
            return True, "git"
        elif git_path.is_file():
            return True, "submodule"
    return False, "none"


def is_monorepo_root(path: Path) -> tuple[bool, str]:
    if (path / "pnpm-workspace.yaml").exists():
        return True, "pnpm"
    if (path / "lerna.json").exists():
        return True, "lerna"
    if (path / "nx.json").exists():
        return True, "nx"
    if (path / "turbo.json").exists():
        return True, "turborepo"
    if (path / "rush.json").exists():
        return True, "rush"
    if (path / "package.json").exists():
        try:
            pkg = json.loads((path / "package.json").read_text())
            if "workspaces" in pkg:
                return True, "npm_yarn_workspaces"
        except (json.JSONDecodeError, IOError):
            pass
    return False, "unknown"


def detect_repos(root: Path, include_hidden: bool = False) -> list[RepoInfo]:
    repos = []
    
    for child in root.iterdir():
        if not child.is_dir():
            continue
        
        if not include_hidden and child.name.startswith('.'):
            continue
        
        if child.name in ['node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build', 'target', '.mesh']:
            continue
        
        is_repo, repo_type = detect_git_repo(child)
        
        if is_repo:
            repo_info = RepoInfo(
                id=child.name,
                name=child.name,
                path=child,
                type=repo_type,
            )
            repos.append(repo_info)
    
    return repos


def detect_workspace(root: Path) -> WorkspaceInfo:
    workspace = WorkspaceInfo(root=root)
    
    is_mono, mono_type = is_monorepo_root(root)
    if is_mono:
        workspace.workspace_type = mono_type
        workspace.config_files.append(f"{mono_type} workspace")
    
    workspace.repos = detect_repos(root)
    
    return workspace


def save_workspace_config(workspace: WorkspaceInfo, config_path: Path | None = None) -> None:
    if config_path is None:
        config_path = workspace.root / ".mesh" / "workspace.json"
    
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    config = workspace.to_dict()
    config_path.write_text(json.dumps(config, indent=2))


def load_workspace_config(config_path: Path) -> WorkspaceInfo | None:
    if not config_path.exists():
        return None
    
    try:
        config = json.loads(config_path.read_text())
        repos = []
        for r in config.get("repos", []):
            repo_info = RepoInfo(
                id=r["id"],
                name=r["name"],
                path=Path(r["path"]),
                type=r["type"],
                module_name=r.get("module_name"),
            )
            repos.append(repo_info)
        
        return WorkspaceInfo(
            root=Path(config["root"]),
            repos=repos,
            workspace_type=config.get("workspace_type", "unknown"),
            config_files=config.get("config_files", []),
        )
    except (json.JSONDecodeError, IOError, KeyError):
        return None


def get_workspace(root: Path) -> WorkspaceInfo:
    config_path = root / ".mesh" / "workspace.json"
    
    if config_path.exists():
        workspace = load_workspace_config(config_path)
        if workspace:
            for repo in workspace.repos:
                if not repo.path.exists():
                    is_repo, repo_type = detect_git_repo(repo.path)
                    if is_repo:
                        repo.type = repo_type
                    else:
                        workspace.repos.remove(repo)
            return workspace
    
    workspace = detect_workspace(root)
    save_workspace_config(workspace, config_path)
    return workspace


def classify_import(import_path: str, workspace: WorkspaceInfo, current_repo: RepoInfo | None = None) -> tuple[str | None, str]:
    import_path = import_path.strip()
    
    if import_path.startswith('.'):
        return None, "relative"
    
    if import_path.startswith('@'):
        parts = import_path.lstrip('@').split('/')
        if len(parts) >= 2:
            scope = parts[0]
            pkg_name = parts[1]
            full_name = f"@{scope}/{pkg_name}"
            
            for repo in workspace.repos:
                if repo.module_name and (scope in repo.module_name or repo.name in full_name):
                    return repo.id, "monorepo_package"
            
            return None, "external_package"
        return None, "external_package"
    
    parts = import_path.split('.')[0].split('/')[0].split('_')
    
    if len(parts) >= 1:
        potential_name = parts[0].lower()
        
        for repo in workspace.repos:
            repo_module = repo.module_name.lower()
            repo_name = repo.name.lower()
            
            if (potential_name in repo_module or 
                potential_name in repo_name or
                repo_name.startswith(potential_name)):
                if current_repo is None or repo.id != current_repo.id:
                    return repo.id, "python_module"
    
    return None, "external_package"


def resolve_cross_repo_imports(
    imports: list[dict],
    workspace: WorkspaceInfo,
    current_repo: RepoInfo | None = None
) -> list[dict]:
    cross_repo_imports = []
    
    for imp in imports:
        import_path = imp.get("import_path", "")
        
        target_repo_id, import_type = classify_import(import_path, workspace, current_repo)
        
        if target_repo_id and (current_repo is None or target_repo_id != current_repo.id):
            cross_repo_imports.append({
                "source_repo": current_repo.id if current_repo else None,
                "target_repo": target_repo_id,
                "import_path": import_path,
                "imported_names": imp.get("imported_names", []),
                "type": import_type,
                "line": imp.get("line", 0),
                "file_path": imp.get("file_path", ""),
            })
    
    return cross_repo_imports


def build_repo_relationship_matrix(workspace: WorkspaceInfo, cross_repo_imports: list[dict]) -> dict:
    matrix = {}
    
    for repo in workspace.repos:
        matrix[repo.id] = {
            "depends_on": [],
            "depended_on_by": [],
            "imports": [],
            "imported_by": [],
        }
    
    for imp in cross_repo_imports:
        src = imp["source_repo"]
        tgt = imp["target_repo"]
        
        if src and tgt:
            if tgt not in matrix.get(src, {}).get("depends_on", []):
                matrix[src]["depends_on"].append(tgt)
            if src not in matrix.get(tgt, {}).get("depended_on_by", []):
                matrix[tgt]["depended_on_by"].append(src)
            
            if imp not in matrix[src]["imports"]:
                matrix[src]["imports"].append(imp)
            if imp not in matrix[tgt]["imported_by"]:
                matrix[tgt]["imported_by"].append(imp)
    
    return matrix
