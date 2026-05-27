# backend/system_tools/file_tree_builder.py
"""
从目录结构文本创建项目目录
"""
from backend.bootstrap import logger
import os
import re
from pathlib import Path
from config_loader import config
from backend.utils.validators import validate_path
import backend


class TreeParser:
    """解析目录树文本，生成创建指令"""

    def __init__(self, text):
        self.text = text.strip()
        self.instructions = []  # [(type, path), ...]  type: "dir" | "file"

    def parse(self):
        """解析文本，识别目录和文件"""
        lines = self.text.split("\n")

        # 检测 Markdown 代码块并去除标记
        if self._is_markdown_codeblock(lines):
            # 去掉首尾的 ``` 行
            start, end = 0, len(lines)
            if lines[0].strip().startswith("```"):
                start = 1
            if lines[-1].strip().startswith("```"):
                end = -1
            lines = lines[start:end]

        # 根据格式选择解析方式
        if self._is_tree_format(lines):
            self._parse_tree_format(lines)
        else:
            self._parse_simple_format(lines)

        return self.instructions

    def _is_tree_format(self, lines):
        """检测是否是 tree 格式（包含 ├── └── │ 等符号）"""
        for line in lines[:10]:
            if any(c in line for c in ["├──", "└──", "│"]):
                return True
        return False

    def _is_markdown_codeblock(self, lines):
        """检测是否被 Markdown 代码块包裹（首行和末行都是 ```）"""
        if len(lines) < 2:
            return False
        first = lines[0].strip()
        last = lines[-1].strip()
        return first.startswith("```") and last.startswith("```")

    def _clean_name(self, name):
        """清理名称，去除行尾注释（两个以上空格后跟 # 的内容）"""
        # 只去除行尾注释，保留路径中正常的 #
        name = re.sub(r'\s{2,}#.*$', '', name)
        name = name.strip()
        return name

    def _detect_indent_width(self, lines):
        """
        检测简单缩进格式的缩进宽度（2 或 4 空格）
        返回一个整数，表示每级缩进使用的空格数，默认为 4
        """
        for line in lines:
            stripped = line.lstrip()
            if not stripped or stripped.startswith('#'):
                continue
            indent = len(line) - len(stripped)
            if indent > 0:
                return indent
        return 4  # 默认

    def _parse_tree_format(self, lines):
        """解析 tree 格式"""
        path_stack = [("", -1)]  # (路径, 层级)
        root_name = None

        for line in lines:
            if not line.strip():
                continue

            stripped = line.strip()
            # 跳过纯分隔符行（如只有 │ 或空格）
            if stripped == "│" or not stripped.replace("│", "").replace(" ", ""):
                continue

            # 检测根目录（没有树形符号的行）
            if not any(c in line for c in ["├──", "└──", "│"]):
                if stripped.endswith("/"):
                    root_name = self._clean_name(stripped).rstrip("/")
                    path_stack = [(root_name, -1)]
                    continue

            # 将树形符号替换为空格，计算缩进
            processed = line.replace("├── ", "    ").replace("└── ", "    ")
            processed = processed.replace("│   ", "    ")
            processed = processed.replace("│", " ")

            indent = 0
            temp = processed
            while temp.startswith("    "):
                indent += 1
                temp = temp[4:]

            name = self._clean_name(temp)
            if not name:
                continue

            # 调整路径栈到正确深度
            while path_stack and path_stack[-1][1] >= indent:
                path_stack.pop()

            parent_path = path_stack[-1][0] if path_stack else ""
            if not parent_path and root_name:
                parent_path = root_name

            is_dir = name.endswith("/")
            name_clean = name.rstrip("/")
            full_path = os.path.join(parent_path, name_clean) if parent_path else name_clean

            if is_dir:
                self.instructions.append(("dir", full_path))
                path_stack.append((full_path, indent))
            else:
                self.instructions.append(("file", full_path))

    def _parse_simple_format(self, lines):
        """解析简单缩进格式（自动检测缩进宽度）"""
        indent_width = self._detect_indent_width(lines)
        path_stack = [("", -1)]
        root_name = None

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # 统一制表符为空格（先处理，再计算缩进）
            processed = line.expandtabs(indent_width)

            # 计算缩进级别（基于检测到的缩进宽度）
            indent = 0
            temp = processed
            while temp.startswith(" " * indent_width):
                indent += 1
                temp = temp[indent_width:]

            name = self._clean_name(temp)
            if not name:
                continue

            # 顶级目录（无缩进且路径栈为空）
            if indent == 0 and path_stack[-1][0] == "":
                if name.endswith("/"):
                    root_name = name.rstrip("/")
                    path_stack = [(root_name, -1)]
                    continue

            # 调整路径栈
            while path_stack and path_stack[-1][1] >= indent:
                path_stack.pop()

            parent_path = path_stack[-1][0] if path_stack else ""
            if not parent_path and root_name:
                parent_path = root_name

            is_dir = name.endswith("/")
            name_clean = name.rstrip("/")
            full_path = os.path.join(parent_path, name_clean) if parent_path else name_clean

            if is_dir:
                self.instructions.append(("dir", full_path))
                path_stack.append((full_path, indent))
            else:
                self.instructions.append(("file", full_path))


class ProjectCreator:
    """根据解析结果创建目录和文件"""

    def __init__(self, instructions, base_path=".", dry_run=False, verbose=False):
        self.instructions = instructions
        self.base_path = os.path.abspath(base_path)
        self.dry_run = dry_run
        self.verbose = verbose
        self.created_dirs = 0
        self.created_files = 0
        self.errors = []
        self.log_messages = []  # 收集所有日志，替代直接 print

    def create(self):
        """执行创建"""
        for inst_type, path in self.instructions:
            full_path = os.path.join(self.base_path, path)

            try:
                if inst_type == "dir":
                    if not os.path.exists(full_path):
                        if self.dry_run:
                            self._log(f"[DRY RUN] 创建目录: {path}")
                        else:
                            os.makedirs(full_path, exist_ok=True)
                            self._log(f"📁 创建目录: {path}")
                        self.created_dirs += 1
                    else:
                        self._log(f"⏭  已存在: {path}")

                elif inst_type == "file":
                    if not os.path.exists(full_path):
                        if self.dry_run:
                            self._log(f"[DRY RUN] 创建文件: {path}")
                        else:
                            # 确保父目录存在
                            os.makedirs(os.path.dirname(full_path), exist_ok=True)
                            with open(full_path, "w", encoding="utf-8") as f:
                                if os.path.basename(path) != ".gitkeep":
                                    f.write(f"# {os.path.basename(path)}\n")
                            self._log(f"📄 创建文件: {path}")
                        self.created_files += 1
                    else:
                        self._log(f"⏭  已存在: {path}")

            except Exception as e:
                error_msg = f"❌ 创建失败 {path}: {e}"
                self.errors.append(error_msg)
                self._log(error_msg)

    def _log(self, msg):
        self.log_messages.append(msg)
        if self.verbose:
            logger.info(msg)

    def summary(self):
        """返回总结信息，不再直接打印"""
        lines = [
            f"\n{'='*60}",
            "📊 创建完成！",
            f"   目录: {self.created_dirs} 个",
            f"   文件: {self.created_files} 个",
            f"   错误: {len(self.errors)} 个",
            f"   路径: {self.base_path}",
        ]
        if self.dry_run:
            lines.append("   ⚠️  这是试运行，没有实际创建任何文件")
        lines.append(f"{'='*60}")
        summary_text = "\n".join(lines)
        self.log_messages.append(summary_text)
        if self.verbose:
            logger.info(summary_text)
        return summary_text


# ============================================================
# 主入口（给大模型调用）
# ============================================================

def create_project_tree(tree: str, path: str) -> dict:
    """
    项目创建，解析目录结构文本，自动创建对应的目录和文件

    支持的格式:
        - tree 命令输出（含 ├── └── │ 符号）
        - Markdown 代码块中的目录树
        - 简单缩进格式（自动检测缩进宽度，支持 2/4 空格或制表符）

    Args:
        tree: 目录树文本
        path: 目标文件路径（相对或绝对路径）

    Returns:
        dict: 包含 success, message, created_dirs, created_files, errors, logs 等字段
    """
    # 加载配置中的允许目录
    paths = [config.uploads_dir, backend.workspace_path]
    allowed_dirs = [Path(p).resolve() for p in paths]

    # 路径安全校验
    try:
        safe_path = validate_path(path, allowed_dirs)
    except ValueError as e:
        return {
            "success": False,
            "error": f"路径校验失败：{e}",
        }

    # 解析目录结构
    parser_obj = TreeParser(tree)
    instructions = parser_obj.parse()

    if not instructions:
        return {
            "success": False,
            "error": "未能解析出任何目录或文件，请检查输入格式",
        }

    # 创建项目
    creator = ProjectCreator(
        instructions=instructions,
        base_path=safe_path,
        dry_run=False,
        verbose=False
    )

    try:
        creator.create()
        creator.summary()  # 收集总结信息到日志
    except Exception as e:
        return {
            "success": False,
            "error": f"项目创建过程中发生异常：{e}",
        }

    # 检查是否有错误
    if creator.errors:
        return {
            "success": False,
            "error": "部分项目创建失败，详见 errors 字段",
            "created_dirs": creator.created_dirs,
            "created_files": creator.created_files,
            "errors": creator.errors,
            "logs": creator.log_messages,
        }

    # 成功返回
    return {
        "success": True,
        "message": f"项目创建成功，路径：{safe_path}",
        "created_dirs": creator.created_dirs,
        "created_files": creator.created_files,
        "logs": creator.log_messages,  # 包含详细日志，便于调试
    }