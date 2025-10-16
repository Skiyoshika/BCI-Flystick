"""Interactive bilingual setup wizard for BCI Flystick."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

CORE_MODULES = [
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("yaml", "pyyaml"),
]

BACKEND_MODULES = {
    "vigem": ("pyvjoy", "pyvjoy"),
    "uinput": ("uinput", "python-uinput"),
}

BRAINFLOW_MODULE = ("brainflow", "brainflow")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
PROFILE_DIR = CONFIG_DIR / "user_profiles"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
LAST_PROFILE_FILE = PROFILE_DIR / ".last_profile"

SUPPORTED_LANGUAGES = {"en", "zh"}

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "Welcome to the BCI Flystick setup wizard!",
        "prereq_header": "Before continuing, make sure the following prerequisites are satisfied:",
        "prereq_python": "Python 3.10+ installed",
        "prereq_driver": "Flystick receiver connected and drivers installed (e.g., vJoy/ViGEm or uinput)",
        "prereq_fpvsim": "Optional: FPV simulator installed (Liftoff, Velocidrone, etc.)",
        "prereq_continue": "Press Enter once you have reviewed the prerequisites...",
        "dependency_check": "Checking required Python packages...",
        "dependency_missing": "Missing package: {package}. Install with: pip install {install}.",
        "dependency_optional": "Optional package missing: {package}. Install with: pip install {install}.",
        "dependency_ok": "All required Python packages are available.",
        "backend_check": "Verifying controller backend support...",
        "backend_ready": "{backend} backend ready.",
        "backend_missing": "Backend requirement missing: {package}. Install with: pip install {install}.",
        "brainflow_check": "Checking BrainFlow SDK (required for real hardware)...",
        "brainflow_ok": "BrainFlow SDK available.",
        "brainflow_missing": "BrainFlow SDK not found. Install with: pip install brainflow",
        "profile_name": "Profile name (letters, numbers, dashes): ",
        "input_invalid": "Input invalid, please try again.",
        "control_scheme": "Choose control backend [1] vJoy/ViGEm (Windows) [2] uinput (Linux): ",
        "udp_port": "UDP port for BCI receiver (default 5005): ",
        "udp_host": "UDP host for local services (default 127.0.0.1): ",
        "axis_invert": "Invert pitch axis? [Y/N]: ",
        "axis_scale": "Throttle scaling (0.1 - 2.0, default 1.0): ",
        "mock_mode": "Use mock EEG generator for dry-run testing? [Y/N]: ",
        "mock_warning": "Mock mode is enabled; real OpenBCI hardware will not be used.",
        "dashboard_prompt": "Choose telemetry dashboard: [1] Terminal (default) [2] GUI [3] None: ",
        "summary": "Configuration summary:",
        "saved": "Profile saved to {path}",
        "remember": "This profile will be used automatically on next launch.",
        "done": "Setup complete! Run 'python -m python.main --config {path}' to start the runtime.",
        "language_prompt": "Choose language / 选择语言 [1] English [2] 中文: ",
    },
    "zh": {
        "welcome": "欢迎使用 BCI Flystick 引导程序！",
        "prereq_header": "继续之前，请确认已经完成以下准备：",
        "prereq_python": "已安装 Python 3.10 及以上版本",
        "prereq_driver": "已连接 Flystick 接收端并安装驱动（如 vJoy/ViGEm 或 uinput）",
        "prereq_fpvsim": "可选：已安装 FPV 模拟器（Liftoff、Velocidrone 等）",
        "prereq_continue": "确认无误后按回车继续...",
        "dependency_check": "正在检查所需的 Python 依赖...",
        "dependency_missing": "缺少依赖：{package}。请运行 pip install {install} 安装。",
        "dependency_optional": "可选依赖缺失：{package}。可运行 pip install {install} 安装。",
        "dependency_ok": "所有 Python 依赖均已就绪。",
        "backend_check": "正在检查控制后端依赖...",
        "backend_ready": "{backend} 后端已就绪。",
        "backend_missing": "缺少后端依赖：{package}。请运行 pip install {install} 安装。",
        "brainflow_check": "正在检查 BrainFlow SDK（连接真实设备所需）...",
        "brainflow_ok": "已检测到 BrainFlow SDK。",
        "brainflow_missing": "未找到 BrainFlow SDK。请运行 pip install brainflow 或参考文档安装。",
        "profile_name": "配置名称（字母、数字或连字符）: ",
        "input_invalid": "输入无效，请重新输入。",
        "control_scheme": "选择控制后端 [1] vJoy/ViGEm（Windows） [2] uinput（Linux）: ",
        "udp_port": "BCI 接收端 UDP 端口（默认为 5005）：",
        "udp_host": "本机 UDP 主机地址（默认为 127.0.0.1）：",
        "axis_invert": "是否反转俯仰轴？[Y/N]: ",
        "axis_scale": "油门缩放系数（0.1 - 2.0，默认 1.0）：",
        "mock_mode": "是否启用模拟 EEG（便于调试，无需硬件）？[Y/N]: ",
        "mock_warning": "将使用模拟 EEG 数据，不会连接真实 OpenBCI 设备。",
        "dashboard_prompt": "选择遥测展示方式：[1] 终端仪表板（默认） [2] 图形界面 [3] 不启动：",
        "summary": "配置概要：",
        "saved": "配置已保存至 {path}",
        "remember": "下次启动时将自动使用该配置。",
        "done": "引导完成！运行 'python -m python.main --config {path}' 即可启动运行时。",
        "language_prompt": "Choose language / 选择语言 [1] English [2] 中文: ",
    },
}

class Wizard:
    def __init__(self, language: str) -> None:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        self.language = language

    @property
    def strings(self) -> dict[str, str]:
        return STRINGS[self.language]

    def t(self, key: str) -> str:
        return self.strings[key]

    def run(self) -> Path:
        self._print_intro()
        self._check_core_dependencies()
        profile_name = self._prompt_profile_name()
        control_backend = self._prompt_control_backend()
        self._check_backend_dependencies(control_backend)
        udp_host = self._prompt_udp_host()
        udp_port = self._prompt_udp_port()
        invert_pitch = self._prompt_yes_no(self.t("axis_invert"), default=False)
        throttle_scale = self._prompt_float(self.t("axis_scale"), default=1.0, minimum=0.1, maximum=2.0)
        mock_mode = self._prompt_yes_no(self.t("mock_mode"), default=False)
        if mock_mode:
            print(self.t("mock_warning"))
        else:
            self._check_brainflow()
        dashboard_mode = self._prompt_dashboard_mode()
        launch_dashboard = dashboard_mode != "none"

        profile = {
            "language": self.language,
            "profile_name": profile_name,
            "control_backend": control_backend,
            "udp_host": udp_host,
            "udp_port": udp_port,
            "invert_pitch": invert_pitch,
            "throttle_scale": throttle_scale,
            "mock_mode": mock_mode,
            "launch_dashboard": launch_dashboard,
            "dashboard_mode": dashboard_mode,
        }

        print("\n" + self.t("summary"))
        print(json.dumps(profile, indent=2, ensure_ascii=False))

        profile_path = PROFILE_DIR / f"{profile_name}.json"
        with profile_path.open("w", encoding="utf-8") as handle:
            json.dump(profile, handle, indent=2, ensure_ascii=False)

        LAST_PROFILE_FILE.write_text(str(profile_path.resolve()), encoding="utf-8")

        print(self.t("saved").format(path=profile_path))
        print(self.t("remember"))
        print(self.t("done").format(path=profile_path))
        return profile_path

    def _print_intro(self) -> None:
        print(self.t("welcome"))
        print()
        print(self.t("prereq_header"))
        for key in ("prereq_python", "prereq_driver", "prereq_fpvsim"):
            print(f" - {self.t(key)}")
        input(self.t("prereq_continue"))

    def _check_core_dependencies(self) -> None:
        print(self.t("dependency_check"))
        missing = []
        for module_name, pip_name in CORE_MODULES:
            if importlib.util.find_spec(module_name) is None:
                missing.append((module_name, pip_name))
        if missing:
            for module_name, pip_name in missing:
                print(self.t("dependency_missing").format(package=module_name, install=pip_name))
        else:
            print(self.t("dependency_ok"))

    def _check_backend_dependencies(self, backend: str) -> None:
        print(self.t("backend_check"))
        module_info = BACKEND_MODULES.get(backend)
        if module_info is None:
            print(self.t("backend_missing").format(package=backend, install=backend))
            return
        module_name, pip_name = module_info
        if importlib.util.find_spec(module_name) is None:
            print(self.t("backend_missing").format(package=module_name, install=pip_name))
        else:
            backend_label = "vJoy / ViGEm" if backend == "vigem" else "uinput"
            print(self.t("backend_ready").format(backend=backend_label))

    def _check_brainflow(self) -> None:
        print(self.t("brainflow_check"))
        module_name, pip_name = BRAINFLOW_MODULE
        if importlib.util.find_spec(module_name) is None:
            print(self.t("brainflow_missing").format(install=pip_name))
        else:
            print(self.t("brainflow_ok"))

    def _prompt_profile_name(self) -> str:
        while True:
            name = input(self.t("profile_name")).strip()
            if name and all(ch.isalnum() or ch in {"-", "_"} for ch in name):
                return name
            print(self.t("input_invalid"))

    def _prompt_control_backend(self) -> str:
        while True:
            choice = input(self.t("control_scheme")).strip() or "1"
            if choice == "1":
                return "vigem"
            if choice == "2":
                return "uinput"
            print(self.t("input_invalid"))

    def _prompt_udp_host(self) -> str:
        while True:
            value = input(self.t("udp_host")).strip()
            if not value:
                return "127.0.0.1"
            if all(ch.isalnum() or ch in {".", "-"} for ch in value):
                return value
            print(self.t("input_invalid"))

    def _prompt_udp_port(self) -> int:
        while True:
            value = input(self.t("udp_port")).strip()
            if not value:
                return 5005
            if value.isdigit():
                port = int(value)
                if 1024 <= port <= 65535:
                    return port
            print(self.t("input_invalid"))

    def _prompt_yes_no(self, prompt: str, *, default: bool) -> bool:
        value = input(prompt).strip().lower()
        if not value:
            return default
        return value in {"y", "yes", "是", "好"}

    def _prompt_float(self, prompt: str, *, default: float, minimum: float, maximum: float) -> float:
        while True:
            value = input(prompt).strip()
            if not value:
                return default
            try:
                number = float(value)
            except ValueError:
                print(self.t("input_invalid"))
                continue
            if minimum <= number <= maximum:
                return number
            print(self.t("input_invalid"))

    def _prompt_dashboard_mode(self) -> str:
        while True:
            choice = input(self.t("dashboard_prompt")).strip() or "1"
            if choice == "1":
                return "terminal"
            if choice == "2":
                return "gui"
            if choice == "3":
                return "none"
            print(self.t("input_invalid"))


def select_language(initial: str | None) -> str:
    if initial in SUPPORTED_LANGUAGES:
        return initial

    while True:
        choice = input(STRINGS["en"]["language_prompt"]).strip()
        if choice == "1":
            return "en"
        if choice == "2":
            return "zh"
        print("Invalid selection, please try again. / 输入无效，请重试。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BCI Flystick setup wizard")
    parser.add_argument("--language", choices=sorted(SUPPORTED_LANGUAGES))
    args = parser.parse_args(argv)

    language = select_language(args.language)
    wizard = Wizard(language)
    wizard.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
