"""ASCII art logos and icons for CodeQuest."""

LOGO = r"""
   ____          _       ___                  _
  / ___|___   __| | ___ / _ \ _   _  ___  ___| |_
 | |   / _ \ / _` |/ _ \ | | | | | |/ _ \/ __| __|
 | |__| (_) | (_| |  __/ |_| | |_| |  __/\__ \ |_
  \____\___/ \__,_|\___|\__\_\\__,_|\___||___/\__|
"""

LOGO_SMALL = "[bold cyan]< CodeQuest />[/]"

ICONS = {
    "Python": "[green][/]",
    "Node": "[yellow][/]",
    "Bash": "[cyan]$_[/]",
    "Rust": "[red][/]",
    "Go": "[blue]Go[/]",
    "Static": "[magenta]<>[/]",
    "Unknown": "[dim]??[/]",
}

BADGES = {
    "git": "[bold blue]\\[GIT][/]",
    "github": "[bold white on #333]\\[GITHUB][/]",
    "claude": "[bold #cc85ff]\\[CLAUDE][/]",
    "local": "[dim]\\[LOCAL][/]",
}

SPINNER_FRAMES = [
    "[ *    ]",
    "[  *   ]",
    "[   *  ]",
    "[    * ]",
    "[   *  ]",
    "[  *   ]",
]

TYPE_COLORS = {
    "Python": "green",
    "Node": "yellow",
    "Bash": "cyan",
    "Rust": "red",
    "Go": "blue",
    "Static": "magenta",
    "Unknown": "white",
}

WELCOME_ART = r"""
  +-------------------------------------------------+
  |                                                 |
  |   ____          _        ___                _   |
  |  / ___|___   __| | ___  / _ \ _   _  ___  | |  |
  | | |   / _ \ / _` |/ _ \| | | | | | |/ _ \ | |  |
  | | |__| (_) | (_| |  __/| |_| | |_| |  __/ |_|  |
  |  \____\___/ \__,_|\___| \__\_\\__,_|\___| (_)  |
  |                                                 |
  |        YOUR PROJECT COMMAND CENTER              |
  |                                                 |
  +-------------------------------------------------+
"""

NO_README = """
No README found for this project.

Detected project type: {project_type}

Tip: Add a README.md to help CodeQuest
understand your project better!
"""
