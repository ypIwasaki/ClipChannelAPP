"""Keep command-line tools from opening a console in the Windows GUI build."""

import os
import subprocess


def hidden_console_kwargs():
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}
