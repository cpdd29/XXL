"""知识源适配器。"""

from .obsidian_fs_adapter import (
    ObsidianFilesystemAdapter,
    ObsidianMarkdownFile,
    ObsidianVaultScanResult,
    obsidian_filesystem_adapter,
)

__all__ = [
    "ObsidianFilesystemAdapter",
    "ObsidianMarkdownFile",
    "ObsidianVaultScanResult",
    "obsidian_filesystem_adapter",
]
